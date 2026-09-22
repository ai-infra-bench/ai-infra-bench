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
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))
from normalize_image_manifests import check_file_hashes

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


def gpu_type_matches(actual: str, requested: str) -> bool:
    """Match a family or model, including A100-40GB against A100-SXM4-40GB."""
    actual_parts = set(re.findall(r"[a-z0-9]+", actual.lower())) - {"nvidia"}
    requested_parts = set(re.findall(r"[a-z0-9]+", requested.lower())) - {"nvidia"}
    return bool(requested_parts) and requested_parts <= actual_parts


def task_contract(task_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = load_toml(task_dir / "task.toml")
    environment = config.get("environment", {})
    legacy = {"accelerator", "topology"}.intersection(environment)
    if legacy or "environment_profile" in config.get("metadata", {}):
        raise ContractError(
            f"{task_dir.name}: use [environment].gpus and gpu_types instead of "
            "accelerator, topology, or metadata.environment_profile"
        )
    task_gpus = environment.get("gpus", 0)
    if type(task_gpus) is not int or task_gpus < 0:
        raise ContractError(f"{task_dir.name}: [environment].gpus must be a nonnegative integer")
    gpu_types = environment.get("gpu_types", [])
    if not isinstance(gpu_types, list) or not all(
        isinstance(item, str) and item.strip() for item in gpu_types
    ):
        raise ContractError(f"{task_dir.name}: [environment].gpu_types must be a list of non-empty strings")
    if environment.get("tpu") is not None:
        raise ContractError(f"{task_dir.name}: the CI runners do not support TPU tasks")
    classes = load_runner_classes()
    if task_gpus == 0:
        if gpu_types:
            raise ContractError(f"{task_dir.name}: gpu_types requires a positive gpus count")
        runner = classes["CPU"]
    else:
        candidates = [
            candidate for candidate in classes.values()
            if task_gpus in candidate.get("allowed_gpu_counts", [])
            and candidate.get("gpu_types")
            and (
                not gpu_types
                or any(
                    gpu_type_matches(requested, supported)
                    for requested in gpu_types for supported in candidate["gpu_types"]
                )
            )
        ]
        if not candidates:
            raise ContractError(
                f"{task_dir.name}: no CI runner supports gpus={task_gpus}, "
                f"gpu_types={gpu_types}; check .github/runner-classes.json"
            )
        runner = candidates[0]
    workdir = environment.get("workdir")
    if (
        not isinstance(workdir, str)
        or not Path(workdir).is_absolute()
        or any(character in workdir for character in "\r\n\0")
    ):
        raise ContractError(f"{task_dir.name}: [environment].workdir must be absolute")

    labels = runner.get("github_labels")
    if not isinstance(labels, list) or not labels or not all(
        isinstance(item, str) and item for item in labels
    ):
        raise ContractError(f"{task_dir.name}: invalid trusted runner labels")
    if not isinstance(runner.get("platform"), str):
        raise ContractError(f"{task_dir.name}: runner platform is missing")
    data_proxy_url = runner.get("data_proxy_url", "")
    proxy_is_valid = isinstance(data_proxy_url, str)
    if proxy_is_valid:
        try:
            parsed_proxy = urlsplit(data_proxy_url)
            proxy_is_valid = (
                not data_proxy_url
                or (
                    parsed_proxy.scheme == "http"
                    and parsed_proxy.hostname == "127.0.0.1"
                    and parsed_proxy.port is not None
                    and parsed_proxy.username is None
                    and parsed_proxy.password is None
                    and not parsed_proxy.path
                    and not parsed_proxy.query
                    and not parsed_proxy.fragment
                )
            )
        except ValueError:
            proxy_is_valid = False
    if not proxy_is_valid:
        raise ContractError(
            f"{task_dir.name}: runner data_proxy_url must be an uncredentialed "
            "loopback HTTP URL"
        )
    return config, runner


def validation_manifest(task_dir: Path) -> dict[str, Any]:
    manifest_path = task_dir / "validation" / "ci-cases.json"
    if not manifest_path.is_file():
        raise ContractError(f"{task_dir.name}: missing validation/ci-cases.json")
    manifest = json.loads(manifest_path.read_text())
    schema = manifest.get("schema_version")
    if schema not in {"ai_infra_bench_validation_cases.v1", "ai_infra_bench_validation_cases.v2"}:
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
        patch_parts = Path(patch_name).parts if isinstance(patch_name, str) else ()
        expected_parts = 2 if schema.endswith(".v2") else 1
        if (
            not isinstance(patch_name, str)
            or len(patch_parts) != expected_parts
            or (expected_parts == 2 and patch_parts[0] != "patches")
            or "\\" in patch_name
            or Path(patch_name).as_posix() != patch_name
            or not patch_name.endswith(".patch")
            or patch_name in declared
        ):
            raise ContractError(f"{task_dir.name}: invalid patch path {patch_name!r}")
        if case.get("expected_reward") not in (0, 1):
            raise ContractError(f"{task_dir.name}/{name}: expected_reward must be 0 or 1")
        apply_after = case.get("apply_after", "base")
        if apply_after not in ("base", "oracle"):
            raise ContractError(
                f"{task_dir.name}/{name}: apply_after must be base or oracle"
            )
        patch_path = task_dir / "validation" / patch_name
        if patch_path.is_symlink() or patch_path.parent.is_symlink() or not patch_path.is_file():
            raise ContractError(f"{task_dir.name}/{name}: patch is missing")
        digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()
        if digest != case.get("patch_sha256"):
            raise ContractError(f"{task_dir.name}/{name}: patch SHA-256 mismatch")
        names.add(name)
        declared.add(patch_name)

    patch_dir = task_dir / "validation"
    if schema.endswith(".v2"):
        patch_dir /= "patches"
    actual = {
        path.relative_to(task_dir / "validation").as_posix()
        for path in patch_dir.glob("*.patch")
    }
    if declared != actual:
        missing = sorted(actual - declared)
        stale = sorted(declared - actual)
        raise ContractError(
            f"{task_dir.name}: validation manifest mismatch; "
            f"missing={missing}, stale={stale}"
        )
    reviewed_replay_config(task_dir, manifest)
    return manifest


def inline_replay_bytes(reference: Any) -> bytes:
    """Serialize curator JSON inputs without a separate file for each case."""
    if (not isinstance(reference, dict) or set(reference) != {"content", "sha256"}
            or not isinstance(reference["content"], dict) or not reference["content"]):
        raise ContractError("Inline replay inputs require nonempty JSON content and sha256")
    content = (json.dumps(reference["content"], indent=2) + "\n").encode()
    if hashlib.sha256(content).hexdigest() != reference["sha256"]:
        raise ContractError("Changed inline reviewed replay input")
    return content


def reviewed_replay_config(task_dir: Path, manifest: dict[str, Any]) -> dict[str, Any] | None:
    """Validate curator-owned replay inputs; never infer an adapter from a solver."""
    if "reviewed_replay" not in manifest:
        return None
    config = manifest["reviewed_replay"]
    if not isinstance(config, dict) or set(config) != {"runner", "cases"}:
        raise ContractError(f"{task_dir.name}: invalid reviewed_replay declaration")
    if load_toml(task_dir / "task.toml").get("environment", {}).get("gpus", 0):
        raise ContractError("Reviewed replay CI supports CPU tasks only; GPU lease integration is required")

    def checked_file(reference: Any) -> Path:
        if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
            raise ContractError("reviewed replay inputs require explicit path and sha256")
        name = reference["path"]
        parts = Path(name).parts if isinstance(name, str) else ()
        if (not isinstance(name, str) or len(parts) < 2 or parts[0] != "tools"
                or ".." in parts or "\\" in name or Path(name).as_posix() != name):
            raise ContractError(f"Unsafe reviewed replay input path: {name!r}")
        path = task_dir / "validation"
        if path.is_symlink():
            raise ContractError("Reviewed replay validation directory must not be a symlink")
        for part in parts:
            path /= part
            if path.is_symlink():
                raise ContractError(f"Reviewed replay input must not be a symlink: {name}")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]:
            raise ContractError(f"Missing or changed reviewed replay input: {name}")
        return path

    checked_file(config["runner"])
    expected = {"base", *(case["name"] for case in manifest["cases"])}
    if task_validation_mode(task_dir, manifest) == "oracle":
        expected.add("oracle")
    if not isinstance(config["cases"], dict) or set(config["cases"]) != expected:
        raise ContractError("Reviewed replay profiles must exactly cover all declared CI cases")
    for name, inputs in config["cases"].items():
        if not isinstance(inputs, dict) or set(inputs) != {"binding", "scenario", "review_evidence"}:
            raise ContractError(f"{name}: explicit binding, scenario and review_evidence required")
        content = {}
        for role, reference in inputs.items():
            if role != "binding" and isinstance(reference, dict) and "content" in reference:
                content[role] = inline_replay_bytes(reference)
            else:
                content[role] = checked_file(reference).read_bytes()
        evidence = json.loads(content["review_evidence"])
        if not isinstance(evidence, dict) or not evidence:
            raise ContractError(f"{name}: reviewed replay evidence must be a nonempty object")
    return config


def task_validation_mode(task_dir: Path, manifest: dict[str, Any]) -> str:
    validation_mode = manifest.get("validation_mode", "oracle")
    if validation_mode not in ("oracle", "verifier_only"):
        raise ContractError(
            f"{task_dir.name}: unsupported validation/ci-cases.json validation_mode "
            f"{validation_mode!r}"
        )
    return validation_mode


def validate_task(task_dir: Path) -> None:
    task_contract(task_dir)
    manifest = validation_manifest(task_dir)
    task_validation_mode(task_dir, manifest)
    environment = task_dir / "environment"
    try:
        image_manifest = json.loads((environment / "image-manifest.json").read_text())
        check_file_hashes(image_manifest, environment)
    except (OSError, ValueError) as exc:
        raise ContractError(f"{task_dir.name}: invalid image manifest: {exc}") from exc


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
    gpus = config["environment"].get("gpus", 0)
    if mode == "manual":
        approval_environment = "manual-task-validation"
    elif gpus == 0:
        approval_environment = "automatic-task-validation"
    else:
        approval_environment = "task-validation"
    return {
        "task": task_dir.name,
        "gpus": gpus,
        "gpu_types": config["environment"].get("gpu_types", []),
        "runs_on": runner["github_labels"],
        "platform": runner["platform"],
        "data_proxy_url": runner.get("data_proxy_url", ""),
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
    # Shared verifiers already see the candidate checkout. Separate verifiers
    # receive their candidate inputs through artifacts, so preserve that transfer.
    task_file = output / "task.toml"
    text = task_file.read_text()
    expected = tomllib.loads(text)
    if expected.get("artifacts") and expected.get("verifier", {}).get("environment_mode") != "separate":
        expected["artifacts"] = []
        updated = re.sub(r"(?m)^artifacts[ \t]*=.*$", "artifacts = []", text, count=1)
        if tomllib.loads(updated) != expected:
            raise ContractError(f"{task_file}: expected a normalized root artifacts field")
        task_file.write_text(updated)

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
    apply_after = case.get("apply_after", "base")
    shutil.rmtree(solution, ignore_errors=True)
    solution.mkdir()

    script = ["#!/usr/bin/env bash", "set -euo pipefail"]
    if apply_after == "oracle":
        # The Golden Oracle solve.sh may reference its sibling files with
        # absolute paths rooted at /solution (e.g. `git apply /solution/fix.patch`).
        # We therefore keep the Oracle solution flat at the /solution root rather
        # than nesting it under /solution/oracle, rename its entrypoint to
        # oracle-solve.sh, and drive it from a generated wrapper. Nesting would
        # break those absolute paths and silently apply nothing (agent exits 128,
        # verifier sees base state) — a HARNESS_INVALID result, not a real signal.
        oracle_src = task_dir / "solution"
        # Fail-closed on any name that our wrapper reserves: the generated
        # wrapper (solve.sh), the renamed Oracle entrypoint (oracle-solve.sh),
        # and the control patch (ci-case.patch) must not already exist in the
        # Oracle solution, or the flat copy would clobber / be clobbered.
        reserved = {"solve.sh", "oracle-solve.sh", "ci-case.patch"}
        conflicts = sorted(
            child.name
            for child in oracle_src.iterdir()
            if child.name in (reserved - {"solve.sh"})
        )
        if conflicts:
            raise ContractError(
                f"{task_dir.name}: Oracle solution contains reserved name(s) "
                f"{conflicts} that collide with prepared apply_after=oracle layout"
            )
        oracle_entry = oracle_src / "solve.sh"
        if not oracle_entry.is_file():
            raise ContractError(
                f"{task_dir.name}: Oracle solution has no solve.sh entrypoint"
            )
        for child in oracle_src.iterdir():
            dest_name = "oracle-solve.sh" if child.name == "solve.sh" else child.name
            dest = solution / dest_name
            if child.is_dir():
                shutil.copytree(child, dest)
            else:
                shutil.copy2(child, dest)
        (solution / "oracle-solve.sh").chmod(0o755)
        script.append("bash /solution/oracle-solve.sh")

    shutil.copy2(patch_source, solution / "ci-case.patch")
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
    """Parse Harbor result.json and extract trial counts + per-trial rewards.

    Harbor 0.22.0+ schema (preferred):
        stats.evals[*].reward_stats.reward: dict[str, list[str]]
            reward value -> trial ID list mapping

    Legacy schema (fallback, only if reward_stats completely absent):
        stats.evals[*].metrics[*].reward: float (single reward per eval)

    Fail-closed on any structural anomaly, non-numeric reward, duplicate trial
    ID, or mismatch between reward_stats trial count and n_completed_trials.
    """
    result = json.loads(result_path.read_text())
    stats = result.get("stats", {})

    completed = stats.get("n_completed_trials")
    errored = stats.get("n_errored_trials")
    if not isinstance(completed, int) or not isinstance(errored, int):
        raise ContractError(
            f"result_reward: n_completed_trials={completed!r} or "
            f"n_errored_trials={errored!r} is not an integer"
        )

    evals = stats.get("evals", {})
    if not isinstance(evals, dict):
        raise ContractError(f"result_reward: stats.evals is not a dict: {type(evals)}")

    has_reward_stats = any(
        isinstance(ev, dict) and isinstance(ev.get("reward_stats"), dict)
        for ev in evals.values()
    )

    rewards: list[float] = []
    seen_trial_ids: set[str] = set()

    if has_reward_stats:
        for eval_name, evaluation in evals.items():
            if not isinstance(evaluation, dict):
                raise ContractError(
                    f"result_reward: evals[{eval_name!r}] is not a dict: "
                    f"{type(evaluation)}"
                )
            reward_stats = evaluation.get("reward_stats")
            if not isinstance(reward_stats, dict):
                raise ContractError(
                    f"result_reward: evals[{eval_name!r}].reward_stats is not a "
                    f"dict: {type(reward_stats)}"
                )
            reward_map = reward_stats.get("reward")
            if not isinstance(reward_map, dict):
                raise ContractError(
                    f"result_reward: evals[{eval_name!r}].reward_stats.reward is "
                    f"not a dict: {type(reward_map)}"
                )
            for reward_str, trial_ids in reward_map.items():
                try:
                    reward_value = float(reward_str)
                except (ValueError, TypeError) as exc:
                    raise ContractError(
                        f"result_reward: evals[{eval_name!r}].reward_stats.reward "
                        f"key {reward_str!r} is not a valid float: {exc}"
                    )
                if not isinstance(trial_ids, list):
                    raise ContractError(
                        f"result_reward: evals[{eval_name!r}].reward_stats."
                        f"reward[{reward_str!r}] is not a list: {type(trial_ids)}"
                    )
                for trial_id in trial_ids:
                    if not isinstance(trial_id, str):
                        raise ContractError(
                            f"result_reward: trial ID {trial_id!r} in "
                            f"evals[{eval_name!r}].reward_stats.reward"
                            f"[{reward_str!r}] is not a string"
                        )
                    if trial_id in seen_trial_ids:
                        raise ContractError(
                            f"result_reward: duplicate trial ID {trial_id!r} in "
                            f"reward_stats"
                        )
                    seen_trial_ids.add(trial_id)
                    rewards.append(reward_value)
        if len(rewards) != completed:
            raise ContractError(
                f"result_reward: reward_stats reports {len(rewards)} trials, but "
                f"n_completed_trials={completed}"
            )
    else:
        for eval_name, evaluation in evals.items():
            if not isinstance(evaluation, dict):
                raise ContractError(
                    f"result_reward: evals[{eval_name!r}] is not a dict: "
                    f"{type(evaluation)}"
                )
            metrics = evaluation.get("metrics", [])
            if not isinstance(metrics, list):
                raise ContractError(
                    f"result_reward: evals[{eval_name!r}].metrics is not a list: "
                    f"{type(metrics)}"
                )
            for metric in metrics:
                if not isinstance(metric, dict):
                    raise ContractError(
                        f"result_reward: metric in evals[{eval_name!r}].metrics is "
                        f"not a dict: {type(metric)}"
                    )
                if "reward" in metric:
                    reward_value = metric["reward"]
                    if not isinstance(reward_value, (int, float)):
                        raise ContractError(
                            f"result_reward: evals[{eval_name!r}].metrics[*].reward "
                            f"is not numeric: {reward_value!r}"
                        )
                    rewards.append(float(reward_value))

    return completed, errored, rewards


def print_verifier_failure_logs(job_dir: Path) -> None:
    root = job_dir.resolve()
    logs = [path for path in sorted(job_dir.glob("*/verifier/test-stdout.txt"))
            if not path.is_symlink() and path.resolve().is_relative_to(root)]
    if not logs:
        return
    # Verifier output is diagnostic text, never GitHub Actions commands.
    token = uuid.uuid4().hex if os.environ.get("GITHUB_ACTIONS") == "true" else None
    if token:
        print(f"::stop-commands::{token}")
    try:
        for path in logs:
            print(f"Verifier output (last 64 KiB): {path.relative_to(job_dir)}")
            try:
                with path.open("rb") as stream:
                    stream.seek(0, os.SEEK_END)
                    stream.seek(max(0, stream.tell() - 65536))
                    print(stream.read(65536).decode("utf-8", errors="replace"))
            except OSError as exc:
                print(f"Unable to read verifier output: {exc}")
    finally:
        if token:
            print(f"::{token}::")


def command_check_result(args: argparse.Namespace) -> None:
    result_path = Path(args.result)
    # Harbor 0.22's OracleAgent records a nonzero solve.sh exit here without
    # raising a trial exception. The verifier can still grade unchanged Base
    # or a partially applied Oracle, so a matching reward is insufficient.
    for status in sorted(result_path.parent.glob("*/agent/exit-code.txt")):
        if any(path.is_symlink() for path in (status, status.parent, status.parent.parent)):
            raise ContractError(f"Oracle exit status must not follow symlinks: {status}")
        try:
            info = status.stat()
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 32:
                raise ContractError(f"Invalid Oracle exit status: {status}")
            raw = status.read_text().strip()
        except (OSError, UnicodeError) as exc:
            raise ContractError(f"Unable to read Oracle exit status: {status}") from exc
        if not re.fullmatch(r"-?[0-9]+", raw):
            raise ContractError(f"Invalid Oracle exit status: {status}")
        if int(raw) != 0:
            raise ContractError(
                f"Oracle execution failed with exit code {raw}; "
                f"see {status.parent / 'oracle.txt'}"
            )
    completed, errored, rewards = result_reward(result_path)
    expected = float(args.expected_reward)
    if completed != 1 or errored != 0 or rewards != [expected]:
        print_verifier_failure_logs(Path(args.result).parent)
        raise ContractError(
            f"unexpected Harbor result: completed={completed}, errored={errored}, "
            f"rewards={rewards}, expected={[expected]}"
        )
    print(json.dumps({"completed": completed, "errored": errored, "rewards": rewards}))


def command_hardware_check(args: argparse.Namespace) -> None:
    task_dir = TASKS_DIR / args.task
    config, runner = task_contract(task_dir)
    environment = config["environment"]
    required = environment.get("gpus", 0)
    gpu_types = environment.get("gpu_types", [])
    machine = platform.machine().lower()
    if machine not in ("x86_64", "amd64"):
        raise ContractError(f"{task_dir.name}: runner architecture is {machine}, expected x64")
    if required == 0:
        print(json.dumps({"architecture": machine, "gpus": 0}))
        return

    query = subprocess.run(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()
    matching = [
        name for name in query
        if any(gpu_type_matches(name, supported) for supported in runner["gpu_types"])
        and (not gpu_types or any(gpu_type_matches(name, requested) for requested in gpu_types))
    ]
    if len(matching) < required:
        raise ContractError(
            f"{task_dir.name}: requires {required} GPUs with types {gpu_types or runner['gpu_types']}, "
            f"found {matching}"
        )
    print(
        json.dumps(
            {
                "architecture": machine,
                "gpus": required,
                "gpu_types": gpu_types,
                "visible_gpus": query,
            }
        )
    )


def command_cases(args: argparse.Namespace) -> None:
    task_dir = TASKS_DIR / args.task
    task_contract(task_dir)
    manifest = validation_manifest(task_dir)
    validation_mode = task_validation_mode(task_dir, manifest)
    cases = [{"name": "base", "expected_reward": 0}]
    if validation_mode == "oracle":
        cases.append({"name": "oracle", "expected_reward": 1})
    cases.extend(
        {"name": item["name"], "expected_reward": item["expected_reward"]}
        for item in manifest["cases"]
    )
    selection = getattr(args, "filter", None)
    if selection is not None:
        names = selection.split(",")
        available = {case["name"] for case in cases}
        if not names or any(not name or name not in available for name in names) or len(names) != len(set(names)):
            raise ContractError("Case filter must contain distinct declared case names")
        cases = [case for case in cases if case["name"] in names]
    if "reviewed_replay" in manifest:
        for case in cases:
            case["reviewed_replay"] = True
    print(json.dumps(cases, separators=(",", ":")))


def command_run_reviewed_case(args: argparse.Namespace) -> None:
    task_dir = TASKS_DIR / args.task
    validate_task(task_dir)
    manifest = validation_manifest(task_dir)
    replay = reviewed_replay_config(task_dir, manifest)
    if replay is None or args.case not in replay["cases"]:
        raise ContractError("No explicit reviewed replay profile for this CI case")
    config = load_toml(task_dir / "task.toml")
    if config["environment"].get("gpus", 0):
        raise ContractError("Reviewed replay CI currently supports the Docker CPU path only")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.image):
        raise ContractError("Reviewed replay requires an immutable local image ID")
    output = Path(args.output).absolute()
    selected = replay["cases"][args.case]
    validation = task_dir / "validation"
    command = [sys.executable, "-I", str(validation / replay["runner"]["path"]),
               "--task", str(task_dir), "--image", args.image, "--output", str(output),
               "--profile-id", "ci-" + hashlib.sha256(f"{args.task}/{args.case}".encode()).hexdigest()[:24],
               "--binding", str(validation / selected["binding"]["path"]),
               "--cpus", "limit", "--memory", "limit", "--no-artifacts", "--delete"]
    if args.override_cpus is not None:
        if args.override_cpus <= 0:
            raise ContractError("CPU override must be positive")
        command += ["--override-cpus", str(args.override_cpus)]
    if args.case in {"base", "oracle"}:
        command.append("--" + args.case)
        expected_reward = 0 if args.case == "base" else 1
    else:
        case = next(case for case in manifest["cases"] if case["name"] == args.case)
        command += ["--submission", str(validation / case["patch"])]
        if case.get("apply_after", "base") == "oracle":
            command.append("--after-oracle")
        expected_reward = case["expected_reward"]
    # Task-owned runners are explicit curator inputs, never candidate workspace
    # code. The existing Harbor reward checker remains authoritative in CI.
    with tempfile.TemporaryDirectory(prefix="reviewed-replay-inputs-") as temporary:
        for role in ("scenario", "review_evidence"):
            reference = selected[role]
            if "content" in reference:
                path = Path(temporary) / (role + ".json")
                path.write_bytes(inline_replay_bytes(reference))
            else:
                path = validation / reference["path"]
            command += ["--" + role.replace("_", "-"), str(path)]
        subprocess.run(command, cwd=REPO_ROOT, check=True)
    job_dir = output / "jobs" / "reviewed-replay"
    command_check_result(argparse.Namespace(result=str(job_dir / "result.json"),
                                           expected_reward=expected_reward))
    shutil.copy2(output / "task" / "task.toml", job_dir / "prepared-task.toml")


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
# The image may run as root while its checkout belongs to the agent. Trust
# only this curator-declared checkout for these read-only audit commands.
git() {{ command git -c safe.directory={shlex.quote(workdir)} "$@"; }}
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
    cases.add_argument("--filter", help="Explicit comma-separated subset; default is every declared case")
    cases.set_defaults(func=command_cases)

    reviewed = subparsers.add_parser("run-reviewed-case")
    reviewed.add_argument("--task", required=True)
    reviewed.add_argument("--image", required=True)
    reviewed.add_argument("--case", required=True)
    reviewed.add_argument("--output", required=True)
    reviewed.add_argument("--override-cpus", type=int)
    reviewed.set_defaults(func=command_run_reviewed_case)

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
