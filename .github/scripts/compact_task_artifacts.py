#!/usr/bin/env python3
"""Deduplicate completed CI workspace snapshots and package full Harbor results."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile
import tempfile
import tomllib
import uuid


def signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_size, stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid,
        info.st_mtime_ns,
    )


def deduplicate(job_dir: Path, index_path: Path, source: str) -> dict[str, int]:
    root = index_path.parent.resolve()
    job_dir = job_dir.resolve()
    if job_dir == root or not job_dir.is_relative_to(root):
        raise ValueError("job directory must be inside the task results directory")
    source_path = PurePosixPath(source)
    if not source_path.is_absolute() or ".." in source_path.parts or source == "/":
        raise ValueError("snapshot source must be an absolute checkout path")
    relative_source = Path(*source_path.parts[1:])
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    summary = {"files_checked": 0, "files_linked": 0, "duplicate_bytes": 0}
    for trial in sorted(job_dir.iterdir()):
        if trial.is_symlink() or not trial.is_dir():
            continue
        snapshot = trial / "artifacts" / relative_source
        if snapshot.is_symlink() or not snapshot.is_dir():
            continue
        # Only deduplicate copied checkouts, never the agent-mounted
        # /logs/artifacts directory or logs that Harbor may still update.
        for directory, dirs, files in os.walk(snapshot, followlinks=False):
            dirs[:] = [name for name in dirs if not (Path(directory) / name).is_symlink()]
            for name in files:
                path = Path(directory) / name
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode):
                    continue
                summary["files_checked"] += 1
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                # Match the same checkout path across trials. Do not introduce
                # new aliases between distinct files within one snapshot.
                key = json.dumps([path.relative_to(snapshot).as_posix(), *signature(info), digest])
                previous = index.get(key)
                reference = root / previous if previous else None
                if reference is not None:
                    if not reference.resolve().is_relative_to(root):
                        raise ValueError("snapshot index references a path outside task results")
                    try:
                        old = reference.lstat()
                    except FileNotFoundError:
                        old = None
                    if old is not None and stat.S_ISREG(old.st_mode) and signature(old) == signature(info):
                        if (old.st_dev, old.st_ino) == (info.st_dev, info.st_ino):
                            continue
                        # Keep the original file until its replacement link is
                        # ready; a failed link must not remove snapshot data.
                        temporary = path.parent / (".snapshot-link-" + uuid.uuid4().hex)
                        try:
                            os.link(reference, temporary, follow_symlinks=False)
                            os.replace(temporary, path)
                        finally:
                            temporary.unlink(missing_ok=True)
                        summary["files_linked"] += 1
                        summary["duplicate_bytes"] += info.st_size
                        continue
                index[key] = path.relative_to(root).as_posix()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=index_path.parent, delete=False) as stream:
        json.dump(index, stream, sort_keys=True)
        temporary_index = Path(stream.name)
    os.replace(temporary_index, index_path)
    return summary


def package(results_dir: Path, output: Path) -> bool:
    if not results_dir.is_dir():
        print(f"No Harbor results to package: {results_dir}")
        return False
    if output.resolve().is_relative_to(results_dir.resolve()):
        raise ValueError("archive output must be outside the results directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        # tar preserves cross-trial hardlinks and hidden files. Uploading the
        # expanded directory as ZIP would duplicate each hardlink's payload.
        with tarfile.open(temporary, "w:gz", compresslevel=1, dereference=False) as archive:
            archive.add(results_dir, arcname=results_dir.name)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({"archive": str(output), "size_bytes": output.stat().st_size}))
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    dedupe = commands.add_parser("dedupe")
    dedupe.add_argument("--task-dir", type=Path, required=True)
    dedupe.add_argument("--job-dir", type=Path, required=True)
    dedupe.add_argument("--index", type=Path, required=True)
    pack = commands.add_parser("pack")
    pack.add_argument("--results-dir", type=Path, required=True)
    pack.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "dedupe":
        config = tomllib.loads((args.task_dir / "task.toml").read_text())
        print(json.dumps(deduplicate(args.job_dir, args.index, config["environment"]["workdir"])))
    else:
        package(args.results_dir, args.output)


if __name__ == "__main__":
    main()
