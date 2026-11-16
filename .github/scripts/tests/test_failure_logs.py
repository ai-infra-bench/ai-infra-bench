"""Read only fixed verifier output paths, without following candidate links."""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import task_ci

class FailureLogTests(unittest.TestCase):
    def render(self, job):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            task_ci.print_verifier_failure_logs(job)
        return output.getvalue()

    def test_only_regular_allowlisted_log_tail_is_printed_with_command_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory) / "job"
            verifier = job / "trial" / "verifier"
            verifier.mkdir(parents=True)
            (verifier / "test-stdout.txt").write_bytes(b"SECRET_PREFIX" + b"x" * 65536 + b"TAIL")
            (verifier / "other.txt").write_text("OTHER_SECRET")
            with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
                out = self.render(job)
            self.assertIn("TAIL", out)
            self.assertNotIn("SECRET_PREFIX", out)
            self.assertNotIn("OTHER_SECRET", out)
            token = out.splitlines()[0].removeprefix("::stop-commands::")
            self.assertEqual(out.splitlines()[-1], f"::{token}::")

    def test_scoring_error_and_stderr_survive_empty_or_missing_stdout(self):
        for stdout_exists in (False, True):
            with self.subTest(stdout_exists=stdout_exists), tempfile.TemporaryDirectory() as directory:
                job = Path(directory) / "job"
                verifier = job / "trial" / "verifier"
                verifier.mkdir(parents=True)
                if stdout_exists:
                    (verifier / "test-stdout.txt").touch()
                (verifier / "grading-status.json").write_text('{"status":"scoring_error","reason":"OBSERVER_FAILURE"}')
                (verifier / "test-stderr.txt").write_text("TRACEBACK_DETAIL")
                (verifier / "summary.json").write_text("UNRELATED_DATA")
                out = self.render(job)
                self.assertIn("OBSERVER_FAILURE", out)
                self.assertIn("TRACEBACK_DETAIL", out)
                self.assertNotIn("UNRELATED_DATA", out)

    def test_each_diagnostic_path_rejects_symlinks_and_bounds_output(self):
        for name in ("test-stdout.txt", "test-stderr.txt", "grading-status.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                job = root / "job"
                verifier = job / "trial" / "verifier"
                verifier.mkdir(parents=True)
                secret = root / "secret"
                secret.write_text("LINK_SECRET")
                log = verifier / name
                log.symlink_to(secret)
                self.assertNotIn("LINK_SECRET", self.render(job))
                log.unlink()
                log.write_bytes(b"OMITTED_PREFIX" + b"x" * 65536 + b"LOG_END")
                out = self.render(job)
                self.assertNotIn("OMITTED_PREFIX", out)
                self.assertIn("LOG_END", out)

    def test_symlinks_at_each_path_component_are_not_read(self):
        for component in ("ancestor", "job", "trial", "verifier", "test-stdout.txt"):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                job = root / "ancestor" / "job"
                log = job / "trial" / "verifier" / "test-stdout.txt"
                log.parent.mkdir(parents=True)
                log.write_text("SYMLINK_SECRET")
                chosen = {"ancestor": job.parent, "job": job, "trial": log.parent.parent,
                          "verifier": log.parent, "test-stdout.txt": log}[component]
                moved = root / "moved"
                chosen.rename(moved)
                chosen.symlink_to(moved, target_is_directory=moved.is_dir())
                self.assertNotIn("SYMLINK_SECRET", self.render(job))

    def test_fifo_is_skipped_without_blocking(self):
        # Run in a separate process with timeout: a regressed plain open would hang.
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory) / "job"
            log = job / "trial" / "verifier" / "test-stdout.txt"
            log.parent.mkdir(parents=True)
            os.mkfifo(log)
            result = subprocess.run([sys.executable, "-c",
                "from pathlib import Path; import task_ci; task_ci.print_verifier_failure_logs(Path(" + repr(str(job)) + "))"],
                env=dict(os.environ, PYTHONPATH=str(Path(task_ci.__file__).parent)),
                capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_job_is_diagnostic_only(self):
        with tempfile.TemporaryDirectory() as directory:
            self.render(Path(directory) / "missing")

    def test_check_result_keeps_original_error_when_diagnostics_fail(self):
        import argparse
        args = argparse.Namespace(result="missing/result.json", expected_reward=0)
        with patch.object(task_ci, "print_verifier_failure_logs", side_effect=RuntimeError("diagnostics broken")):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(FileNotFoundError):
                    task_ci.command_check_result(args)

    def test_reward_mismatch_prints_log_once_and_remains_failure(self):
        import argparse
        import json
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory)
            log = job / "trial" / "verifier" / "test-stdout.txt"
            log.parent.mkdir(parents=True)
            log.write_text("ONCE_MARKER")
            result = job / "result.json"
            result.write_text(json.dumps({"stats": {"n_completed_trials": 1,
                "n_errored_trials": 0, "evals": {"test": {"reward_stats": {
                    "reward": {"0.0": ["trial"]}}}}}}))
            output = io.StringIO()
            with contextlib.redirect_stdout(output), self.assertRaises(task_ci.ContractError):
                task_ci.command_check_result(argparse.Namespace(result=str(result), expected_reward=1))
            self.assertEqual(output.getvalue().count("ONCE_MARKER"), 1)
