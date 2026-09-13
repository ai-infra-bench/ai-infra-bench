"""Exercise image routing through the real validation script without Docker/GPUs."""

import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


GITHUB_DIR = Path(__file__).resolve().parents[2]
REGISTRY = "ghcr.io/test-owner/ai-infra-bench-task-envs"
DIGEST = "sha256:" + "a" * 64

# Keep task discovery, hashing, case preparation, image checks and result parsing
# real. Replace only host hardware checks, GPU allocation, Docker and Harbor.
FAKE_COMMAND = r'''
import json
import os
from pathlib import Path
import sys
import tomllib

name, args = Path(sys.argv[0]).name, sys.argv[1:]
if name == "python3":
    if args[:2] == [".github/scripts/task_ci.py", "hardware-check"]:
        sys.exit(0)
    if args and Path(args[0]).name == "gpu_pool.py":
        name, args = "gpu_pool", args[1:]
    else:
        os.execv(sys.executable, [sys.executable, *args])

with open(os.environ["MOCK_LOG"], "a") as stream:
    stream.write(json.dumps([name, *args]) + "\n")

if name == "gpu_pool":
    command = args[args.index("--") + 1:]
    os.execvp(command[0], command)
elif name == "docker":
    ready = Path(os.environ["MOCK_IMAGE_READY"])
    if args[0] == "pull":
        if os.environ["MOCK_CACHE_HIT"] != "true":
            sys.exit(1)
        ready.touch()
    elif args[:2] == ["image", "inspect"]:
        if not ready.exists() and os.environ["MOCK_CACHE_HIT"] != "true":
            sys.exit(1)
        if "--format" in args:
            print(os.environ["MOCK_REGISTRY"] + "@" + os.environ["MOCK_DIGEST"])
        else:
            print(json.dumps([{"Id": "sha256:local-image"}]))
    elif args[:2] == ["buildx", "build"]:
        ready.touch()
    elif args[:3] == ["buildx", "imagetools", "inspect"]:
        print(json.dumps(os.environ["MOCK_DIGEST"]))
    elif args[0] not in ("push", "run"):
        raise AssertionError(args)
elif name == "harbor":
    task_dir = Path(args[args.index("--path") + 1])
    config = tomllib.loads((task_dir / "task.toml").read_text())
    with open(os.environ["MOCK_LOG"], "a") as stream:
        stream.write(json.dumps(["prepared_image", config["environment"]["docker_image"]]) + "\n")
    if os.environ["MOCK_HARBOR_FAIL"] == "true":
        sys.exit(1)
    job = Path(args[args.index("--jobs-dir") + 1]) / args[args.index("--job-name") + 1]
    job.mkdir(parents=True)
    reward = "0.0" if args[args.index("--agent") + 1] == "nop" else "1.0"
    (job / "result.json").write_text(json.dumps({"stats": {
        "n_completed_trials": 1, "n_errored_trials": 0,
        "evals": {"test": {"reward_stats": {"reward": {reward: ["trial"]}}}},
    }}))
else:
    raise AssertionError(name)
'''


class ValidationImageTests(unittest.TestCase):
    def run_validation(self, *, gpus, cache_hit, publish, harbor_fail=False, docker_image=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / ".github/scripts"
            scripts.mkdir(parents=True)
            for name in ("task_ci.py", "run_task_validation.sh"):
                shutil.copy2(GITHUB_DIR / "scripts" / name, scripts / name)
            shutil.copy2(GITHUB_DIR / "runner-classes.json", scripts.parent)
            task = root / "tasks/example"
            (task / "environment").mkdir(parents=True)
            (task / "environment/Dockerfile").write_text("FROM scratch\n")
            (task / "validation").mkdir()
            (task / "validation/ci-cases.json").write_text(json.dumps({
                "schema_version": "ai_infra_bench_validation_cases.v1", "cases": [],
            }))
            accelerator = "A100" if gpus else "CPU"
            config = f'[environment]\naccelerator = "{accelerator}"\nworkdir = "/workspace/repo"\n'
            if gpus and docker_image:
                config += f'docker_image = "sha256:local-canonical-image"\ngpus = {gpus}\ntopology = {gpus}\ngpu_types = ["A100"]\n'
            elif gpus:
                config += f'gpus = {gpus}\ntopology = {gpus}\ngpu_types = ["A100"]\n'
            (task / "task.toml").write_text(config)

            # Both PR and manual discovery must expose the accelerator used by
            # workflow conditions, independently of the approval environment.
            for mode in ("pr", "manual"):
                result = subprocess.run([
                    sys.executable, "-c",
                    "from pathlib import Path; import json, task_ci; "
                    f"print(json.dumps(task_ci.matrix_entry(Path('tasks/example'), '{mode}')))",
                ], cwd=root, env=dict(os.environ, PYTHONPATH=str(scripts)),
                    check=True, capture_output=True, text=True)
                self.assertEqual(json.loads(result.stdout)["accelerator"], accelerator)

            bin_dir = root / "bin"
            bin_dir.mkdir()
            for name in ("python3", "docker", "harbor"):
                executable = bin_dir / name
                executable.write_text(f"#!{sys.executable}\n" + textwrap.dedent(FAKE_COMMAND))
                executable.chmod(0o755)
            env = dict(os.environ)
            # GPU execution must also work outside GitHub without registry vars.
            for key in ("GHCR_REPOSITORY", "GITHUB_REPOSITORY_OWNER"):
                env.pop(key, None)
            env.update({
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "TASK_NAME": "example", "TARGET_PLATFORM": "linux/amd64",
                "PUBLISH_IMAGE": str(publish).lower(),
                "HARBOR_JOBS_DIR": str(root / "jobs"), "RUNNER_TEMP": str(root),
                "AI_INFRA_GPU_POOL_CONFIG": str(root / "pool.json"),
                "MOCK_LOG": str(root / "commands.jsonl"),
                "MOCK_IMAGE_READY": str(root / "image-ready"),
                "MOCK_CACHE_HIT": str(cache_hit).lower(),
                "MOCK_HARBOR_FAIL": str(harbor_fail).lower(),
                "MOCK_REGISTRY": REGISTRY, "MOCK_DIGEST": DIGEST,
            })
            if not gpus:
                env["GITHUB_REPOSITORY_OWNER"] = "test-owner"
            result = subprocess.run(
                ["bash", str(scripts / "run_task_validation.sh")],
                cwd=root, env=env, capture_output=True, text=True, timeout=20,
            )
            commands = [json.loads(line) for line in (root / "commands.jsonl").read_text().splitlines()]
            summary = root / "jobs/example/ci-summary.json"
            if harbor_fail:
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(summary.exists())
                return None, commands
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            summary = json.loads(summary.read_text())
            self.assertEqual(summary["cache_hit"], cache_hit if not gpus else False)
            builds = [cmd for cmd in commands if cmd[:3] == ["docker", "buildx", "build"]]
            self.assertEqual(len(builds), 1 if gpus else int(not cache_hit))
            if builds:
                self.assertEqual(builds[0][builds[0].index("--tag") + 1], summary["image"])
                self.assertIn("--load", builds[0])
            harbor = [cmd for cmd in commands if cmd[0] == "harbor"]
            self.assertEqual(len(harbor), 2)
            expected_env = "ci_gpu_docker:LeasedGpuDockerEnvironment" if gpus else "docker"
            self.assertTrue(all(cmd[cmd.index("--env") + 1] == expected_env for cmd in harbor))
            self.assertEqual(sum(cmd[0] == "gpu_pool" for cmd in commands), 2 if gpus else 0)
            return summary, commands

    def test_gpu_uses_local_images_even_when_publication_is_requested(self):
        for gpus, cache_hit, publish in itertools.product((1, 2, 4), (False, True), (False, True)):
            with self.subTest(gpus=gpus, cache_hit=cache_hit, publish=publish):
                summary, commands = self.run_validation(gpus=gpus, cache_hit=cache_hit, publish=publish)
                expected_image = f"ai-infra-bench-task-envs:example-{summary['environment_key']}"
                self.assertEqual(summary["image"], expected_image)
                self.assertFalse(summary["published"])
                self.assertEqual(summary["registry_digest"], "")
                self.assertFalse(any(cmd[:2] in (["docker", "pull"], ["docker", "push"]) for cmd in commands))
                self.assertFalse(any(cmd[:3] == ["docker", "buildx", "imagetools"] for cmd in commands))
                self.assertNotIn("ghcr.io", json.dumps(commands))
                # The single inspect is the mandatory post-build image check;
                # there must be no pre-build cache lookup for GPU images.
                self.assertEqual(sum(cmd[:3] == ["docker", "image", "inspect"] for cmd in commands), 1)
                self.assertEqual([cmd[1] for cmd in commands if cmd[0] == "prepared_image"], [summary["image"]] * 2)

    def test_cpu_retains_registry_cache_and_publication(self):
        for cache_hit, publish in itertools.product((False, True), repeat=2):
            with self.subTest(cache_hit=cache_hit, publish=publish):
                summary, commands = self.run_validation(gpus=0, cache_hit=cache_hit, publish=publish)
                image = f"{REGISTRY}:example-{summary['environment_key']}"
                self.assertEqual(summary["image"], image)
                self.assertIn(["docker", "pull", image], commands)
                should_publish = publish and not cache_hit
                self.assertEqual(summary["published"], should_publish)
                self.assertEqual(["docker", "push", image] in commands, should_publish)
                self.assertEqual(summary["registry_digest"], DIGEST if cache_hit or should_publish else "")
                runtime_image = f"{REGISTRY}@{DIGEST}" if cache_hit else image
                self.assertEqual([cmd[1] for cmd in commands if cmd[0] == "prepared_image"], [runtime_image] * 2)

    def test_failed_validation_never_publishes(self):
        for gpus in (0, 1):
            with self.subTest(gpus=gpus):
                _, commands = self.run_validation(gpus=gpus, cache_hit=False, publish=True, harbor_fail=True)
                self.assertFalse(any(cmd[:2] == ["docker", "push"] for cmd in commands))

    def test_gpu_without_canonical_image_builds_locally(self):
        summary, commands = self.run_validation(
            gpus=2, cache_hit=False, publish=False, docker_image=False,
        )
        self.assertTrue(summary["image"].startswith("ai-infra-bench-task-envs:example-"))
        self.assertEqual(len([cmd for cmd in commands if cmd[:3] == ["docker", "buildx", "build"]]), 1)
        self.assertFalse(any(cmd[:2] == ["docker", "pull"] for cmd in commands))


if __name__ == "__main__":
    unittest.main()
