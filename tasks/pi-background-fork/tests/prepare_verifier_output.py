#!/usr/bin/env python3
"""Establish the verifier output boundary before executing any candidate code.

Preserve already-open Harbor stdout files. Walk using directory descriptors and
O_NOFOLLOW; reject symlinks, special files and multiply-linked regular files rather
than following or recursively deleting a candidate-supplied path.
"""
import json
import os
from pathlib import Path
import stat
import sys


def open_directory(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("output parent must be an absolute directory path")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd
    except BaseException:
        os.close(fd)
        raise


def prepare(logs="/logs", *, owner_uid=0, owner_gid=0):
    parent = open_directory(logs)
    output = None
    files = []
    try:
        # Protect the parent too: write access there would allow renaming the
        # protected verifier directory and replacing it after this check.
        os.fchown(parent, owner_uid, owner_gid)
        os.fchmod(parent, 0o755)
        try:
            os.mkdir("verifier", 0o755, dir_fd=parent)
        except FileExistsError:
            pass
        output = os.open("verifier", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        os.fchown(output, owner_uid, owner_gid)
        os.fchmod(output, 0o755)
        for name in os.listdir(output):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=output)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError(f"unexpected non-regular or multiply-linked verifier output: {name}")
                os.fchown(fd, owner_uid, owner_gid)
                os.fchmod(fd, 0o644)
                files.append(name)
            finally:
                os.close(fd)
        return {"directory": str(Path(logs) / "verifier"), "directory_mode": "0755", "file_mode": "0644", "owner_uid": owner_uid, "protected_existing_files": sorted(files)}
    finally:
        if output is not None:
            os.close(output)
        os.close(parent)


if __name__ == "__main__":
    if sys.argv[1:] == ["--check-not-writable"]:
        paths = ["/logs", "/logs/verifier"]
        paths += ["/logs/verifier/" + name for name in os.listdir("/logs/verifier")]
        writable = [path for path in paths if os.access(path, os.W_OK)]
        print(json.dumps({"checked_as_uid": os.geteuid(), "candidate_writable_outputs": writable}))
        raise SystemExit(1 if writable else 0)
    if sys.argv[1:]:
        raise SystemExit("unexpected output preparation arguments")
    if os.geteuid() != 0:
        raise SystemExit("verifier output preparation requires root")
    try:
        print(json.dumps(prepare()))
    except (OSError, ValueError) as exc:
        print(f"verifier output isolation failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
