#!/usr/bin/env python3
"""Trusted helpers for ai-infra-bench task CI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = REPO_ROOT / "tasks"
RUNNER_CLASSES_PATH = REPO_ROOT / ".github" / "runner-classes.json"
ENV_HASH_EXCLUDES = {"image-manifest.json", ".DS_Store"}


class ContractError(ValueError):
    pass


def run(*args: str, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )


def load_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text())


def load_runner_classes() -> dict[str, Any]:
    data = json.loads(RUNNER_CLASSES_PATH.read_text())
    if data.get("schema_version") != "ai_infra_bench_runner_classes.v1":
        raise ContractError("unsupported runner class schema")
    accelerators = data.get("accelerators")
    if not isinstance(accelerators, dict) or not accelerators:
        raise ContractError("runner class file has no accelerators")
    return accelerators


def task_dirs() -> list[Path]:
    return sorted(
        path for path in TASKS_DIR.iterdir() if path.is_dir() and (path / "task.toml").is_file()
    )


def task_contract(task_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = load_toml(task_dir / "task.toml")
    environment = config.get("environment", {})
    accelerator = environment.get("accelerator")
    classes = load_runner_classes()
    if accelerator not in classes:
        raise ContractError(
            f"{task_dir.name}: unsupported accelerator {accelerator!r}; "
            f"allowed values are {sorted(classes)}"
        )
    runner = classes[accelerator]
    task_gpus = environment.get("gpus", 0) or 0
    workdir = environment.get("workdir")
    if (
        not isinstance(workdir, str)
        or not Path(workdir).is_absolute()
        or any(character in workdir for character in "\r\n\0")
    ):
        raise ContractError(f"{task_dir.name}: [environment].workdir must be absolute")

    if accelerator == "CPU":
        if "topology" in environment:
            raise ContractError(f"{task_dir.name}: CPU tasks must not set topology")
        if task_gpus != 0:
            raise ContractError(f"{task_dir.name}: CPU task requests {task_gpus} GPUs")
    else:
        topology = environment.get("topology")
        allowed = runner.get("allowed_topologies", [])
        if not isinstance(topology, int) or topology not in allowed:
            raise ContractError(
                f"{task_dir.name}: {accelerator} topology must be one of {allowed}"
            )
        if task_gpus != topology:
            raise ContractError(
                f"{task_dir.name}: [environment].gpus={task_gpus} "
                f"does not match topology={topology}"
            )
        gpu_types = environment.get("gpu_types") or []
        if not any(accelerator.lower() in str(item).lower() for item in gpu_types):
            raise ContractError(
                f"{task_dir.name}: [environment].gpu_types must name {accelerator}"
            )

    labels = runner.get("github_labels")
    if not isinstance(labels, list) or not labels or not all(
        isinstance(item, str) and item for item in labels
    ):
        raise ContractError(f"{task_dir.name}: invalid trusted runner labels")
    if not isinstance(runner.get("platform"), str):
        raise ContractError(f"{task_dir.name}: runner platform is missing")
    return config, runner


def validation_manifest(task_dir: Path) -> dict[str, Any]:
    manifest_path = task_dir / "validation" / "ci-cases.json"
    if not manifest_path.is_file():
        raise ContractError(f"{task_dir.name}: missing validation/ci-cases.json")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != "ai_infra_bench_validation_cases.v1":
        raise ContractError(f"{task_dir.name}: unsupported validation case schema")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise ContractError(f"{task_dir.name}: validation cases must be a list")

    declared: set[str] = set()
    names: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ContractError(f"{task_dir.name}: invalid validation case")
        name = case.get("name")
        patch_name = case.get("patch")
        if not isinstance(name, str) or not name or name in names:
            raise ContractError(f"{task_dir.name}: duplicate or invalid case name {name!r}")
        if (
            not isinstance(patch_name, str)
            or Path(patch_name).name != patch_name
            or not patch_name.endswith(".patch")
            or patch_name in declared
        ):
            raise ContractError(f"{task_dir.name}: invalid patch path {patch_name!r}")
        if case.get("expected_reward") not in (0, 1):
            raise ContractError(f"{task_dir.name}/{name}: expected_reward must be 0 or 1")
        patch_path = task_dir / "validation" / patch_name
        if not patch_path.is_file():
            raise ContractError(f"{task_dir.name}/{name}: patch is missing")
        digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()
        if digest != case.get("patch_sha256"):
            raise ContractError(f"{task_dir.name}/{name}: patch SHA-256 mismatch")
        names.add(name)
        declared.add(patch_name)

    actual = {path.name for path in (task_dir / "validation").glob("*.patch")}
    if declared != actual:
        missing = sorted(actual - declared)
        stale = sorted(declared - actual)
        raise ContractError(
            f"{task_dir.name}: validation manifest mismatch; "
            f"missing={missing}, stale={stale}"
        )
    return manifest


def task_validation_mode(task_dir: Path, config: dict[str, Any]) -> str:
    validation_mode = config.get("metadata", {}).get("validation_mode", "oracle")
    if validation_mode not in ("oracle", "verifier_only"):
        raise ContractError(
            f"{task_dir.name}: unsupported metadata.validation_mode "
            f"{validation_mode!r}"
        )
    return validation_mode


def validate_task(task_dir: Path) -> None:
    config, _ = task_contract(task_dir)
    task_validation_mode(task_dir, config)
    validation_manifest(task_dir)


def changed_tasks(base: str, head: str) -> list[Path]:
    changed = run("git", "diff", "--name-only", base, head).stdout.splitlines()
    selected: set[str] = set()
    for raw in changed:
        path = raw.strip("/")
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] == "tasks":
            selected.add(parts[1])

    for name in sorted(selected):
        base_task = subprocess.run(
            ["git", "cat-file", "-e", f"{base}:tasks/{name}/task.toml"],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
        head_task = subprocess.run(
            ["git", "cat-file", "-e", f"{head}:tasks/{name}/task.toml"],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
        if base_task and not head_task:
            raise ContractError(
                f"{name}: task deletion requires a separate approved removal process"
            )

    return [
        TASKS_DIR / name
        for name in sorted(selected)
        if (TASKS_DIR / name / "task.toml").is_file()
    ]


def matrix_entry(task_dir: Path, mode: str) -> dict[str, Any]:
    config, runner = task_contract(task_dir)
    validation_manifest(task_dir)
    if mode == "manual":
        approval_environment = "manual-task-validation"
    elif config["environment"]["accelerator"] == "CPU":
        approval_environment = "automatic-task-validation"
    else:
        approval_environment = "task-validation"
    return {
        "task": task_dir.name,
        "runs_on": runner["github_labels"],
        "platform": runner["platform"],
        "approval_environment": approval_environment,
    }


def command_discover(args: argparse.Namespace) -> None:
    if args.mode == "pr":
        if not args.base or not args.head:
            raise ContractError("PR discovery requires --base and --head")
        selected = changed_tasks(args.base, args.head)
        mode = "pr"
    else:
        requested = [item.strip() for item in args.tasks.split(",") if item.strip()]
        if not requested or requested == ["all"]:
            selected = task_dirs()
        else:
            selected = [TASKS_DIR / item for item in requested]
            missing = [path.name for path in selected if not (path / "task.toml").is_file()]
            if missing:
                raise ContractError(f"unknown tasks: {missing}")
        mode = "manual"

    entries = [matrix_entry(path, mode) for path in selected]
    print(json.dumps(entries, separators=(",", ":")))


def environment_key(task_dir: Path, target_platform: str) -> str:
    environment = task_dir / "environment"
    if not environment.is_dir():
        raise ContractError(f"{task_dir.name}: environment directory is missing")
    digest = hashlib.sha256()
    digest.update(b"ai-infra-bench-environment-v2\0")
    digest.update(target_platform.encode())
    digest.update(b"\0")

    entries = []
    for path in environment.rglob("*"):
        rel = path.relative_to(environment)
        if (
            path.name in ENV_HASH_EXCLUDES
            or "__pycache__" in rel.parts
            or any(part.startswith(".") and part != ".dockerignore" for part in rel.parts)
        ):
            continue
        entries.append((rel.as_posix(), path))
    for rel, path in sorted(entries):
        metadata = path.lstat()
        digest.update(rel.encode())
        digest.update(b"\0")
        digest.update(f"{stat.S_IMODE(metadata.st_mode):04o}".encode())
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.readlink(path).encode())
        elif path.is_file():
            digest.update(b"file\0")
            digest.update(path.read_bytes())
        elif path.is_dir():
            digest.update(b"directory\0")
        else:
            raise ContractError(f"{task_dir.name}: unsupported environment entry {rel}")
        digest.update(b"\0")
    return digest.hexdigest()


def command_env_key(args: argparse.Namespace) -> None:
    task_dir = TASKS_DIR / args.task
    validate_task(task_dir)
    print(environment_key(task_dir, args.platform))


def inject_docker_image(task_file: Path, image: str) -> None:
    lines = task_file.read_text().splitlines()
    output: list[str] = []
    in_environment = False
    found_environment = False
    inserted = False
    for line in lines:
        if re.fullmatch(r"\[environment\]", line.strip()):
            in_environment = True
            found_environment = True
            output.append(line)
            output.append(f'docker_image = "{image}"')
            inserted = True
            continue
        if line.startswith("[") and line.endswith("]"):
            in_environment = False
        if in_environment and re.match(r"\s*docker_image\s*=", line):
            continue
        output.append(line)
    if not found_environment or not inserted:
        raise ContractError(f"{task_file}: missing [environment] section")
    task_file.write_text("\n".join(output) + "\n")


def prepare_case(task_dir: Path, image: str, case_name: str, output: Path) -> str:
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(task_dir, output)
    inject_docker_image(output / "task.toml", image)

    if case_name == "base":
        return "nop"
    if case_name == "oracle":
        return "oracle"

    manifest = validation_manifest(task_dir)
    case = next((item for item in manifest["cases"] if item["name"] == case_name), None)
    if case is None:
        raise ContractError(f"{task_dir.name}: unknown validation case {case_name}")

    solution = output / "solution"
    patch_source = task_dir / "validation" / case["patch"]
    shutil.rmtree(solution, ignore_errors=True)
    solution.mkdir()
    shutil.copy2(patch_source, solution / "ci-case.patch")

    script = ["#!/usr/bin/env bash", "set -euo pipefail"]
    script.extend(
        [
            "git apply --check /solution/ci-case.patch",
            "git apply /solution/ci-case.patch",
        ]
    )
    solve = solution / "solve.sh"
    solve.write_text("\n".join(script) + "\n")
    solve.chmod(0o755)
    return "oracle"


def command_prepare_case(args: argparse.Namespace) -> None:
    task_dir = TASKS_DIR / args.task
    validate_task(task_dir)
    agent = prepare_case(task_dir, args.image, args.case, Path(args.output))
    print(agent)


def result_reward(result_path: Path) -> tuple[int, int, list[float]]:
    result = json.loads(result_path.read_text())
    stats = result.get("stats", {})
    completed = stats.get("n_completed_trials")
    errored = stats.get("n_errored_trials")
    rewards: list[float] = []
    for evaluation in stats.get("evals", {}).values():
        for metric in evaluation.get("metrics", []):
            if "reward" in metric:
                rewards.append(float(metric["reward"]))
            elif evaluation.get("n_trials") == 1 and "mean" in metric:
                rewards.append(float(metric["mean"]))
        if rewards:
            continue
        reward_stats = evaluation.get("reward_stats", {}).get("reward", {})
        for reward, trials in reward_stats.items():
            rewards.extend(float(reward) for _ in trials)
    return completed, errored, rewards


def command_check_result(args: argparse.Namespace) -> None:
    completed, errored, rewards = result_reward(Path(args.result))
    expected = float(args.expected_reward)
    if completed != 1 or errored != 0 or rewards != [expected]:
        raise ContractError(
            f"unexpected Harbor result: completed={completed}, errored={errored}, "
            f"rewards={rewards}, expected={[expected]}"
        )
    print(json.dumps({"completed": completed, "errored": errored, "rewards": rewards}))


def command_hardware_check(args: argparse.Namespace) -> None:
    task_dir = TASKS_DIR / args.task
    config, _ = task_contract(task_dir)
    environment = config["environment"]
    machine = platform.machine().lower()
    if machine not in ("x86_64", "amd64"):
        raise ContractError(f"{task_dir.name}: runner architecture is {machine}, expected x64")
    if environment["accelerator"] == "CPU":
        print(json.dumps({"architecture": machine, "accelerator": "CPU"}))
        return

    query = subprocess.run(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()
    required = environment["topology"]
    matching = [
        name for name in query if environment["accelerator"].lower() in name.lower()
    ]
    if len(matching) < required:
        raise ContractError(
            f"{task_dir.name}: requires {required} {environment['accelerator']} GPUs, "
            f"found {matching}"
        )
    print(
        json.dumps(
            {
                "architecture": machine,
                "accelerator": environment["accelerator"],
                "topology": required,
                "visible_gpus": query,
            }
        )
    )


def command_cases(args: argparse.Namespace) -> None:
    task_dir = TASKS_DIR / args.task
    config, _ = task_contract(task_dir)
    validation_mode = task_validation_mode(task_dir, config)
    manifest = validation_manifest(task_dir)
    cases = [{"name": "base", "expected_reward": 0}]
    if validation_mode == "oracle":
        cases.append({"name": "oracle", "expected_reward": 1})
    cases.extend(
        {"name": item["name"], "expected_reward": item["expected_reward"]}
        for item in manifest["cases"]
    )
    print(json.dumps(cases, separators=(",", ":")))


def command_image_check(args: argparse.Namespace) -> None:
    task_dir = TASKS_DIR / args.task
    config, _ = task_contract(task_dir)
    inspect = json.loads(
        subprocess.run(
            ["docker", "image", "inspect", args.image],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout
    )[0]
    expected_head = config.get("metadata", {}).get("base_commit")
    workdir = config["environment"]["workdir"]
    audit_script = f"""
set -euo pipefail
for path in /tests /solution /validation; do
  test ! -e "$path"
done
cd {shlex.quote(workdir)}
test "$(git rev-parse HEAD)" = {shlex.quote(str(expected_head))}
test -z "$(git remote)"
test -z "$(git rev-list --all --not {shlex.quote(str(expected_head))})"
test ! -e .git/logs
test -z "$(git status --porcelain)"
test -z "$(git fsck --full --no-reflogs --unreachable --no-progress 2>/dev/null)"
"""
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network=none",
            args.image,
            "bash",
            "-lc",
            audit_script,
        ],
        check=True,
    )

    print(
        json.dumps(
            {
                "image": args.image,
                "image_id": inspect.get("Id"),
                "base_commit": expected_head,
            }
        )
    )


def command_validate(args: argparse.Namespace) -> None:
    targets = task_dirs() if not args.tasks else [TASKS_DIR / item for item in args.tasks]
    for target in targets:
        validate_task(target)
        print(f"OK {target.name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover")
    discover.add_argument("--mode", choices=("manual", "pr"), required=True)
    discover.add_argument("--base")
    discover.add_argument("--head")
    discover.add_argument("--tasks", default="all")
    discover.set_defaults(func=command_discover)

    env_key = subparsers.add_parser("env-key")
    env_key.add_argument("--task", required=True)
    env_key.add_argument("--platform", required=True)
    env_key.set_defaults(func=command_env_key)

    prepare = subparsers.add_parser("prepare-case")
    prepare.add_argument("--task", required=True)
    prepare.add_argument("--image", required=True)
    prepare.add_argument("--case", required=True)
    prepare.add_argument("--output", required=True)
    prepare.set_defaults(func=command_prepare_case)

    check = subparsers.add_parser("check-result")
    check.add_argument("--result", required=True)
    check.add_argument("--expected-reward", type=int, choices=(0, 1), required=True)
    check.set_defaults(func=command_check_result)

    hardware = subparsers.add_parser("hardware-check")
    hardware.add_argument("--task", required=True)
    hardware.set_defaults(func=command_hardware_check)

    cases = subparsers.add_parser("cases")
    cases.add_argument("--task", required=True)
    cases.set_defaults(func=command_cases)

    image_check = subparsers.add_parser("image-check")
    image_check.add_argument("--task", required=True)
    image_check.add_argument("--image", required=True)
    image_check.set_defaults(func=command_image_check)

    validate = subparsers.add_parser("validate")
    validate.add_argument("tasks", nargs="*")
    validate.set_defaults(func=command_validate)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (ContractError, FileNotFoundError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
