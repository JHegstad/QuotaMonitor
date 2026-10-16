import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("quota_reader", Path(__file__).parents[1] / "extension/quota_reader.py")
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)


def limits(primary=None, secondary=None):
    return {"rateLimits": {"primary": primary, "secondary": secondary}}


def window(duration, used, reset=1792146000):
    return {"windowDurationMins": duration, "usedPercent": used, "resetsAt": reset}


class ParserTests(unittest.TestCase):
    def test_both_windows_and_exact_reset_timestamp(self):
        data = reader.parse_limits(limits(window(300, 18), window(10080, 39)))
        self.assertEqual(data, {"fiveHourRemaining": 82, "weeklyRemaining": 61,
                                "fiveHourReset": 1792146000, "weeklyReset": 1792146000})

    def test_codex_specific_limits_take_precedence_and_window_order_is_irrelevant(self):
        result = limits(window(300, 99))
        result["rateLimitsByLimitId"] = {"codex": {"primary": window(10080, 59), "secondary": window(300, 26)}}
        data = reader.parse_limits(result)
        self.assertEqual((data["fiveHourRemaining"], data["weeklyRemaining"]), (74, 41))

    def test_one_window_is_available(self):
        data = reader.parse_limits(limits(window(10080, 100, None)))
        self.assertIsNone(data["fiveHourRemaining"])
        self.assertEqual(data["weeklyRemaining"], 0)
        self.assertIsNone(data["weeklyReset"])

    def test_missing_and_malformed_percentages_are_failures_not_zero(self):
        for used in (None, "18", True, float("nan"), float("inf")):
            with self.subTest(used=used), self.assertRaises(reader.QuotaError):
                reader.parse_limits(limits(window(300, used)))

    def test_missing_limits_and_unknown_windows_fail(self):
        for result in (None, {}, limits(window(60, 1))):
            with self.subTest(result=result), self.assertRaises(reader.QuotaError):
                reader.parse_limits(result)

    def test_rounding_clamping_and_no_invented_reset(self):
        for used, expected in ((17.5, 83), (-2, 100), (102, 0)):
            data = reader.parse_limits(limits(window(300, used, "tomorrow")))
            self.assertEqual(data["fiveHourRemaining"], expected)
            self.assertIsNone(data["fiveHourReset"])


class PersistenceTests(unittest.TestCase):
    def test_failure_retains_all_last_successful_values(self):
        previous = {"fiveHourRemaining": 18, "weeklyRemaining": 63,
                    "fiveHourReset": 10000, "weeklyReset": 20000, "lastUpdated": 9000}
        def fail():
            raise reader.QuotaError("offline")
        actual = reader.refresh(previous, reader=fail, now=10000)
        for key, value in previous.items():
            self.assertEqual(actual[key], value)
        self.assertEqual(actual["lastAttemptAt"], 10000)
        self.assertTrue(actual["lastRefreshFailed"])
        self.assertNotIn("lastRefreshFailed", previous)

    def test_success_clears_failure_and_advances_success_time(self):
        previous = {"lastRefreshFailed": True, "error": "offline", "lastUpdated": 10}
        actual = reader.refresh(previous, reader=lambda: {"fiveHourRemaining": 82}, now=200)
        self.assertFalse(actual["lastRefreshFailed"])
        self.assertIsNone(actual["error"])
        self.assertEqual(actual["lastUpdated"], 200)

    def test_automatic_interval_and_manual_override(self):
        calls = []
        previous = {"lastAttemptAt": 1000}
        def fetch():
            calls.append(True)
            return {"weeklyRemaining": 41}
        self.assertIs(reader.refresh(previous, reader=fetch, now=1119), previous)
        self.assertEqual(calls, [])
        reader.refresh(previous, reader=fetch, now=1120)
        reader.refresh(previous, reader=fetch, now=1001, force=True)
        self.assertEqual(len(calls), 2)

    def test_state_round_trip_and_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "quotamonitor/quota.json"
            data = {"fiveHourRemaining": 0, "weeklyReset": 12345, "lastRefreshFailed": True}
            reader.save_json(path, data)
            self.assertEqual(reader.load_json(path), data)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_cached_only_never_attempts_rpc(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = {"fiveHourRemaining": 82, "lastUpdated": 12345}
            reader.save_json(Path(temporary) / "quotamonitor/quota.json", data)
            env = dict(os.environ, XDG_STATE_HOME=temporary, PATH="/no-executables-here")
            result = subprocess.run([sys.executable, str(SPEC.origin), "--cached-only"], env=env,
                                    capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout), data)


class RPCTests(unittest.TestCase):
    def fake(self, directory, body):
        path = Path(directory) / "fake_codex.py"
        path.write_text(body, encoding="utf-8")
        return [sys.executable, str(path)]

    def test_real_stdio_exchange_only_initialization_and_read_only_rpc(self):
        with tempfile.TemporaryDirectory() as temporary:
            argv = self.fake(temporary, '''import json, sys, time
assert sys.argv[1:] == ["app-server", "--listen", "stdio://"]
first = json.loads(sys.stdin.readline())
assert first["id"] == 1 and first["method"] == "initialize"
print(json.dumps({"id": 1, "result": {}}), flush=True)
assert json.loads(sys.stdin.readline())["method"] == "initialized"
request = json.loads(sys.stdin.readline())
assert request == {"id": 2, "method": "account/rateLimits/read", "params": {}}
print("not-json", flush=True)
print(json.dumps({"method": "notification"}), flush=True)
print(json.dumps({"id": 2, "result": {"rateLimits": {"primary": {
    "windowDurationMins": 300, "usedPercent": 18, "resetsAt": 1792146000}}}}), flush=True)
time.sleep(30)
''')
            started = time.monotonic()
            self.assertEqual(reader.read_codex(argv)["fiveHourRemaining"], 82)
            self.assertLess(time.monotonic() - started, 3)

    def test_rpc_error_is_a_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            argv = self.fake(temporary, '''import json, sys
sys.stdin.readline()
print(json.dumps({"id": 1, "error": {"code": -1}}), flush=True)
''')
            with self.assertRaises(reader.QuotaError):
                reader.read_codex(argv)

    def test_timeout_reaps_the_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            pid_path = Path(temporary) / "pid"
            argv = self.fake(temporary, f'''import os, time
open({str(pid_path)!r}, "w").write(str(os.getpid()))
time.sleep(30)
''')
            started = time.monotonic()
            with self.assertRaises(reader.QuotaError):
                reader.read_codex(argv, timeout=0.3)
            self.assertLess(time.monotonic() - started, 3)
            pid = int(pid_path.read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_configured_nvm_path_does_not_depend_on_shell_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "bin with spaces/codex"
            executable.parent.mkdir()
            executable.touch(mode=0o700)
            config = Path(temporary) / "quotamonitor/config.json"
            reader.save_json(config, {"codexExecutable": str(executable)})
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": temporary, "PATH": "/no-node"}):
                self.assertEqual(reader.codex_executable(), str(executable))

    def test_launcher_finds_a_sibling_interpreter_with_an_empty_shell_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "codex"
            # Stand in for an NVM install's sibling node interpreter without
            # requiring Node or a real Codex installation in this test.
            (Path(temporary) / "node").symlink_to(sys.executable)
            executable.write_text('''#!/usr/bin/env node
import json, sys, time
sys.stdin.readline()
print(json.dumps({"id": 1, "result": {}}), flush=True)
sys.stdin.readline()
sys.stdin.readline()
print(json.dumps({"id": 2, "result": {"rateLimits": {"primary": {
    "windowDurationMins": 300, "usedPercent": 18}}}}), flush=True)
time.sleep(30)
''', encoding="utf-8")
            executable.chmod(0o700)
            with patch.dict(os.environ, {"PATH": "/no-interpreters"}):
                data = reader.read_codex([str(executable)])
            self.assertEqual(data["fiveHourRemaining"], 82)

    def test_disabling_worker_reaps_its_codex_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "codex"
            pid_path = root / "child.pid"
            executable.write_text(f'''#!{sys.executable}
import os, time
open({str(pid_path)!r}, "w").write(str(os.getpid()))
time.sleep(30)
''', encoding="utf-8")
            executable.chmod(0o700)
            reader.save_json(root / "config/quotamonitor/config.json", {"codexExecutable": str(executable)})
            env = dict(os.environ, XDG_CONFIG_HOME=str(root / "config"), XDG_STATE_HOME=str(root / "state"))
            process = subprocess.Popen([sys.executable, str(SPEC.origin), "--force"], env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 3
                while not pid_path.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(pid_path.exists(), "fake Codex child did not start")
                process.send_signal(signal.SIGTERM)
                process.communicate(timeout=3)
                self.assertEqual(process.returncode, 0)
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(pid_path.read_text()), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()


if __name__ == "__main__":
    unittest.main()
