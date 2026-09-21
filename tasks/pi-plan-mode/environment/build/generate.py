#!/usr/bin/env python3
"""Generate pi-plan-mode's Dockerfile from its task-local frozen template.

The rendered Dockerfile has no local COPY instructions, so it builds from an
empty context; every input (base commit, dependency cutoff, the sha256 of the
checked-in package-lock.json) is read from task.toml and environment/lock/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPOSITORY = "earendil-works/pi"
TOKENS = {
    "base_commit": "__PI_BASE_SHA__",
    "dependency_cutoff": "__PI_DEPENDENCY_CUTOFF__",
    "cache_namespace": "__PI_CACHE_NAMESPACE__",
    "lock_sha256": "__PI_LOCK_SHA256__",
    "editable_extension": "__PI_EDITABLE_EXTENSION__",
}
SHA_RE = re.compile(r"[0-9a-f]{40}")
CUTOFF_RE = re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
TEMPLATE_DIR = Path(__file__).resolve().parent
TASK_DIR = TEMPLATE_DIR.parents[1]
TEMPLATE_PATH = TEMPLATE_DIR / "Dockerfile.template"


def metadata_value(task_file: Path, key: str) -> str:
    text = task_file.read_text()
    section = re.search(r"(?ms)^\[metadata\][ \t]*\n(.*?)(?=^\[|\Z)", text)
    if section is None:
        raise ValueError(f"{task_file}: missing [metadata] section")
    value = re.search(rf'(?m)^{re.escape(key)}[ \t]*=[ \t]*"([^"]+)"[ \t]*$', section.group(1))
    if value is None:
        raise ValueError(f"{task_file}: missing string metadata.{key}")
    return value.group(1)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lock_sha256(task_dir: Path) -> str:
    """The lock manifest names the lock file; its recorded sha256 must match the file."""
    manifest_path = task_dir / "environment" / "lock" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    output = manifest["output"]
    lock_path = task_dir / output["path"]
    if not lock_path.is_file():
        raise FileNotFoundError(f"{manifest_path}: output.path {output['path']} does not exist")
    actual = sha256_file(lock_path)
    if actual != output["sha256"]:
        raise ValueError(
            f"{lock_path}: sha256 {actual} differs from lock manifest {output['sha256']}"
        )
    if manifest.get("base_commit") != metadata_value(task_dir / "task.toml", "base_commit"):
        raise ValueError(f"{manifest_path}: base_commit differs from task.toml")
    return actual


def render(task_dir: Path, template: str) -> tuple[Path, str]:
    task_file = task_dir / "task.toml"
    if metadata_value(task_file, "repository") != REPOSITORY:
        raise ValueError(f"{task_file}: not an {REPOSITORY} task")
    base_commit = metadata_value(task_file, "base_commit")
    if SHA_RE.fullmatch(base_commit) is None:
        raise ValueError(f"{task_file}: base_commit must be 40 lowercase hex characters")
    dependency_cutoff = metadata_value(task_file, "dependency_cutoff")
    if CUTOFF_RE.fullmatch(dependency_cutoff) is None:
        raise ValueError(f"{task_file}: dependency_cutoff must be an RFC 3339 UTC timestamp")
    lock = lock_sha256(task_dir)
    try:
        editable_extension = metadata_value(task_file, "editable_extension")
    except ValueError:
        editable_extension = ""
    if editable_extension and re.fullmatch(r"[a-z0-9][a-z0-9-]*", editable_extension) is None:
        raise ValueError(f"{task_file}: editable_extension must be a plain extension directory name")
    values = {
        "base_commit": base_commit,
        "dependency_cutoff": dependency_cutoff,
        "cache_namespace": f"{base_commit}-{lock[:16]}",
        "lock_sha256": lock,
        "editable_extension": editable_extension,
    }
    generated = template
    for key, token in TOKENS.items():
        generated = generated.replace(token, values[key])
    return task_dir / "environment" / "Dockerfile", generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Fail if a generated Dockerfile is missing or stale"
    )
    args = parser.parse_args()

    template = TEMPLATE_PATH.read_text()
    for token in TOKENS.values():
        if template.count(token) != 1:
            raise ValueError(f"{TEMPLATE_PATH}: expected exactly one {token} token")
    if re.search(r"(?m)^COPY (?!--from=|<<)", template):
        raise ValueError(f"{TEMPLATE_PATH}: local COPY instructions break the empty build context")

    output, generated = render(TASK_DIR, template)
    digest = hashlib.sha256(generated.encode()).hexdigest()
    if args.check:
        if not output.is_file() or output.read_text() != generated:
            print(f"STALE {output}", file=sys.stderr)
            return 1
        print(f"OK {digest} {output}")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(generated)
        print(f"WROTE {digest} {output}")
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
