#!/usr/bin/env python3
"""Read-only Codex RPC worker. No model turns, auth-file access or billing APIs."""

import argparse
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time

REFRESH_SECONDS = 120
TIMEOUT_SECONDS = 12


class QuotaError(Exception):
    pass


def directory(variable, fallback):
    value = os.environ.get(variable)
    return Path(value) if value and Path(value).is_absolute() else Path.home() / fallback


def state_path():
    return directory("XDG_STATE_HOME", ".local/state") / "quotamonitor/quota.json"


def config_path():
    return directory("XDG_CONFIG_HOME", ".config") / "quotamonitor/config.json"


def load_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_json(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Atomic replacement prevents the shell from reading a half-written cache.
    handle, temporary = tempfile.mkstemp(prefix=".quota-", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def codex_executable():
    configured = load_json(config_path()).get("codexExecutable")
    if configured:
        if isinstance(configured, str) and Path(configured).is_absolute() and os.access(configured, os.X_OK):
            return configured
        raise QuotaError("Lagret Codex-sti finnes ikke. Kjør install.py på nytt fra terminalen.")
    candidates = [shutil.which("codex"), str(Path.home() / ".local/bin/codex"),
                  str(Path.home() / ".npm-global/bin/codex"), "/usr/local/bin/codex", "/usr/bin/codex"]
    for candidate in candidates:
        if candidate and os.access(candidate, os.X_OK):
            return candidate
    raise QuotaError("Fant ikke Codex CLI. Kjør install.py fra terminalen der codex fungerer.")


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def parse_limits(result):
    if not isinstance(result, dict):
        raise QuotaError("Ugyldig kvotesvar fra Codex.")
    by_id = result.get("rateLimitsByLimitId")
    limits = by_id.get("codex") if isinstance(by_id, dict) else None
    if not isinstance(limits, dict):
        limits = result.get("rateLimits")
    if not isinstance(limits, dict):
        raise QuotaError("Ingen Codex-kvoter i svaret. Kontroller innlogging i Codex CLI.")
    windows = [limits.get("primary"), limits.get("secondary")]
    snapshot = {}
    for name, duration in (("fiveHour", 300), ("weekly", 10080)):
        window = next((w for w in windows if isinstance(w, dict) and
                       w.get("windowDurationMins") == duration), {})
        used = window.get("usedPercent")
        # Match Swift's nonnegative percentage rounding, including .5 ties.
        snapshot[name + "Remaining"] = max(0, min(100, math.floor(100 - used + 0.5))) if finite_number(used) else None
        reset = window.get("resetsAt")
        # resetsAt is Unix seconds from Codex; never synthesize a reset date.
        snapshot[name + "Reset"] = reset if finite_number(reset) and 0 <= reset <= 253402300799 else None
    if snapshot["fiveHourRemaining"] is None and snapshot["weeklyRemaining"] is None:
        raise QuotaError("Codex returnerte ingen gyldige 5-timers- eller ukeskvoter.")
    return snapshot


def read_codex(argv=None, timeout=TIMEOUT_SECONDS):
    command = argv if argv is not None else [codex_executable()]
    environment = os.environ.copy()
    # An npm/NVM Codex launcher may use '#!/usr/bin/env node'. Its sibling
    # node executable must be discoverable even outside the terminal session.
    environment["PATH"] = str(Path(command[0]).parent) + os.pathsep + environment.get("PATH", "/usr/local/bin:/usr/bin:/bin")
    process = subprocess.Popen(command + ["app-server", "--listen", "stdio://"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, env=environment)
    deadline = time.monotonic() + timeout
    buffer = b""
    try:
        def send(message):
            process.stdin.write(json.dumps(message).encode("utf-8") + b"\n")
            process.stdin.flush()

        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "quota_monitor_gnome", "title": "QuotaMonitor", "version": "1.0"}}})
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise QuotaError("Codex svarte ikke innen 12 sekunder.")
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    raise QuotaError("Codex avsluttet før kvotene ble mottatt.")
                buffer += chunk
                if len(buffer) > 2 * 1024 * 1024:
                    raise QuotaError("For stort svar fra Codex.")
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        message = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if not isinstance(message, dict) or message.get("id") not in (1, 2):
                        continue
                    if message.get("error") is not None:
                        raise QuotaError("Codex avviste kvoteforespørselen. Kontroller innlogging i Codex CLI.")
                    if message["id"] == 1:
                        send({"method": "initialized", "params": {}})
                        send({"id": 2, "method": "account/rateLimits/read", "params": {}})
                    else:
                        return parse_limits(message.get("result"))
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for stream in (process.stdin, process.stdout):
            try:
                stream.close()
            except OSError:
                pass


def refresh(previous, force=False, reader=read_codex, now=None):
    now = time.time() if now is None else now
    attempted = previous.get("lastAttemptAt")
    # Re-enabling the extension or unlocking does not increase automatic RPC frequency.
    if not force and finite_number(attempted) and 0 <= now - attempted < REFRESH_SECONDS:
        return previous
    updated = dict(previous)
    updated["lastAttemptAt"] = now
    try:
        snapshot = reader()
        updated.update(snapshot)
        updated.update(lastUpdated=now, lastRefreshFailed=False, error=None)
    except (QuotaError, OSError, ValueError) as error:
        # Do not touch quota values, reset dates or last successful update time.
        updated.update(lastRefreshFailed=True, error=str(error)[:300])
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cached-only", action="store_true", help="Print cached data without contacting Codex")
    parser.add_argument("--force", action="store_true", help="Manual refresh; bypass the 120-second automatic interval")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    previous = load_json(state_path())
    data = previous if args.cached_only else refresh(previous, force=args.force)
    if not args.cached_only and data is not previous:
        try:
            save_json(state_path(), data)
        except OSError:
            # Still deliver valid values to the UI when the cache cannot be saved.
            data["cacheWarning"] = "Kunne ikke lagre siste data på disk."
    print(json.dumps(data, allow_nan=False))


if __name__ == "__main__":
    main()
