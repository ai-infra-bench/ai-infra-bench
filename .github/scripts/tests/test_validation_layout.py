"""Release validation paths and control preparation."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".github/scripts"))
import task_ci


class ValidationLayoutTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.task = self.root / "example"
        (self.task / "validation/patches").mkdir(parents=True)
        (self.task / "solution").mkdir()
        (self.task / "tests").mkdir()
        (self.task / "environment").mkdir()
        for relative, content in {
            "task.toml": '[environment]\nworkdir = "/workspace/repo"\n',
            "instruction.md": "Repair the example.\n",
            "environment/Dockerfile": "FROM scratch\n",
            "solution/solve.sh": "#!/bin/sh\ngit apply /solution/oracle.patch\n",
            "solution/oracle.patch": "oracle patch\n",
            "tests/test.sh": "#!/bin/sh\nexit 0\n",
            "validation/patches/control.patch": "control patch\n",
        }.items():
            (self.task / relative).write_text(content)
        self.manifest = {
            "schema_version": "ai_infra_bench_validation_cases.v2",
            "cases": [{
                "name": "control", "patch": "patches/control.patch",
                "patch_sha256": hashlib.sha256(b"control patch\n").hexdigest(),
                "expected_reward": 0,
            }],
        }
        self.save_manifest()

    def save_manifest(self):
        (self.task / "validation/ci-cases.json").write_text(json.dumps(self.manifest))

    def test_release_corpus_has_only_current_validation_material(self):
        directories = sorted((ROOT / "tasks").glob("*/validation"))
        self.assertTrue(directories)
        for directory in directories:
            with self.subTest(task=directory.parent.name):
                self.assertTrue({p.name for p in directory.iterdir()} <= {
                    "ci-cases.json", "patches", "tools",
                })
                for path in directory.rglob("*"):
                    self.assertNotIn("history", path.relative_to(directory).parts)
                    self.assertNotIn(path.suffix, {".md", ".log", ".zip", ".gz"})
                    if path.is_file() and path.suffix == ".py":
                        compile(path.read_text(), str(path), "exec")
                manifest = task_ci.validation_manifest(directory.parent)
                self.assertEqual(manifest["schema_version"], "ai_infra_bench_validation_cases.v2")
                self.assertFalse({"status", "superseded_security_controls"} & manifest.keys())
                for case in manifest["cases"]:
                    self.assertFalse({"execution_status", "observed_reward", "task_version", "historical_result"} & case.keys())
                task_ci.validate_task(directory.parent)
                task_ci.matrix_entry(directory.parent, "manual")

    def test_v2_controls_prepare_from_patches_directory(self):
        self.assertEqual(task_ci.validation_manifest(self.task), self.manifest)
        output = self.root / "prepared"
        agent = task_ci.prepare_case(self.task, "example-image", "control", output)
        self.assertEqual(agent, "oracle")
        self.assertEqual((output / "solution/ci-case.patch").read_text(), "control patch\n")
        self.assertIn("git apply", (output / "solution/solve.sh").read_text())

    def test_noncanonical_paths_symlinks_missing_and_unlisted_controls_fail(self):
        for path in ("control.patch", "../control.patch", "/tmp/control.patch", "patches/../control.patch", "patches//control.patch", "patches\\control.patch"):
            with self.subTest(path=path):
                self.manifest["cases"][0]["patch"] = path
                self.save_manifest()
                with self.assertRaises(task_ci.ContractError):
                    task_ci.validation_manifest(self.task)
        self.manifest["cases"][0]["patch"] = "patches/control.patch"
        self.save_manifest()
        control = self.task / "validation/patches/control.patch"
        control.unlink()
        with self.assertRaises(task_ci.ContractError):
            task_ci.validation_manifest(self.task)
        external = self.root / "external.patch"
        external.write_text("control patch\n")
        control.symlink_to(external)
        with self.assertRaises(task_ci.ContractError):
            task_ci.validation_manifest(self.task)
        control.unlink()
        control.write_text("control patch\n")
        (control.parent / "unlisted.patch").write_text("unlisted\n")
        with self.assertRaises(task_ci.ContractError):
            task_ci.validation_manifest(self.task)

    def test_historical_v1_control_manifests_remain_readable(self):
        self.manifest["schema_version"] = "ai_infra_bench_validation_cases.v1"
        self.manifest["cases"][0]["patch"] = "control.patch"
        (self.task / "validation/patches/control.patch").rename(self.task / "validation/control.patch")
        self.save_manifest()
        self.assertEqual(task_ci.validation_manifest(self.task), self.manifest)


if __name__ == "__main__":
    unittest.main()
