#!/usr/bin/env python3
"""Scope check by content, not by git.

The instruction forbids changing pi core, the build/test toolchain, and existing test
files. The checkout and its .git belong to the agent, so `git status` is not evidence:
`git update-index --assume-unchanged`, a `.gitignore` line or `.git/info/exclude` hide
an edit from it, and the built pi the lifecycle suite runs (`packages/*/dist/`) is
gitignored altogether. This check reads the files themselves and compares them with

- base-manifest.json (tests/, never visible to the agent): SHA-256 of every Base file
  under the protected paths and under the existing test tree, and
- /opt/pi-baseline/build-manifest.sha256 (root-owned, recorded at image build): SHA-256
  of the untracked files the image build generated in the checkout (the built `dist/`
  trees, generated sources), whose bytes depend on the image build.

The rule is unchanged: protected files must be byte-identical, nothing may be added
under a protected path, existing tests must be untouched. New files anywhere else
(the extension, its tests, docs, scratch files) are never penalised.

Usage: check_scope.py <workspace> <base-manifest.json> <build-manifest.sha256> <summary.json>
Exit status is a bit mask: 1 scope violated, 2 existing tests modified, 4 check error, 8 required deliverable missing.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

LIMIT = 50
# Built output of a workspace package, at any depth (packages/session-backends/*/dist).
DIST = re.compile(r"^packages/(?:[^/]+/)+dist/")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def problem(root: Path, rel: str, expected: str) -> str | None:
    """None when root/rel is a regular file with the expected content, reached without
    passing through a symlink."""
    path = root / rel
    try:
        info = path.lstat()
    except OSError:
        return "missing"
    if not stat.S_ISREG(info.st_mode):
        return "not a regular file"
    if Path(os.path.realpath(path)) != path:
        return "reached through a symlink"
    return None if sha256(path) == expected else "content differs from Base"


def main() -> int:
    root = Path(os.path.realpath(sys.argv[1]))
    manifest_path, build_manifest_path, summary_path = (Path(p) for p in sys.argv[2:5])
    summary: dict[str, object] = {"passed": False}
    status = 4
    try:
        manifest = json.loads(manifest_path.read_text())
        files: dict[str, str] = manifest["files"]
        scope = re.compile(manifest["scope_pattern"])
        tests_prefix: str = manifest["tests_prefix"]
        if len(files) < 100:
            raise ValueError("base manifest is implausibly small")
        # Generated at image build: protected when built output or under a protected path.
        built: dict[str, str] = {}
        for line in build_manifest_path.read_text().splitlines():
            expected, rel = line.split("  ", 1)
            if DIST.search(rel) or scope.search(rel):
                built[rel] = expected
        if len(built) < 500:
            raise ValueError("build manifest is implausibly small")

        scope_modified, tests_modified = [], []
        for rel, expected in files.items():
            reason = problem(root, rel, expected)
            if reason:
                (tests_modified if rel.startswith(tests_prefix) else scope_modified).append(
                    f"{rel}: {reason}"
                )

        # Anything new under a protected path, whether git would list it or not.
        scope_added, new_test_files = [], []
        for current, dirs, names in os.walk(root, followlinks=False):
            rel_dir = os.path.relpath(current, root)
            rel_dir = "" if rel_dir == "." else rel_dir + "/"
            keep = []
            for name in dirs:
                rel = rel_dir + name
                if name in (".git", "node_modules") or DIST.search(rel + "/"):
                    continue
                if os.path.islink(os.path.join(current, name)):
                    if scope.search(rel + "/") or scope.search(rel):
                        scope_added.append(f"{rel}: symlinked directory")
                    continue
                keep.append(name)
            dirs[:] = keep
            for name in names:
                rel = rel_dir + name
                if rel in files or rel in built:
                    continue
                if scope.search(rel):
                    scope_added.append(rel)
                elif rel.startswith(tests_prefix) and re.search(r"\.(test|spec)\.[cm]?[jt]sx?$", name):
                    if Path(root / rel).is_file() and not Path(root / rel).is_symlink() and (root / rel).stat().st_size > 0:
                        new_test_files.append(rel)

        built_modified = []
        for rel, expected in built.items():
            reason = problem(root, rel, expected)
            if reason:
                built_modified.append(f"{rel}: {reason}")

        readme = root / "packages/coding-agent/examples/extensions/fork/README.md"
        missing_deliverables = []
        if not readme.is_file() or readme.is_symlink() or not readme.read_text().strip():
            missing_deliverables.append("nonempty README.md next to the extension")
        if not new_test_files:
            missing_deliverables.append("new offline unit test under packages/coding-agent/test/")

        status = (1 if scope_modified or scope_added or built_modified else 0) | (
            2 if tests_modified else 0
        ) | (8 if missing_deliverables else 0)
        summary.update(
            passed=status == 0,
            protected_files=len(files),
            built_files=len(built),
            scope_modified=sorted(scope_modified)[:LIMIT],
            scope_added=sorted(scope_added)[:LIMIT],
            built_modified=sorted(built_modified)[:LIMIT],
            tests_modified=sorted(tests_modified)[:LIMIT],
            new_test_files=sorted(new_test_files),
            missing_deliverables=missing_deliverables,
        )
    except (OSError, ValueError, KeyError) as error:
        summary["error"] = f"{type(error).__name__}: {error}"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
