#!/usr/bin/env python3
"""Build and retain generated vLLM task images with provenance manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import tomllib

TEMPLATE_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEMPLATE_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))
from normalize_image_manifests import check_file_hashes, normalize_manifest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_task(task_dir: Path) -> tuple[dict, str]:
    metadata = tomllib.loads((task_dir / "task.toml").read_text())
    task_name = metadata["task"]["name"]
    short_name = task_name.rsplit("/", 1)[-1]
    base_commit = metadata["metadata"]["base_commit"]
    tag = f"ai-infra-bench/{short_name}:base-{base_commit[:12]}"
    return metadata, tag


def run(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )


def build(task_dir: Path) -> None:
    task_dir = task_dir.resolve()
    metadata, tag = load_task(task_dir)
    dockerfile = task_dir / "environment" / "Dockerfile"
    if not dockerfile.is_file():
        raise FileNotFoundError(dockerfile)

    run(
        "python3",
        str(TEMPLATE_DIR / "generate.py"),
        "--check",
        str(task_dir),
    )

    input_hashes = {
        "Dockerfile": sha256_file(dockerfile),
        "lock/requirements.txt": sha256_file(task_dir / "environment/lock/requirements.txt"),
        "lock/manifest.json": sha256_file(task_dir / "environment/lock/manifest.json"),
    }

    # The Dockerfile fetches its pinned source in a named stage and has no
    # local COPY instructions. An empty context makes it impossible for task
    # tests, the Oracle, or curator files to enter the image accidentally.
    with tempfile.TemporaryDirectory(prefix="ai-infra-build-context-") as context:
        run(
            "docker",
            "buildx",
            "build",
            "--load",
            "--provenance=false",
            "--progress=plain",
            "--tag",
            tag,
            "--file",
            str(dockerfile),
            context,
        )

    inspect = json.loads(run("docker", "image", "inspect", tag, capture=True).stdout)[0]
    image_id = inspect["Id"]
    labels = inspect["Config"].get("Labels") or {}
    expected_base = metadata["metadata"]["base_commit"]
    expected_cutoff = metadata["metadata"]["dependency_cutoff"]
    if labels.get("ai.infra.bench.base-commit") != expected_base:
        raise RuntimeError("built image has the wrong base-commit label")
    if labels.get("ai.infra.bench.dependency-cutoff") != expected_cutoff:
        raise RuntimeError("built image has the wrong dependency-cutoff label")

    manifest = normalize_manifest({"image_id": image_id, "files": input_hashes})
    check_file_hashes(manifest, task_dir / "environment")
    manifest_path = task_dir / "environment" / "image-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"RETAINED {tag} {image_id}")
    print(f"WROTE {manifest_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_dirs", nargs="+", type=Path)
    args = parser.parse_args()
    for raw in args.task_dirs:
        task_dir = raw if raw.is_absolute() else REPO_ROOT / raw
        build(task_dir)


if __name__ == "__main__":
    main()
