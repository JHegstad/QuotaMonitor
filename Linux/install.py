#!/usr/bin/env python3
"""Install QuotaMonitor for the current Ubuntu/GNOME 46 user (no sudo)."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

UUID = "quotamonitor@hegstad.no"


def xdg_path(variable, fallback):
    value = os.environ.get(variable)
    return Path(value) if value and Path(value).is_absolute() else Path.home() / fallback


def install(codex):
    if sys.platform != "linux":
        raise RuntimeError("Run this installer on Ubuntu, not on the Mac.")
    if os.geteuid() == 0:
        raise RuntimeError("Run as your desktop user without sudo.")
    for executable in ("gnome-shell", "glib-compile-schemas", "gnome-extensions"):
        if not shutil.which(executable):
            raise RuntimeError("Missing prerequisite: " + executable)
    version = subprocess.check_output(["gnome-shell", "--version"], text=True).strip()
    if not version.startswith("GNOME Shell 46."):
        raise RuntimeError("This version targets GNOME Shell 46; found " + version)

    codex = codex or shutil.which("codex")
    if not codex:
        raise RuntimeError("Codex CLI not found. Run from a terminal where 'command -v codex' works, "
                           "or pass --codex /absolute/path/to/codex.")
    codex_path = Path(codex).expanduser().absolute()
    if not codex_path.is_file() or not os.access(codex_path, os.X_OK):
        raise RuntimeError("Not an executable file: " + str(codex_path))
    source = Path(__file__).resolve().parent / "extension"
    if not (source / "metadata.json").is_file():
        raise RuntimeError("Keep install.py beside the extension folder from the download.")

    data_root = xdg_path("XDG_DATA_HOME", ".local/share")
    target = data_root / "gnome-shell/extensions" / UUID
    config = xdg_path("XDG_CONFIG_HOME", ".config") / "quotamonitor/config.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    # Compile and validate in a staging directory before touching an existing install.
    with tempfile.TemporaryDirectory(prefix="quotamonitor-install-") as temporary:
        staged = Path(temporary) / UUID
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        subprocess.run(["glib-compile-schemas", "--strict", str(staged / "schemas")], check=True)
        if target.exists():
            backup_root = data_root / "quotamonitor/backups"
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = backup_root / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            shutil.copytree(target, backup)
            print("Previous extension backed up to:", backup)
            subprocess.run(["gnome-extensions", "disable", UUID], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.copytree(staged, target, dirs_exist_ok=True)
    config.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    existing = {}
    if config.exists():
        try:
            existing = json.loads(config.read_text(encoding="utf-8"))
        except ValueError:
            raise RuntimeError("Existing config is not valid JSON; extension installed but config left unchanged: " + str(config))
        if not isinstance(existing, dict):
            raise RuntimeError("Existing config is not a JSON object; config left unchanged: " + str(config))
    existing["codexExecutable"] = str(codex_path)
    config.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    config.chmod(0o600)
    print("Installed:", target)
    print("Codex executable:", codex_path)
    print("\nLog out of GNOME and log back in, then run:\n")
    print("    gnome-extensions enable " + UUID)
    print("\nUse the Work percentage in the top bar to refresh or position the desktop card.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", help="Absolute path to the Codex CLI; defaults to the terminal PATH")
    args = parser.parse_args()
    try:
        install(args.codex)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print("Installation failed:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
