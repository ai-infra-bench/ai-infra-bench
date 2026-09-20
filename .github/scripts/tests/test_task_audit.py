"""Benchmark policy and control-patch baselines in the maintainer audit."""

from contextlib import redirect_stdout
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "task_auditor", ROOT / ".agents/skills/ai-infra-bench-task-review/scripts/audit_task_artifacts.py",
)
auditor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auditor)


class TaskAuditTests(unittest.TestCase):
    def test_benchmark_policy_accepts_current_corpus_and_rejects_configuration_drift(self):
        for path in (ROOT / "tasks").glob("*/task.toml"):
            with self.subTest(task=path.parent.name), redirect_stdout(io.StringIO()):
                audit = auditor.Audit()
                auditor.check_benchmark_config(tomllib.loads(path.read_text()), audit)
                self.assertEqual(audit.errors, 0)

        original = tomllib.loads((ROOT / "tasks/vllm-asr-chunk-spacing/task.toml").read_text())
        for section, key, value in (
            ("agent", "timeout_sec", 600),
            ("agent", "timeout_sec", 72000),
            ("verifier", "timeout_sec", 600),
            ("verifier", "environment_mode", "separate"),
            ("environment", "cpus", 4),
            ("environment", "memory_mb", 8192),
            ("environment", "storage_mb", 10240),
            ("environment", "build_timeout_sec", 600),
            ("environment", "network_mode", "public"),
            ("environment", "docker_image", "example:old"),
            ("task", "keywords", ["vllm", "gpu-worker"]),
            ("task", "authors", ["Example"]),
        ):
            config = copy.deepcopy(original)
            config[section][key] = value
            with self.subTest(section=section, key=key, value=value), redirect_stdout(io.StringIO()):
                audit = auditor.Audit()
                auditor.check_benchmark_config(config, audit)
                self.assertGreater(audit.errors, 0)
        config = copy.deepcopy(original)
        config["verifier"]["collect"][0]["command"] = "true"
        with redirect_stdout(io.StringIO()):
            audit = auditor.Audit()
            auditor.check_benchmark_config(config, audit)
        self.assertGreater(audit.errors, 0)

    def test_image_audit_checks_controls_on_their_declared_base(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "task"
            base = root / "base"
            base.mkdir()
            for relative in ("environment", "solution", "validation/patches"):
                (task / relative).mkdir(parents=True)

            def git(*args):
                return subprocess.run(
                    ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
                    cwd=base, text=True, capture_output=True, check=True,
                ).stdout

            git("init", "-q")
            (base / "value.txt").write_text("base\n")
            git("add", ".")
            git("commit", "-qm", "base")
            (base / "value.txt").write_text("oracle\n")
            oracle = git("diff")
            (task / "solution/oracle.patch").write_text(oracle)
            (task / "validation/patches/from-base.patch").write_text(oracle)
            git("add", ".")
            (base / "value.txt").write_text("control\n")
            (task / "validation/patches/from-oracle.patch").write_text(git("diff"))
            git("reset", "--hard", "HEAD")
            cases = [{"patch": f"patches/from-{kind}.patch", "apply_after": kind} for kind in ("base", "oracle")]
            (task / "validation/ci-cases.json").write_text(json.dumps({"cases": cases}))
            image_id = "sha256:" + "a" * 64
            (task / "environment/image-manifest.json").write_text(json.dumps({"image_id": image_id}))
            runs = []

            def fake_run(command, **kwargs):
                if command[1:3] == ["image", "inspect"]:
                    return subprocess.CompletedProcess(command, 0, stdout=json.dumps([{"Id": image_id}]), stderr="")
                if command[:2] == ["docker", "run"]:
                    # Replace only Docker transport; exercise real Git patch application
                    # in a fresh writable checkout for each control.
                    checkout = root / f"check-{len(runs)}"
                    shutil.copytree(base, checkout)
                    start = command.index("-eu")
                    shell_args = [arg.replace("/task/", str(task) + "/") for arg in command[start:]]
                    result = subprocess.run(["sh", *shell_args], cwd=checkout, text=True, capture_output=True)
                    runs.append(result)
                    return result
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            audit = auditor.Audit()
            config = {"environment": {"workdir": "/workspace/repo"}}
            with patch.object(auditor.shutil, "which", return_value="docker"), patch.object(auditor, "run", side_effect=fake_run), redirect_stdout(io.StringIO()):
                auditor.check_image(task, config, ROOT, image_id, audit)
            self.assertEqual(len(runs), 3)
            self.assertEqual(audit.errors, 0, [r.stderr for r in runs])
            self.assertEqual((base / "value.txt").read_text(), "base\n")


if __name__ == "__main__":
    unittest.main()
