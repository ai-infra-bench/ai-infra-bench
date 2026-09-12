#!/usr/bin/env python3
"""Root-side freeze of the candidate's built native artifact.

Runs as root AFTER the (unprivileged) candidate build and BEFORE any candidate
Python is imported anywhere. It must never import the candidate ``vllm``
package: resolving the artifact via ``importlib.util.find_spec("vllm._moe_C")``
would import the candidate parent package ``vllm`` first and thereby execute
candidate code in this privileged process. The path is therefore discovered by
directory listing only.

Guarantees established here, and relied on by the workers:
  * exactly one ``_moe_C*.so`` exists in the fixed build output directory --
    zero or several is a hard failure, so a stale leftover cannot be picked
    silently;
  * the entry is a regular file, not a symlink (``lstat`` + ``O_NOFOLLOW``), so
    a symlink swap cannot redirect the load;
  * the bytes are read through the ``O_NOFOLLOW`` descriptor and hashed, then
    copied into a root-owned staging directory (0755 root:root, file 0444) that
    the ``agent`` user cannot write;
  * the SHA-256 is taken from the same descriptor that produced the staged
    bytes, so a post-hash replacement (TOCTOU) cannot change what workers load.

Workers are then given ONLY the staged path plus its expected digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path

BUILD_OUTPUT_DIR = Path("/app/vllm")
ARTIFACT_GLOB = "_moe_C*.so"


def fail(reason: str, **extra) -> int:
    print(json.dumps({"staging": "FAIL", "reason": reason, **extra},
                     sort_keys=True))
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging-dir", default="/trusted/staging")
    ap.add_argument("--manifest", default="/logs/verifier/native-staging.json")
    args = ap.parse_args()

    staging = Path(args.staging_dir)
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # Fail closed: an unfinished staging step must not look like a success.
    manifest_path.write_text(json.dumps(
        {"staging": "FAIL", "reason": "staging_did_not_complete"},
        indent=2, sort_keys=True))

    if not BUILD_OUTPUT_DIR.is_dir():
        return fail("build_output_dir_missing", dir=str(BUILD_OUTPUT_DIR))

    # Directory listing only -- no candidate import, no find_spec.
    candidates = sorted(
        p for p in BUILD_OUTPUT_DIR.iterdir() if p.match(ARTIFACT_GLOB)
    )
    if len(candidates) != 1:
        return fail("artifact_count_not_exactly_one",
                    found=[str(p) for p in candidates])

    src = candidates[0]

    # Reject symlinks before opening.
    st = os.lstat(src)
    if stat.S_ISLNK(st.st_mode):
        return fail("artifact_is_symlink", path=str(src))
    if not stat.S_ISREG(st.st_mode):
        return fail("artifact_not_regular_file", path=str(src),
                    mode=oct(st.st_mode))
    real = os.path.realpath(src)
    if real != str(src):
        return fail("artifact_path_escapes_via_symlink",
                    path=str(src), realpath=real)

    # Single O_NOFOLLOW descriptor is the sole source of both the staged bytes
    # and the digest, so nothing can be swapped between hashing and copying.
    try:
        fd = os.open(src, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        return fail("artifact_open_failed", error=str(exc))
    try:
        fst = os.fstat(fd)
        if fst.st_ino != st.st_ino or fst.st_dev != st.st_dev:
            return fail("artifact_changed_between_lstat_and_open")
        with os.fdopen(fd, "rb", closefd=False) as fh:
            data = fh.read()
    finally:
        os.close(fd)

    digest = hashlib.sha256(data).hexdigest()

    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    staged = staging / src.name
    staged.write_bytes(data)

    # Root-owned, world-readable, non-writable by the agent user.
    os.chown(staging, 0, 0)
    os.chmod(staging, 0o755)
    os.chown(staged, 0, 0)
    os.chmod(staged, 0o444)

    staged_digest = hashlib.sha256(staged.read_bytes()).hexdigest()
    if staged_digest != digest:
        return fail("staged_digest_mismatch",
                    expected=digest, actual=staged_digest)

    manifest = {
        "staging": "OK",
        "source_path": str(src),
        "source_realpath": real,
        "staged_path": str(staged),
        "sha256": digest,
        "size_bytes": len(data),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(json.dumps(manifest, sort_keys=True))
    print(f"NATIVE_STAGED_SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
