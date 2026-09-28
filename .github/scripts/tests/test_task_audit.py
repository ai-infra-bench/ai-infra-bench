"""Benchmark policy and control-patch baselines in the maintainer audit."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
import re
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "task_auditor", ROOT / ".agents/skills/ai-infra-bench-task-review/scripts/audit_task_artifacts.py",
)
auditor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auditor)


class TaskAuditTests(unittest.TestCase):
    def test_cli_skill_and_ci_share_static_contract_checks(self):
        sys.path.insert(0, str(ROOT / ".github/scripts"))
        import task_ci
        from normalize_task_configs import normalize_config

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            task = repo / "tasks/vllm-asr-chunk-spacing"
            source = ROOT / "tasks" / task.name

            def reset():
                shutil.rmtree(task, ignore_errors=True)
                shutil.copytree(source, task, ignore=shutil.ignore_patterns("__pycache__"))

            def check(expected):
                try:
                    task_ci.validate_task(task)  # The CI corpus check uses this entry.
                    direct = True
                except task_ci.ContractError:
                    direct = False
                cli = subprocess.run(
                    [sys.executable, str(ROOT / ".github/scripts/task_ci.py"), "validate", str(task)],
                    capture_output=True, text=True,
                )
                skill = subprocess.run(
                    [sys.executable, str(ROOT / ".agents/skills/ai-infra-bench-task-review/scripts/audit_task_artifacts.py"), str(task)],
                    capture_output=True, text=True,
                )
                self.assertEqual(
                    (direct, cli.returncode == 0, skill.returncode == 0),
                    (expected, expected, expected), cli.stderr + skill.stdout + skill.stderr,
                )

            def field(section, key, value):
                path = task / "task.toml"
                text = path.read_text()
                header = "[[verifier.collect]]" if section == "verifier.collect" else f"[{section}]"
                start = text.index(header + "\n") + len(header) + 1 if section else 0
                following = re.search(r"(?m)^\[\[?[A-Za-z0-9_.-]+\]\]?\s*$", text[start:])
                end = start + following.start() if following else len(text)
                block = text[start:end]
                existing = re.search(r"(?m)^" + re.escape(key) + r"[ \t]*=.*\n?", block)
                line = "" if value is None else f"{key} = {json.dumps(value)}\n"
                if existing:
                    block = block[:existing.start()] + line + block[existing.end():]
                else:
                    block = block.rstrip() + "\n" + line + "\n"
                path.write_text(normalize_config(text[:start] + block + text[end:]))

            reset()
            check(True)
            for section, key, value in (
                ("", "schema_version", "0.0"), ("", "schema_version", None),
                ("", "publication_state", "published"),
                ("", "artifacts", []),
                ("task", "name", "wrong/task"), ("task", "name", None),
                ("task", "description", ""), ("task", "description", 42),
                ("task", "description", "<observable failure>"),
                ("task", "descripton", "typo"), ("task", "version", "2.0.0"),
                ("task", "authors", ["Example"]),
                ("task", "keywords", ["vllm", " "]),
                ("task", "keywords", ["vllm", 42]),
                ("task", "keywords", ["vllm", "vllm"]),
                ("task", "keywords", ["vllm", "gpu worker"]),
                ("task", "keywords", ["vllm", "GPU/worker"]),
                ("task", "keywords", ["vllm", "<subsystem>"]),
                ("metadata", "domain", "other"), ("metadata", "domain", None),
                ("metadata", "task_type", "other"), ("metadata", "source_ids", ["old"]),
                ("metadata", "base_commit", "invalid"),
                ("metadata", "dependency_cutoff", "not-a-date"),
                ("metadata", "dependency_cutoff", "2026-02-30T00:00:00Z"),
                ("metadata", "dependency_cutoff", "2000-01-01T00:00:00Z"),
                ("environment", "cpus", 4), ("environment", "memory_mb", 8192),
                ("environment", "storage_mb", 10240), ("environment", "build_timeout_sec", 600),
                ("environment", "memory_mib", 1), ("environment", "network_mode", "public"),
                ("environment", "docker_image", "example:old"), ("environment", "gpus", None),
                ("agent", "timeout_sec", 600), ("agent", "timout_sec", 600),
                ("verifier", "timeout_sec", 600), ("verifier", "timout_sec", 600),
                ("verifier", "environment_mode", "shared"),
                ("verifier.collect", "timeout_sec", 30), ("verifier.collect", "user", "other"),
            ):
                with self.subTest(section=section, key=key, value=value):
                    reset()
                    field(section, key, value)
                    check(False)
            for missing in ("task.toml", "instruction.md", "tests/test.sh", "solution/solve.sh"):
                with self.subTest(missing=missing):
                    reset()
                    (task / missing).unlink()
                    check(False)
            for placeholder in ("", " \n", "<task instructions>", "TODO", "TBD"):
                with self.subTest(instruction=placeholder):
                    reset()
                    (task / "instruction.md").write_text(placeholder)
                    check(False)
            for empty in ("", "# No configuration yet\n"):
                with self.subTest(config=empty):
                    reset()
                    (task / "task.toml").write_text(empty)
                    check(False)
            reset()
            path = task / "task.toml"
            path.write_text(path.read_text() + "\n[accidental]\nsetting = true\n")
            check(False)
            reset()
            path = task / "task.toml"
            path.write_text(path.read_text().replace("set -eu\n", "set -e\n", 1))
            check(False)
            reset()
            path = task / "task.toml"
            text = path.read_text()
            first = re.search(r"(?m)^name = .*\n", text)[0]
            second = re.search(r"(?m)^version = .*\n", text)[0]
            path.write_text(text.replace(first + second, second + first, 1))
            check(False)
            reset()
            field("task", "description", "Preserve <parameter> values in XML inputs.")
            (task / "instruction.md").write_text('Preserve this XML: <parameter name="topic">hello</parameter>.\n')
            check(True)

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
