#!/usr/bin/env python3
"""Run mechanical checks for one ai-infra-bench task.

This does not judge authenticity, verifier alignment, E2E quality, or actual
Base, Oracle, control, and Harbor behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
from normalize_image_manifests import check_file_hashes
from sync_collect_hooks import render_command

TIMEOUT = 120
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
RAW_ID = re.compile(r"(?:^|-)(?:pr|issue|candidate|instance)-[a-z0-9]+(?:-|$)")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# The dependency lock is the target ecosystem's own: pip requirements for Python
# targets (vLLM), the repository's package-lock.json for Node targets (pi).
DEPENDENCY_LOCKS = ("environment/lock/requirements.txt", "environment/lock/package-lock.json")
# The leading keyword names the project; the website derives the repository from it.
PROJECT_KEYWORDS = ("vllm", "pi")
REQUIRED_FILES = (
    "instruction.md",
    "environment/Dockerfile",
    "environment/image-manifest.json",
    "environment/lock/manifest.json",
    "solution/oracle.patch",
    "solution/solve.sh",
    "tests/test.sh",
    "validation/ci-cases.json",
)


class Audit:
    def __init__(self) -> None:
        self.checks = self.warnings = self.errors = 0

    def ok(self, message: str) -> None:
        self.checks += 1
        print(f"OK: {message}")

    def warn(self, message: str) -> None:
        self.warnings += 1
        print(f"WARN: {message}")

    def require(self, condition: bool, message: str) -> bool:
        if condition:
            return True
        self.errors += 1
        print(f"ERROR: {message}")
        return False

    def finish(self, before: int, message: str) -> None:
        if self.errors == before:
            self.ok(message)


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            command, 124, "", f"timed out after {TIMEOUT}s"
        )


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def recorded_sha256(value: Any) -> str | None:
    if isinstance(value, str) and SHA256.fullmatch(value):
        return value
    if isinstance(value, dict):
        candidate = value.get("sha256")
        if isinstance(candidate, str) and SHA256.fullmatch(candidate):
            return candidate
    return None


def safe_task_relative_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or any(
        character in value for character in "\r\n\0"
    ):
        return None
    return path.as_posix()


def load(task: Path, audit: Audit) -> tuple[dict[str, Any], dict[str, Any]]:
    before = audit.errors
    config: dict[str, Any] = {}
    try:
        config = tomllib.loads((task / "task.toml").read_text())
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        audit.require(False, f"invalid task.toml: {exc}")

    documents: dict[str, Any] = {}
    for path in sorted(task.rglob("*.json")):
        try:
            documents[path.relative_to(task).as_posix()] = json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            audit.require(False, f"invalid JSON {path.relative_to(task)}: {exc}")
    for path in sorted(task.rglob("*.py")):
        try:
            compile(path.read_text(), str(path), "exec")
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            audit.require(False, f"invalid Python {path.relative_to(task)}: {exc}")
    if bash := shutil.which("bash"):
        for path in sorted(task.rglob("*.sh")):
            result = run([bash, "-n", str(path)])
            audit.require(
                result.returncode == 0,
                f"invalid shell {path.relative_to(task)}: {result.stderr.strip()}",
            )
    else:
        audit.warn("bash is unavailable; shell syntax was not checked")
    audit.finish(before, "task artifacts parse")
    return config, documents


def check_task(task: Path, config: dict[str, Any], repo: Path, audit: Audit) -> None:
    before = audit.errors
    slug = task.name
    audit.require(bool(SLUG.fullmatch(slug)), f"invalid semantic task slug: {slug}")
    audit.require(not RAW_ID.search(slug), f"task slug contains a raw ID: {slug}")

    task_data = mapping(config.get("task"))
    metadata = mapping(config.get("metadata"))
    audit.require(
        task_data.get("name") == f"ai-infra-bench/{slug}",
        f"[task].name does not match tasks/{slug}",
    )
    audit.require(
        isinstance(task_data.get("description"), str)
        and bool(task_data["description"].strip()),
        "[task].description must be non-empty",
    )
    audit.require(
        set(metadata) == {"task_type", "base_commit", "dependency_cutoff"},
        "[metadata] must contain only task_type, base_commit, and dependency_cutoff",
    )
    audit.require(
        metadata.get("task_type") in {"feature", "bugfix", "performance"},
        "[metadata].task_type must be feature, bugfix, or performance",
    )

    case_manifest_path = task / "validation/ci-cases.json"
    try:
        case_manifest = mapping(json.loads(case_manifest_path.read_text()))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        case_manifest = {}
    verifier_only = case_manifest.get("validation_mode") == "verifier_only"
    required_files = [path for path in REQUIRED_FILES if not (verifier_only and path.startswith("solution/"))]
    missing = [path for path in required_files if not (task / path).is_file()]
    audit.require(not missing, f"required task files are missing: {missing}")
    locks = [path for path in DEPENDENCY_LOCKS if (task / path).is_file()]
    audit.require(len(locks) == 1, f"exactly one dependency lock is required ({' or '.join(DEPENDENCY_LOCKS)}), found {locks}")
    audit.require(
        bool(re.fullmatch(r"[0-9a-f]{40}", str(metadata.get("base_commit", "")))),
        "[metadata].base_commit is not a full commit SHA",
    )
    check_benchmark_config(config, audit)
    validator = repo / ".github/scripts/task_ci.py"
    if audit.require(validator.is_file(), "repository task validator is missing"):
        result = run([sys.executable, str(validator), "validate", slug], cwd=repo)
        audit.require(
            result.returncode == 0,
            f"repository task validation failed: {result.stderr.strip()}",
        )
    audit.finish(before, "task identity and repository contract pass")


def check_benchmark_config(config: dict[str, Any], audit: Audit) -> None:
    expected = {
        "task": {"version": "1.0.0"},
        "environment": {
            "cpus": 8, "memory_mb": 16384, "storage_mb": 51200,
            "build_timeout_sec": 10800, "network_mode": "no-network",
        },
        "agent": {"timeout_sec": 36000},
        "verifier": {"timeout_sec": 7200},
    }
    for section, fields in expected.items():
        actual = mapping(config.get(section))
        for key, value in fields.items():
            audit.require(actual.get(key) == value, f"[{section}].{key} must be {value!r}")
    task = mapping(config.get("task"))
    audit.require("authors" not in task, "[task].authors must be omitted")
    keywords = task.get("keywords")
    audit.require(
        isinstance(keywords, list) and 1 <= len(keywords) <= 4
        and keywords[0] in PROJECT_KEYWORDS
        and all(isinstance(word, str) and word and not re.search(r"(?:^|[-_])(cpu|gpu)(?:$|[-_])", word, re.I) for word in keywords),
        f"keywords must start with the project ({' or '.join(PROJECT_KEYWORDS)}) and contain at most three topic tags, without CPU/GPU tags",
    )
    environment = mapping(config.get("environment"))
    agent = mapping(config.get("agent"))
    verifier = mapping(config.get("verifier"))
    audit.require("docker_image" not in environment, "omit environment.docker_image from the committed task")
    gpus = environment.get("gpus")
    if audit.require(type(gpus) is int and gpus >= 0, "environment.gpus must be an explicit nonnegative integer"):
        if gpus:
            audit.require(environment.get("gpu_types") == ["A100"], "GPU tasks must declare gpu_types = ['A100']")
        else:
            audit.require("gpu_types" not in environment, "CPU tasks must omit gpu_types")
    audit.require(
        "environment_mode" not in verifier and "environment" not in verifier,
        "omit verifier environment settings to use default shared verification",
    )
    for section in ("agent", "verifier"):
        audit.require(
            mapping(config.get(section)).get("network_mode", "no-network") == "no-network",
            f"[{section}] must preserve offline runtime networking",
        )
    workdir = environment.get("workdir")
    audit.require(config.get("artifacts") == [workdir], "artifacts must archive the complete environment.workdir")
    hooks = verifier.get("collect")
    if audit.require(isinstance(hooks, list) and len(hooks) == 1, "one standard verifier.collect hook is required"):
        hook = mapping(hooks[0])
        audit.require(hook.get("service") == "main", "collector service must be main")
        audit.require(hook.get("timeout_sec") == 300, "collector timeout_sec must be 300")
        audit.require(hook.get("user") == agent.get("user"), "collector must run as the agent user")
        base = mapping(config.get("metadata")).get("base_commit")
        if isinstance(workdir, str) and isinstance(base, str):
            audit.require(hook.get("command") == render_command(workdir, base), "collector command is stale; run tools/sync_collect_hooks.py")


def compare(
    audit: Audit,
    label: str,
    expected: Any,
    required: dict[str, Any],
) -> None:
    for source, actual in required.items():
        audit.require(actual is not None, f"{source} does not record {label}")
        if actual is not None:
            audit.require(actual == expected, f"{source} has the wrong {label}")


def check_artifacts(
    task: Path,
    config: dict[str, Any],
    documents: dict[str, Any],
    audit: Audit,
) -> None:
    before = audit.errors
    image = mapping(documents.get("environment/image-manifest.json"))
    lock = mapping(documents.get("environment/lock/manifest.json"))
    metadata = mapping(config.get("metadata"))

    compare(
        audit,
        "Base commit",
        metadata.get("base_commit"),
        {
            "lock manifest": lock.get("base_commit"),
        },
    )
    compare(
        audit,
        "dependency cutoff",
        metadata.get("dependency_cutoff"),
        {
            "lock manifest": lock.get("dependency_cutoff"),
        },
    )
    checked_paths: set[str] = set()
    try:
        check_file_hashes(image, task / "environment")
        checked_paths.update(f"environment/{relative}" for relative in image["files"])
    except ValueError as exc:
        audit.require(False, f"invalid image manifest: {exc}")

    hashes: list[tuple[str, Any, str]] = []
    output = mapping(lock.get("output"))
    lock_output_path = safe_task_relative_path(output.get("path"))
    if lock_output_path is not None:
        hashes.append(("lock manifest", output.get("sha256"), lock_output_path))
    else:
        audit.require(False, "lock manifest does not record a safe output.path")

    for source, recorded, relative in hashes:
        audit.require(
            recorded_sha256(recorded) is not None,
            f"{source} does not contain a 64-character SHA-256 for {relative}",
        )
        path = task / relative
        audit.require(path.is_file(), f"{source} refers to missing {relative}")
        if path.is_file() and recorded_sha256(recorded) is not None:
            matches = recorded_sha256(recorded) == digest(path)
            audit.require(matches, f"{source} hash is stale for {relative}")
            if matches:
                checked_paths.add(relative)

    manifest = mapping(documents.get("validation/ci-cases.json"))
    cases = manifest.get("cases", [])
    if audit.require(isinstance(cases, list), "validation cases must be a list"):
        for index, item in enumerate(cases):
            case = mapping(item)
            patch_name = case.get("patch")
            recorded = case.get("patch_sha256")
            if not isinstance(patch_name, str):
                audit.require(False, f"validation case {index} has no patch")
                continue
            relative = f"validation/{patch_name}"
            path = task / relative
            audit.require(
                recorded_sha256(recorded) is not None,
                f"validation case {index} patch hash is not a 64-character SHA-256",
            )
            audit.require(path.is_file(), f"validation case refers to missing {relative}")
            if path.is_file() and recorded_sha256(recorded) is not None:
                matches = recorded == digest(path)
                audit.require(
                    matches, f"validation case patch hash is stale for {relative}"
                )
                if matches:
                    checked_paths.add(relative)

    print(f"INFO: checked artifact hashes for {sorted(checked_paths)}")
    audit.finish(before, "artifact identities and all recorded hashes pass")


def check_junit(task: Path, junit: Path, audit: Audit) -> None:
    checker = task / "tests/check_junit.py"
    if not audit.require(checker.is_file(), "tests/check_junit.py is missing"):
        return
    result = run([sys.executable, str(checker), str(junit)])
    audit.require(
        result.returncode == 0,
        f"task JUnit check failed: {(result.stdout + result.stderr).strip()}",
    )
    if result.returncode == 0:
        audit.ok("task JUnit check passes")


def check_image(
    task: Path,
    config: dict[str, Any],
    repo: Path,
    image: str,
    audit: Audit,
) -> None:
    before = audit.errors
    docker = shutil.which("docker")
    if not audit.require(docker is not None, "Docker is unavailable"):
        return
    inspect = run([docker, "image", "inspect", image])
    if not audit.require(inspect.returncode == 0, f"image is unavailable: {image}"):
        return
    try:
        image_id = json.loads(inspect.stdout)[0]["Id"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        audit.require(False, f"cannot read image ID for {image}")
        return
    manifest_path = task / "environment/image-manifest.json"
    try:
        expected_image_id = mapping(json.loads(manifest_path.read_text())).get("image_id")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        audit.require(False, f"cannot read image manifest: {exc}")
        return
    audit.require(
        image_id == expected_image_id,
        "local image ID does not match environment/image-manifest.json",
    )

    validator = repo / ".github/scripts/task_ci.py"
    if not audit.require(validator.is_file(), "repository image checker is missing"):
        return
    result = run(
        [
            sys.executable,
            str(validator),
            "image-check",
            "--task",
            task.name,
            "--image",
            image,
        ],
        cwd=repo,
    )
    audit.require(
        result.returncode == 0,
        f"repository image check failed: {result.stderr.strip()}",
    )

    workdir = str(mapping(config.get("environment")).get("workdir"))
    patches: list[tuple[Path, str]] = []
    if (task / "solution/oracle.patch").is_file():
        patches.append((task / "solution/oracle.patch", "base"))
    case_path = task / "validation/ci-cases.json"
    if case_path.is_file():
        try:
            cases = json.loads(case_path.read_text())["cases"]
            for case in cases:
                relative = safe_task_relative_path(case["patch"])
                apply_after = case.get("apply_after", "base")
                if not relative or apply_after not in {"base", "oracle"}:
                    raise ValueError("invalid patch path or apply_after")
                patches.append((task / "validation" / relative, apply_after))
        except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
            audit.require(False, f"cannot read control patch bases: {exc}")
            return
    for patch, apply_after in patches:
        if apply_after == "oracle" and not audit.require(
            (task / "solution/oracle.patch").is_file(),
            f"{patch.relative_to(task)} requires an unavailable Oracle",
        ):
            continue
        result = run(
            [
                docker,
                "run",
                "--rm",
                "--network=none",
                "--workdir",
                workdir,
                "--entrypoint",
                "sh",
                "-v",
                f"{task}:/task:ro",
                image,
                "-eu",
                "-c",
                'if [ "$1" = oracle ]; then git apply /task/solution/oracle.patch; fi\n'
                'git apply --check "$2"',
                "check-patch",
                apply_after,
                f"/task/{patch.relative_to(task)}",
            ]
        )
        audit.require(
            result.returncode == 0,
            f"{patch.relative_to(task)} does not apply after {apply_after}: {result.stderr.strip()}",
        )
    audit.finish(
        before,
        f"image identity and {len(patches)} patch applicability checks pass",
    )


def check_staged(task: Path, repo: Path, audit: Audit) -> None:
    before = audit.errors
    approved = task.relative_to(repo).as_posix()
    result = run(["git", "diff", "--cached", "--check"], cwd=repo)
    audit.require(result.returncode == 0, f"staged diff is invalid: {result.stdout}")
    result = run(["git", "diff", "--cached", "--name-only", "-z"], cwd=repo)
    staged = [path for path in result.stdout.split("\0") if path]
    outside = [
        path
        for path in staged
        if path != approved and not path.startswith(f"{approved}/")
    ]
    audit.require(not outside, f"staged paths outside the task: {outside}")
    commands = (
        ["git", "diff", "--name-only", "--", approved],
        ["git", "ls-files", "--others", "--exclude-standard", "--", approved],
    )
    remaining = {
        line
        for command in commands
        for line in run(command, cwd=repo).stdout.splitlines()
        if line
    }
    audit.require(
        not remaining, f"task changes are not fully staged: {sorted(remaining)}"
    )
    audit.finish(before, "staged changes are clean and limited to the task")


def check_diff_whitespace(task: Path, repo: Path, audit: Audit) -> None:
    before = audit.errors
    approved = task.relative_to(repo).as_posix()
    for label, command in (
        ("working-tree", ["git", "diff", "--check", "--", approved]),
        ("staged", ["git", "diff", "--cached", "--check", "--", approved]),
    ):
        result = run(command, cwd=repo)
        audit.require(
            result.returncode == 0,
            f"{label} task diff has whitespace errors: "
            f"{(result.stdout + result.stderr).strip()}",
        )
    audit.finish(before, "task diff whitespace checks pass")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path)
    parser.add_argument("--image", help="run image and patch checks")
    parser.add_argument("--junit", type=Path, help="run the task's JUnit checker")
    parser.add_argument("--staged", action="store_true", help="check staged scope")
    args = parser.parse_args()

    task = args.task.resolve()
    audit = Audit()
    if not audit.require(
        (task / "task.toml").is_file(), f"not a task directory: {task}"
    ):
        return 1
    root = run(["git", "rev-parse", "--show-toplevel"], cwd=task)
    if not audit.require(root.returncode == 0, "task is not in a Git worktree"):
        return 1
    repo = Path(root.stdout.strip()).resolve()
    config, documents = load(task, audit)
    if config:
        check_task(task, config, repo, audit)
        check_artifacts(task, config, documents, audit)
        check_diff_whitespace(task, repo, audit)
        if args.junit:
            check_junit(task, args.junit.resolve(), audit)
        if args.image:
            check_image(task, config, repo, args.image, audit)
        if args.staged:
            check_staged(task, repo, audit)
    print(json.dumps(vars(audit), sort_keys=True))
    return int(audit.errors > 0)


if __name__ == "__main__":
    raise SystemExit(main())
