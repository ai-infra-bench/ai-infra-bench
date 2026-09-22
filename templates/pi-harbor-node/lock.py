#!/usr/bin/env python3
"""Materialize the dependency lock for one pi task.

pi's monorepo commits its own package-lock.json and the image installs from it
with `npm ci`, so the lock is the file at the base commit, copied verbatim, and
environment/lock/manifest.json records its sha256 for the generator, the
builder, and the repository audit. The Node image is selected from the template's reviewed runtime configuration.

    python3 templates/pi-harbor-node/lock.py tasks/<task>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

import tomllib

from generate import runtime_config

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = Path(__file__).resolve().parent
# task.toml [metadata] carries only task_type, base_commit and dependency_cutoff; the
# repository is the template's.
PI_REPOSITORY = "earendil-works/pi"
PI_REPO = "https://github.com/earendil-works/pi.git"


def generate(task_dir: Path) -> None:
    task_dir = task_dir.resolve()
    runtime = runtime_config(task_dir)
    config = tomllib.loads((task_dir / "task.toml").read_text())
    base_commit = config["metadata"]["base_commit"]
    cutoff = config["metadata"]["dependency_cutoff"]
    lock_dir = task_dir / "environment" / "lock"
    lock_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pi-lock-") as tmp:
        subprocess.run(["git", "init", "-q", tmp], check=True)
        subprocess.run(
            ["git", "-C", tmp, "fetch", "-q", "--depth", "1", "--no-tags", PI_REPO, base_commit],
            check=True,
        )
        lock_text = subprocess.run(
            ["git", "-C", tmp, "show", f"{base_commit}:package-lock.json"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout
    (lock_dir / "package-lock.json").write_text(lock_text)
    digest = hashlib.sha256(lock_text.encode()).hexdigest()

    node_image = runtime["node_image"]
    node_version = re.search(r"node:([0-9.]+)", node_image or "")

    manifest = {
        "schema_version": "pi_dependency_lock.v1",
        "resolver": f"npm (npm ci{' --ignore-scripts' if runtime['npm_ignore_scripts'] else ''} --no-audit --no-fund)",
        "repository": PI_REPOSITORY,
        "base_commit": base_commit,
        "dependency_cutoff": cutoff,
        "node_version": node_version.group(1) if node_version else None,
        "node_image": node_image,
        "inputs": {
            "package-lock.json": {
                "source": "package-lock.json at base_commit, unchanged",
                "sha256": digest,
            }
        },
        "output": {"path": "environment/lock/package-lock.json", "sha256": digest},
        "notes": [
            "The repository lock file at the base commit is used verbatim; npm ci resolves every package from it.",
            "Dependencies are npm registry artifacts published before the cutoff as pinned by the lock; no toolchain overrides needed.",
            "Model catalog: the Dockerfile takes packages/ai/src/providers/data from the published @earendil-works/pi-ai package of the base commit's release (PI_AI_VERSION / PI_AI_TARBALL_SHA256) and builds pi with network disabled; record that package under inputs with its publish time and, if it postdates the cutoff, why it reveals nothing after the base commit (templates/pi-harbor-node/README.md, 'Model catalog').",
        ],
    }
    (lock_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"WROTE {lock_dir / 'package-lock.json'} sha256:{digest}")
    print(f"WROTE {lock_dir / 'manifest.json'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_dirs", nargs="+", type=Path)
    args = parser.parse_args()
    for raw in args.task_dirs:
        generate(raw if raw.is_absolute() else REPO_ROOT / raw)


if __name__ == "__main__":
    main()
