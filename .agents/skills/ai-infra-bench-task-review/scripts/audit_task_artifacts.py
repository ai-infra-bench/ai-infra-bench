#!/usr/bin/env python3
"""Run mechanical checks for one ai-infra-bench task.

This does not judge authenticity, verifier alignment, E2E quality, or actual
Base, Oracle, control, and Harbor behavior.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".github/scripts"))
from task_ci import ContractError, validate_task

TIMEOUT = 120

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


def mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_task_relative_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or any(
        character in value for character in "\r\n\0"
    ):
        return None
    return path.as_posix()


def load(task: Path, audit: Audit) -> dict[str, Any]:
    before = audit.errors
    config: dict[str, Any] = {}
    try:
        config = tomllib.loads((task / "task.toml").read_text())
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        audit.require(False, f"invalid task.toml: {exc}")

    for path in sorted(task.rglob("*.json")):
        try:
            json.loads(path.read_text())
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
    return config


def check_task(task: Path, audit: Audit) -> None:
    before = audit.errors
    try:
        validate_task(task)
    except ContractError as exc:
        audit.require(False, f"repository task validation failed: {exc}")
    audit.finish(before, "shared task contract checks pass")


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
    config = load(task, audit)
    check_task(task, audit)
    if config:
        check_diff_whitespace(task, repo, audit)
        if args.image:
            check_image(task, config, repo, args.image, audit)
        if args.staged:
            check_staged(task, repo, audit)
    print(json.dumps(vars(audit), sort_keys=True))
    return int(audit.errors > 0)


if __name__ == "__main__":
    raise SystemExit(main())
