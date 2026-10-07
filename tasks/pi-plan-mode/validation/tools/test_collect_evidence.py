#!/usr/bin/env python3
"""Curator-only collector checks using synthetic records, never Harbor evidence."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


TASK = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value) + "\n")


class CollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="plan-collector-synthetic-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.task = self.root / "task"
        for directory in ("validation/tools", "environment", "tests"):
            (self.task / directory).mkdir(parents=True)
        for relative in ("task.toml", "environment/image-manifest.json",
                         "validation/ci-cases.json", "validation/tools/collect_evidence.py"):
            shutil.copyfile(TASK / relative, self.task / relative)
        # Inputs and reports below are intentionally synthetic. The current
        # metadata/manifest/catalog are copied only to exercise their real schema.
        (self.task / "instruction.md").write_text("SYNTHETIC collector fixture, not a task run.\n")
        (self.task / "tests/test.sh").write_text("# SYNTHETIC verifier input\n")
        self.matrix_dir = self.root / "synthetic-matrix"
        self.matrix_dir.mkdir()
        self.output = self.matrix_dir / "synthetic-evidence.json"
        image = json.loads((self.task / "environment/image-manifest.json").read_text())
        controls = json.loads((self.task / "validation/ci-cases.json").read_text())["cases"]
        cases = [{"name": "base", "expected_reward": 0}, {"name": "oracle", "expected_reward": 1}, *controls]
        self.matrix = {"fixture_only": True, "image": image["image_id"],
                       "harbor": "SYNTHETIC-NOT-A-HARBOR-RUN", "results": []}
        for case in cases:
            name, reward = case["name"], case["expected_reward"]
            prepared = self.matrix_dir / "prepared" / name
            (prepared / "tests").mkdir(parents=True)
            for relative in ("instruction.md", "tests/test.sh"):
                shutil.copyfile(self.task / relative, prepared / relative)
            job = self.matrix_dir / "jobs" / name
            job.mkdir(parents=True)
            write_json(job / "result.json", {"fixture_only": True})
            for filename, contents in {
                "contract-summary.json": {"passed": bool(reward)},
                "lifecycle-summary.json": {"passed": True},
                "pass-to-pass-summary.json": {"passed": True},
                "scope.json": {"passed": True},
                "reward.json": {"reward": reward},
            }.items():
                write_json(job / filename, contents)
            self.matrix["results"].append({
                "case": name, "expected_reward": reward, "harbor_exit_code": 0,
                "check_exit_code": 0, "result": str(job / "result.json"),
                "check_output": json.dumps({"completed": 1, "errored": 0, "rewards": [float(reward)]}),
                "command": ["SYNTHETIC-harbor", "run", "--path", str(prepared),
                            "--jobs-dir", str(self.matrix_dir / "jobs")],
            })
        self.save_matrix()

    def save_matrix(self) -> None:
        write_json(self.matrix_dir / "summary.json", self.matrix)

    def run_collector(self, output: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.task / "validation/tools/collect_evidence.py"),
                               str(self.matrix_dir), "--output", str(output or self.output)],
                              capture_output=True, text=True)

    def assert_rejected(self, expected_message: str) -> None:
        self.save_matrix()
        result = self.run_collector()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected_message, result.stderr)
        self.assertFalse(self.output.exists())

    def test_complete_current_schema(self) -> None:
        result = self.run_collector()
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(self.output.read_text())
        metadata = tomllib.loads((self.task / "task.toml").read_text())
        self.assertEqual(evidence["task_version"], metadata["task"]["version"])
        for key in ("base_commit", "dependency_cutoff"):
            self.assertEqual(evidence[key], metadata["metadata"][key])
        self.assertEqual(evidence["image"], json.loads((self.task / "environment/image-manifest.json").read_text()))
        self.assertEqual(evidence["declared_resources"], {key: metadata["environment"][key] for key in
                                                       ("cpus", "memory_mb", "storage_mb", "gpus", "network_mode")})
        self.assertIsNone(evidence["actual_resources"])
        self.assertNotIn("hardware", evidence)
        self.assertNotIn("other_checks", evidence)
        self.assertEqual(len(evidence["harbor_runs"]), len(self.matrix["results"]))
        self.assertIn("tests/test.sh", evidence["artifacts"]["files"])
        for run in evidence["harbor_runs"]:
            self.assertFalse(Path(run["result"]).is_absolute())
            self.assertEqual(run["command"][0], "<harbor-launcher>")
            self.assertIn("reward.json", run["raw_artifact_sha256"])

    def test_manifest_without_optional_build(self) -> None:
        path = self.task / "environment/image-manifest.json"
        image = json.loads(path.read_text())
        image.pop("build", None)
        write_json(path, image)
        result = self.run_collector()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.output.read_text())["image"], image)

    def test_wrong_image(self) -> None:
        self.matrix["image"] = "sha256:wrong"
        self.assert_rejected("Matrix image does not match")

    def test_missing_case(self) -> None:
        self.matrix["results"].pop()
        self.assert_rejected("exactly once")

    def test_duplicate_case(self) -> None:
        self.matrix["results"].append(self.matrix["results"][0])
        self.assert_rejected("exactly once")

    def test_changed_expected_reward(self) -> None:
        self.matrix["results"][0]["expected_reward"] = 1
        self.assert_rejected("expected reward differs")

    def test_changed_observed_reward(self) -> None:
        self.matrix["results"][0]["check_output"] = json.dumps({"completed": 1, "errored": 0, "rewards": [1.0]})
        self.assert_rejected("Unexpected Harbor result")

    def test_changed_verifier_reward(self) -> None:
        write_json(self.matrix_dir / "jobs/base/reward.json", {"reward": 1})
        self.assert_rejected("Verifier reward differs")

    def test_behavior_does_not_explain_reward(self) -> None:
        write_json(self.matrix_dir / "jobs/base/contract-summary.json", {"passed": True})
        self.assert_rejected("Behavioral result does not explain reward")

    def test_instruction_hash_mismatch(self) -> None:
        (self.matrix_dir / "prepared/base/instruction.md").write_text("changed")
        self.assert_rejected("Trial snapshot differs")

    def test_verifier_hash_mismatch(self) -> None:
        (self.matrix_dir / "prepared/base/tests/test.sh").write_text("changed")
        self.assert_rejected("Trial snapshot differs")

    def test_failed_run(self) -> None:
        self.matrix["results"][0]["harbor_exit_code"] = 1
        self.assert_rejected("Unaccepted author run")

    def test_output_inside_task_rejected_before_read_or_write(self) -> None:
        (self.matrix_dir / "summary.json").unlink()
        output = self.task / "forbidden-evidence.json"
        result = self.run_collector(output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Evidence output must be outside the task directory", result.stderr)
        self.assertFalse(output.exists())

    def test_output_symlink_into_task_does_not_overwrite(self) -> None:
        protected = self.task / "instruction.md"
        original = protected.read_bytes()
        self.output.symlink_to(protected)
        result = self.run_collector()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Evidence output must be outside the task directory", result.stderr)
        self.assertEqual(protected.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
