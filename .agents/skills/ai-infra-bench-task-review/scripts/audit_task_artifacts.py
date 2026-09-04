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

TIMEOUT = 120
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
RAW_ID = re.compile(r"(?:^|-)(?:pr|issue|candidate|instance)-[a-z0-9]+(?:-|$)")
REQUIRED_FILES = (
    "instruction.md",
    "environment/Dockerfile",
    "environment/image-manifest.json",
    "environment/lock/manifest.json",
    "environment/lock/requirements.txt",
    "solution/oracle.patch",
    "solution/solve.sh",
    "tests/test.sh",
    "validation/ci-cases.json",
    "validation/e2e-evidence.json",
)
EVIDENCE_HASHES = {
    "task_metadata_sha256": "task.toml",
    "instruction_sha256": "instruction.md",
    "image_manifest_sha256": "environment/image-manifest.json",
    "oracle_patch_sha256": "solution/oracle.patch",
    "solve_script_sha256": "solution/solve.sh",
    "test_script_sha256": "tests/test.sh",
    "regression_test_sha256": "tests/test_regression.py",
    "junit_checker_sha256": "tests/check_junit.py",
    "ci_cases_sha256": "validation/ci-cases.json",
    "remediation_matrix_sha256": "validation/remediation-matrix.md",
}


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
    repository = metadata.get("repository")
    if isinstance(repository, str) and "/" in repository:
        prefix = repository.rsplit("/", 1)[-1].lower().replace("_", "-")
        audit.require(
            slug.startswith(f"{prefix}-"), f"task slug must start with {prefix}-"
        )

    missing = [path for path in REQUIRED_FILES if not (task / path).is_file()]
    audit.require(not missing, f"required task files are missing: {missing}")
    audit.require(
        bool(re.fullmatch(r"[0-9a-f]{40}", str(metadata.get("base_commit", "")))),
        "[metadata].base_commit is not a full commit SHA",
    )
    audit.require(
        bool(
            re.fullmatch(r"sha256:[0-9a-f]{64}", str(metadata.get("image_digest", "")))
        ),
        "[metadata].image_digest is not a SHA-256 digest",
    )
    validator = repo / ".github/scripts/task_ci.py"
    if audit.require(validator.is_file(), "repository task validator is missing"):
        result = run([sys.executable, str(validator), "validate", slug], cwd=repo)
        audit.require(
            result.returncode == 0,
            f"repository task validation failed: {result.stderr.strip()}",
        )
    audit.finish(before, "task identity and repository contract pass")


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
    evidence = mapping(documents.get("validation/e2e-evidence.json"))
    metadata = mapping(config.get("metadata"))

    compare(
        audit,
        "task name",
        mapping(config.get("task")).get("name"),
        {"image manifest": image.get("task")},
    )
    compare(
        audit,
        "Base commit",
        metadata.get("base_commit"),
        {
            "image manifest": image.get("base_commit"),
            "lock manifest": lock.get("base_commit"),
        },
    )
    compare(
        audit,
        "dependency cutoff",
        metadata.get("dependency_cutoff"),
        {
            "image manifest": image.get("dependency_cutoff"),
            "lock manifest": lock.get("dependency_cutoff"),
        },
    )
    compare(
        audit,
        "image digest",
        metadata.get("image_digest"),
        {"image manifest": image.get("image_id")},
    )

    hashes = [
        ("image manifest", image.get("dockerfile_sha256"), "environment/Dockerfile"),
        (
            "image manifest",
            image.get("dependency_lock_sha256"),
            "environment/lock/requirements.txt",
        ),
        (
            "image manifest",
            image.get("dependency_lock_manifest_sha256"),
            "environment/lock/manifest.json",
        ),
    ]
    output = mapping(lock.get("output"))
    if isinstance(output.get("path"), str):
        hashes.append(("lock manifest", output.get("sha256"), output["path"]))
    else:
        audit.require(False, "lock manifest does not record output.path")
    artifacts = mapping(evidence.get("artifacts"))
    for key, relative in EVIDENCE_HASHES.items():
        if key in artifacts:
            hashes.append((f"evidence artifacts.{key}", artifacts[key], relative))
    for source, recorded, relative in hashes:
        path = task / relative
        audit.require(path.is_file(), f"{source} refers to missing {relative}")
        if path.is_file():
            audit.require(
                recorded == digest(path), f"{source} hash is stale for {relative}"
            )

    control_hashes = {digest(path) for path in (task / "validation").glob("*.patch")}
    for group in ("adversarial_runs", "alternative_implementation_runs"):
        runs = evidence.get(group, [])
        if not audit.require(
            isinstance(runs, list), f"evidence {group} must be a list"
        ):
            continue
        for index, item in enumerate(runs):
            recorded = mapping(item).get("patch_sha256")
            audit.require(
                recorded in control_hashes,
                f"evidence {group}[{index}] does not match a control patch",
            )
    audit.finish(before, "artifact identities and standard hashes match")


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
    audit.require(
        image_id == mapping(config.get("metadata")).get("image_digest"),
        "local image ID does not match task.toml",
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
    patches = [
        task / "solution/oracle.patch",
        *sorted((task / "validation").glob("*.patch")),
    ]
    for patch in patches:
        result = run(
            [
                docker,
                "run",
                "--rm",
                "--network=none",
                "--workdir",
                workdir,
                "--entrypoint",
                "git",
                "-v",
                f"{task}:/task:ro",
                image,
                "apply",
                "--check",
                f"/task/{patch.relative_to(task)}",
            ]
        )
        audit.require(
            result.returncode == 0,
            f"{patch.relative_to(task)} does not apply: {result.stderr.strip()}",
        )
    audit.finish(before, f"image audit and {len(patches)} patch checks pass")


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path)
    parser.add_argument("--image", help="run image and patch checks")
    parser.add_argument(
        "--junit", type=Path, required=True, help="run the task's JUnit checker"
    )
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
        check_junit(task, args.junit.resolve(), audit)
        if args.image:
            check_image(task, config, repo, args.image, audit)
        if args.staged:
            check_staged(task, repo, audit)
    print(json.dumps(vars(audit), sort_keys=True))
    return int(audit.errors > 0)


if __name__ == "__main__":
    raise SystemExit(main())
