#!/usr/bin/env python3
"""Normalize image records and check their file hashes against the working tree."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
# One dependency lock per task: pip requirements (Python targets) or the repository's
# package-lock.json (Node targets).
DEPENDENCY_LOCKS = ("lock/requirements.txt", "lock/package-lock.json")
REQUIRED_FILES = ("Dockerfile", "lock/manifest.json")
BUILD_FIELDS = ("dockerfile", "parent_image_id", "args")


def normalize_manifest(manifest: dict) -> dict:
    if not isinstance(manifest, dict):
        raise ValueError("Image manifest must be an object")
    unknown = manifest.keys() - {"image_id", "build", "files"}
    if unknown:
        raise ValueError(f"Review unknown image manifest fields: {sorted(unknown)}")
    image_id = manifest.get("image_id")
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("image_id must be a SHA-256 image ID")
    files = manifest.get("files")
    if not isinstance(files, dict) or not set(REQUIRED_FILES) <= files.keys():
        raise ValueError(f"files must include {', '.join(REQUIRED_FILES)}")
    locks = [name for name in DEPENDENCY_LOCKS if name in files]
    if len(locks) != 1:
        raise ValueError(f"files must include exactly one dependency lock ({' or '.join(DEPENDENCY_LOCKS)})")
    for relative, digest in files.items():
        if (
            not isinstance(relative, str) or not relative
            or Path(relative).is_absolute() or ".." in Path(relative).parts
            or Path(relative).as_posix() != relative
            or any(character in relative for character in "\\\r\n\0")
        ):
            raise ValueError(f"Unsafe environment-relative file path: {relative!r}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"Invalid SHA-256 for {relative}")
    result = {"image_id": image_id}
    if "build" in manifest:
        build = manifest["build"]
        if not isinstance(build, dict) or build.keys() - set(BUILD_FIELDS):
            raise ValueError("build may contain only dockerfile, parent_image_id, and args")
        if "dockerfile" in build and (
            not isinstance(build["dockerfile"], str) or build["dockerfile"] not in files
        ):
            raise ValueError("build.dockerfile must have a recorded file hash")
        if "parent_image_id" in build and not re.fullmatch(
            r"sha256:[0-9a-f]{64}", str(build["parent_image_id"])
        ):
            raise ValueError("build.parent_image_id must be a SHA-256 image ID")
        if "args" in build and (
            not isinstance(build["args"], dict)
            or not all(isinstance(k, str) and k and isinstance(v, str) for k, v in build["args"].items())
        ):
            raise ValueError("build.args must map argument names to string values")
        if build:
            result["build"] = {key: build[key] for key in BUILD_FIELDS if key in build}
    leading = ["Dockerfile", *locks, "lock/manifest.json"]
    order = [*leading, *sorted(files.keys() - set(leading))]
    result["files"] = {relative: files[relative] for relative in order}
    return result


def check_file_hashes(manifest: dict, environment: Path) -> None:
    for relative, expected in normalize_manifest(manifest)["files"].items():
        path = environment / relative
        if not path.resolve().is_relative_to(environment.resolve()) or not path.is_file():
            raise ValueError(f"Missing or escaping image input: {path}")
        with path.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != expected:
            raise ValueError(f"Image input hash is stale for {path}: recorded {expected}, actual {actual}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check without editing")
    args = parser.parse_args()
    paths = sorted((REPO_ROOT / "tasks").glob("*/environment/image-manifest.json"))
    changes = []
    hashes = 0
    # Check every record before writing; formatting never refreshes image provenance.
    for path in paths:
        original = path.read_text()
        try:
            manifest = normalize_manifest(json.loads(original))
            check_file_hashes(manifest, path.parent)
        except ValueError as exc:
            parser.error(f"{path}: {exc}")
        hashes += len(manifest["files"])
        updated = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        if updated != original:
            changes.append((path, updated))
    if args.check and changes:
        parser.exit(1, "Image manifests need normalization:\n" + "\n".join(
            path.relative_to(REPO_ROOT).as_posix() for path, _ in changes
        ) + "\n")
    for path, updated in changes:
        path.write_text(updated)
    print(f"{'Checked' if args.check else 'Normalized'} {len(paths)} image manifests; checked {hashes} file hashes")


if __name__ == "__main__":
    main()
