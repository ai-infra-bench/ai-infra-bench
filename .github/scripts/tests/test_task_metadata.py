"""Metadata/build-input migration and comment-preserving config ordering."""

import argparse
from contextlib import redirect_stdout
import importlib.util
import io
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "templates/vllm-harbor-all-in-one"))
sys.path.insert(0, str(ROOT / ".github/scripts"))
from normalize_task_configs import normalize_config
from normalize_image_manifests import check_file_hashes, normalize_manifest
from build_config import load_build_config
import task_ci


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load_module("metadata_generator", "templates/vllm-harbor-all-in-one/generate.py")
locker = load_module("metadata_locker", "templates/vllm-harbor-all-in-one/lock.py")
auditor = load_module("metadata_auditor", ".agents/skills/ai-infra-bench-task-review/scripts/audit_task_artifacts.py")
builder = load_module("metadata_builder", "templates/vllm-harbor-all-in-one/build.py")


class TaskMetadataTests(unittest.TestCase):
    def test_ci_preparation_omits_snapshots_without_changing_formal_configs(self):
        with tempfile.TemporaryDirectory() as directory:
            for path in sorted((ROOT / "tasks").glob("*/task.toml")):
                with self.subTest(task=path.parent.name):
                    original = path.read_text()
                    expected = tomllib.loads(original)
                    self.assertTrue(expected["artifacts"])
                    expected["artifacts"] = []
                    expected["environment"]["docker_image"] = "ci-image:checked"
                    prepared = Path(directory) / path.parent.name
                    self.assertEqual(task_ci.prepare_case(
                        path.parent, "ci-image:checked", "base", prepared,
                    ), "nop")
                    self.assertEqual(tomllib.loads((prepared / "task.toml").read_text()), expected)
                    self.assertEqual(path.read_text(), original)

    def test_corpus_metadata_and_order_are_uniform(self):
        paths = sorted((ROOT / "tasks").glob("*/task.toml"))
        self.assertTrue(paths, "the benchmark corpus must not be empty")
        for path in paths:
            with self.subTest(path=path):
                text = path.read_text()
                config = tomllib.loads(text)
                self.assertEqual(list(config["metadata"]), ["task_type", "base_commit", "dependency_cutoff"])
                self.assertIn(config["metadata"]["task_type"], {"feature", "bugfix", "performance"})
                self.assertEqual(normalize_config(text), text)
                manifest = json.loads((path.parent / "environment/image-manifest.json").read_text())
                self.assertEqual(
                    json.dumps(normalize_manifest(manifest), ensure_ascii=False, indent=2) + "\n",
                    (path.parent / "environment/image-manifest.json").read_text(),
                )
                self.assertRegex(manifest["image_id"], r"^sha256:[0-9a-f]{64}$")
                check_file_hashes(manifest, path.parent / "environment")

    def test_manifest_normalization_preserves_image_identity_and_build_overrides(self):
        manifest = json.loads((ROOT / "tasks/vllm-dp-multi-port-supervisor/environment/image-manifest.json").read_text())
        shuffled = dict(reversed(list(manifest.items())))
        self.assertEqual(normalize_manifest(shuffled), manifest)
        self.assertEqual(normalize_manifest(shuffled)["build"], manifest["build"])
        with self.assertRaisesRegex(ValueError, "unknown"):
            normalize_manifest({**manifest, "new_provenance": "retain until reviewed"})

    def test_image_file_hash_checks_reject_stale_missing_and_escaping_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / "environment"
            (env / "lock").mkdir(parents=True)
            files = {"Dockerfile": "FROM scratch\n", "lock/requirements.txt": "example==1.0\n", "lock/manifest.json": "{}\n"}
            for relative, content in files.items():
                (env / relative).write_text(content)
            manifest = {"image_id": "sha256:" + "a" * 64, "files": {
                relative: hashlib.sha256(content.encode()).hexdigest() for relative, content in files.items()
            }}
            original = json.dumps(manifest)
            check_file_hashes(manifest, env)
            (env / "Dockerfile").write_text("FROM other-image\n")
            with self.assertRaisesRegex(ValueError, "stale.*Dockerfile"):
                check_file_hashes(manifest, env)
            self.assertEqual(json.dumps(manifest), original)
            (env / "Dockerfile").unlink()
            with self.assertRaisesRegex(ValueError, "Missing"):
                check_file_hashes(manifest, env)
            outside = env.parent / "outside"
            outside.write_text(files["Dockerfile"])
            (env / "Dockerfile").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "escaping"):
                check_file_hashes(manifest, env)
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                normalize_manifest({**manifest, "files": {**manifest["files"], "../outside": "a" * 64}})

    def test_builder_records_inspected_identity_and_input_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            env = task / "environment"
            (env / "lock").mkdir(parents=True)
            (task / "task.toml").write_text(
                '[task]\nname="ai-infra-bench/example"\n[metadata]\nbase_commit="'
                + "a" * 40 + '"\ndependency_cutoff="2026-01-01T00:00:00Z"\n'
            )
            for relative, content in {
                "Dockerfile": "FROM scratch\n", "lock/requirements.txt": "example==1.0\n",
                "lock/manifest.json": "{}\n",
            }.items():
                (env / relative).write_text(content)
            image_id = "sha256:" + "b" * 64
            repo_digest = "example@sha256:" + "c" * 64
            inspection = {"Id": image_id, "RepoDigests": [repo_digest], "Config": {"Labels": {
                "ai.infra.bench.base-commit": "a" * 40,
                "ai.infra.bench.dependency-cutoff": "2026-01-01T00:00:00Z",
            }}}

            def fake_run(*args, **kwargs):
                if args[:3] == ("docker", "image", "inspect"):
                    return subprocess.CompletedProcess(args, 0, stdout=json.dumps([inspection]))
                return subprocess.CompletedProcess(args, 0, stdout="")

            with patch.object(builder, "run", side_effect=fake_run), redirect_stdout(io.StringIO()):
                builder.build(task)
            manifest_path = env / "image-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["image_id"], image_id)
            self.assertEqual(set(manifest), {"image_id", "files"})
            self.assertEqual(manifest["files"]["Dockerfile"], builder.sha256_file(env / "Dockerfile"))
            check_file_hashes(manifest, env)
            self.assertEqual(manifest, normalize_manifest(manifest))
            original = manifest_path.read_text()
            inspection["Config"]["Labels"]["ai.infra.bench.base-commit"] = "d" * 40
            with patch.object(builder, "run", side_effect=fake_run), self.assertRaisesRegex(RuntimeError, "base-commit"):
                builder.build(task)
            self.assertEqual(manifest_path.read_text(), original)

    def test_sorting_preserves_comments_multiline_commands_and_values(self):
        text = """# document comment
artifacts = ["/workspace/repo"]
schema_version = "1.4"

[verifier]
timeout_sec = 7200
# runner identity
user = "root"

[task]
keywords = ["vllm", "scheduler"]
name = "ai-infra-bench/example"

[[verifier.collect]]
command = '''
# inside shell
[environment]
printf 'literal text'
'''
timeout_sec = 300
service = "main"

[environment]
build_timeout_sec = 10800
workdir = "/workspace/repo"
gpus = 0
"""
        result = normalize_config(text)
        self.assertEqual(tomllib.loads(result), tomllib.loads(text))
        self.assertEqual(normalize_config(result), result)
        self.assertIn("# document comment", result)
        self.assertIn('# runner identity\nuser = "root"', result)
        self.assertLess(result.index("schema_version"), result.index("artifacts ="))
        self.assertLess(result.index("[task]"), result.index("[environment]"))
        self.assertLess(result.index("[environment]"), result.index("[verifier]"))
        self.assertLess(result.index("[verifier]"), result.index("[[verifier.collect]]"))

    def test_runtime_assets_and_fixtures_are_read_from_build_config(self):
        for slug, function in (
            ("vllm-anthropic-inline-system-template", generator.runtime_asset_install),
            ("vllm-implement-anthropic-rust-serving", generator.runtime_asset_install),
            ("vllm-minimax-m3-streaming-reasoning", generator.runtime_asset_install),
            ("vllm-pyav-target-frame-selection", generator.runtime_file_install),
            ("vllm-responses-compound-tool-deltas", generator.runtime_file_install),
        ):
            task = ROOT / "tasks" / slug
            inputs = load_build_config(task)
            rendered = function(task / "task.toml")
            self.assertTrue(rendered, slug)
            for key in ("runtime_asset_revision", "runtime_asset_path", "runtime_file_sha256", "runtime_file_path"):
                if key in inputs:
                    self.assertIn(inputs[key], rendered, (slug, key))

    def test_lock_generation_retains_per_package_cutoff_exceptions(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory)
            lock = task / "environment/lock"
            lock.mkdir(parents=True)
            (lock / "extras.in").write_text("pytest\n")
            (task / "task.toml").write_text(
                '[metadata]\ntask_type="bugfix"\nbase_commit="' + "a" * 40
                + '"\ndependency_cutoff="2026-01-01T00:00:00Z"\n'
            )
            overrides = ["torch=2026-05-01T23:59:59Z"]
            (task / "environment/build-config.json").write_text(json.dumps({
                "schema_version": "vllm_build_config.v1", "dependency_cutoff_overrides": overrides,
            }))
            commands = []

            def fake_run(args, *, cwd):
                commands.append(args)
                if args[:2] == ["git", "clone"]:
                    for relative in ("requirements/cpu.txt", "requirements/cpu-build.txt", "requirements/common.txt"):
                        path = cwd / relative
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("torch\n")
                if args[0] == "uvx":
                    Path(args[args.index("--output-file") + 1]).write_text("torch==1.0\n")

            with patch.object(locker, "run", side_effect=fake_run), redirect_stdout(io.StringIO()):
                locker.generate(task)
            compile_command = next(c for c in commands if c[0] == "uvx")
            self.assertEqual(compile_command[-2:], ["--exclude-newer-package", overrides[0]])
            self.assertEqual(json.loads((lock / "manifest.json").read_text())["dependency_cutoff_overrides"], overrides)

    def test_verifier_only_task_still_has_no_oracle_case(self):
        output = io.StringIO()
        with redirect_stdout(output):
            task_ci.command_cases(argparse.Namespace(task="vllm-implement-anthropic-rust-serving"))
        cases = json.loads(output.getvalue())
        self.assertEqual(cases[0], {"name": "base", "expected_reward": 0})
        manifest = json.loads((ROOT / "tasks/vllm-implement-anthropic-rust-serving/validation/ci-cases.json").read_text())
        self.assertEqual(len(cases), 1 + len(manifest["cases"]))
        self.assertNotIn("oracle", [c["name"] for c in cases])
        with self.assertRaises(task_ci.ContractError):
            task_ci.task_validation_mode(Path("example"), {"validation_mode": "typo"})

    def test_image_audit_uses_manifest_without_metadata_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            task = Path(directory) / "example"
            (task / "environment").mkdir(parents=True)
            expected = "sha256:" + "a" * 64
            (task / "environment/image-manifest.json").write_text(json.dumps({"image_id": expected}))
            config = {"metadata": {"task_type": "bugfix"}, "environment": {"workdir": "/workspace/repo"}}
            for image_id, errors in ((expected, 0), ("sha256:" + "b" * 64, 1)):
                def fake_run(command, **kwargs):
                    stdout = json.dumps([{"Id": image_id}]) if command[1:3] == ["image", "inspect"] else ""
                    return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")
                audit = auditor.Audit()
                with patch.object(auditor.shutil, "which", return_value="docker"), patch.object(auditor, "run", side_effect=fake_run), redirect_stdout(io.StringIO()):
                    auditor.check_image(task, config, ROOT, "example-image", audit)
                self.assertEqual(audit.errors, errors)


if __name__ == "__main__":
    unittest.main()
