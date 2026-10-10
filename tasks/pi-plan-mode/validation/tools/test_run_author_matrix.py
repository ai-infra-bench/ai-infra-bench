#!/usr/bin/env python3
"""Exercise the matrix launcher's paths with fake executables, not Harbor runs."""
from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TASK = Path(__file__).resolve().parents[2]
REPO = TASK.parents[1]


class AuthorMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="plan-author-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.task = self.repo / "tasks/pi-plan-mode"
        (self.task / "validation/tools").mkdir(parents=True)
        for relative in ("validation/ci-cases.json", "validation/tools/run_author_matrix.py"):
            shutil.copyfile(TASK / relative, self.task / relative)
        self.output = self.root / "synthetic-output"
        self.helper = self.repo / ".github/scripts/task_ci.py"
        self.helper.parent.mkdir(parents=True)
        # Reuse only today's actual parser definition; none of its real command
        # implementations are imported or executed. A changed CLI will fail here.
        source = (REPO / ".github/scripts/task_ci.py").read_text()
        tree = ast.parse(source)
        parser_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_parser")
        parser_source = ast.get_source_segment(source, parser_node)
        handlers = {node.id for node in ast.walk(parser_node) if isinstance(node, ast.Name) and node.id.startswith("command_")}
        fake_helper = '''import argparse, json, sys
from pathlib import Path
repo = Path(__file__).resolve().parents[2]
assert Path.cwd() == repo, "helper must run from the task's repository"
'''
        fake_helper += "\n".join(f"{name} = None" for name in sorted(handlers)) + "\n" + parser_source + '''
args = build_parser().parse_args()
with (repo / "fake-helper-calls.jsonl").open("a") as out:
    out.write(json.dumps({"argv": sys.argv[1:], "cwd": str(Path.cwd())}) + "\\n")
failure_file = repo / "fake-failures.json"
failures = json.loads(failure_file.read_text()) if failure_file.exists() else {}
if args.command in failures:
    raise SystemExit(failures[args.command])
if args.command == "validate":
    assert args.tasks == ["pi-plan-mode"]
elif args.command == "image-check":
    assert args.task == "pi-plan-mode" and args.image == "sha256:synthetic"
elif args.command == "prepare-case":
    assert args.task == "pi-plan-mode" and args.image == "sha256:synthetic"
    prepared = Path(args.output)
    prepared.mkdir(parents=True)
    (prepared / "FIXTURE_ONLY").write_text(args.case)
    print("nop" if args.case == "base" else "oracle")
elif args.command == "check-result":
    assert Path(args.result).is_file()
    print(json.dumps({"completed": 1, "errored": 0, "rewards": [float(args.expected_reward)]}))
else:
    raise AssertionError("Unexpected helper command")
'''
        self.helper.write_text(fake_helper)
        self.harbor = self.repo / "fake-harbor"
        self.harbor.write_text(f"#!{sys.executable}\n" + '''import argparse, json, sys
from pathlib import Path
repo = Path(__file__).resolve().parent
if sys.argv[1:] == ["--version"]:
    print("SYNTHETIC-NOT-HARBOR")
    raise SystemExit(0)
assert Path.cwd() == repo, "launcher must run from the task's repository"
parser = argparse.ArgumentParser()
parser.add_argument("command", choices=["run"])
for flag in ["--path", "--agent", "--env", "--jobs-dir", "--job-name", "--n-concurrent"]:
    parser.add_argument(flag, required=True)
for flag in ["--delete", "--yes"]:
    parser.add_argument(flag, action="store_true", required=True)
args = parser.parse_args()
assert args.env == "docker" and args.n_concurrent == "1"
name = (Path(args.path) / "FIXTURE_ONLY").read_text()
assert args.agent == ("nop" if name == "base" else "oracle")
assert args.job_name == "pi-plan-mode--" + name
result = Path(args.jobs_dir) / args.job_name / "result.json"
result.parent.mkdir(parents=True)
result.write_text(json.dumps({"fixture_only": True, "case": name}))
failure_file = repo / "fake-failures.json"
failures = json.loads(failure_file.read_text()) if failure_file.exists() else {}
raise SystemExit(failures.get("harbor", 0))
''')
        self.harbor.chmod(0o755)

    def run_matrix(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.task / "validation/tools/run_author_matrix.py"),
                               "--image", "sha256:synthetic", "--output", str(self.output),
                               "--harbor", str(self.harbor), "--workers", "2", *extra],
                              cwd=self.root, capture_output=True, text=True)

    def inject_failure(self, stage: str, code: int) -> None:
        (self.repo / "fake-failures.json").write_text(json.dumps({stage: code}))

    def test_complete_catalog_paths_and_current_helper_arguments(self) -> None:
        result = self.run_matrix()
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads((self.output / "summary.json").read_text())
        catalog = json.loads((self.task / "validation/ci-cases.json").read_text())["cases"]
        expected = {"base": 0, "oracle": 1, **{item["name"]: item["expected_reward"] for item in catalog}}
        self.assertEqual({item["case"]: item["expected_reward"] for item in summary["results"]}, expected)
        self.assertEqual(summary["harbor"], "SYNTHETIC-NOT-HARBOR")
        self.assertEqual(summary["image"], "sha256:synthetic")
        for item in summary["results"]:
            self.assertEqual(item["harbor_exit_code"], 0)
            self.assertEqual(item["check_exit_code"], 0)
            self.assertEqual(json.loads(item["check_output"])["rewards"], [float(expected[item["case"]])])
            self.assertEqual(json.loads((self.output / (item["case"] + ".check.json")).read_text()), item)
            self.assertTrue((self.output / (item["case"] + ".log")).is_file())
        calls = [json.loads(line) for line in (self.repo / "fake-helper-calls.jsonl").read_text().splitlines()]
        self.assertEqual(calls[0]["argv"], ["validate", "pi-plan-mode"])
        self.assertEqual(calls[1]["argv"], ["image-check", "--task", "pi-plan-mode", "--image", "sha256:synthetic"])
        self.assertEqual(len(calls), 2 + 2 * len(expected))

    def test_explicit_subset(self) -> None:
        result = self.run_matrix("--cases", "oracle")
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual([item["case"] for item in summary["results"]], ["oracle"])

    def test_harbor_failure_is_retained_and_returns_failure(self) -> None:
        self.inject_failure("harbor", 7)
        result = self.run_matrix("--cases", "base")
        self.assertEqual(result.returncode, 1, result.stderr)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(summary["results"][0]["harbor_exit_code"], 7)
        self.assertEqual(summary["results"][0]["check_exit_code"], 0)

    def test_checker_failure_is_retained_and_returns_failure(self) -> None:
        self.inject_failure("check-result", 9)
        result = self.run_matrix("--cases", "oracle")
        self.assertEqual(result.returncode, 1, result.stderr)
        summary = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(summary["results"][0]["harbor_exit_code"], 0)
        self.assertEqual(summary["results"][0]["check_exit_code"], 9)

    def test_preflight_failure_does_not_launch_or_publish_summary(self) -> None:
        self.inject_failure("validate", 4)
        result = self.run_matrix()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.output / "summary.json").exists())
        self.assertFalse((self.output / "jobs").exists())
        calls = (self.repo / "fake-helper-calls.jsonl").read_text().splitlines()
        self.assertEqual(len(calls), 1)

    def test_unknown_case_rejected_before_output_creation(self) -> None:
        result = self.run_matrix("--cases", "not-declared")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown cases", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertFalse((self.repo / "fake-helper-calls.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
