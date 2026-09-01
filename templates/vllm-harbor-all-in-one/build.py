#!/usr/bin/env python3
"""Build and retain generated vLLM task images with provenance manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import tomllib

TEMPLATE_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEMPLATE_DIR.parents[1]


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


def build(task_dir: Path, builder: str | None = None) -> None:
    task_dir = task_dir.resolve()
    metadata, tag = load_task(task_dir)
    cutoff = datetime.fromisoformat(
        metadata["metadata"]["dependency_cutoff"].replace("Z", "+00:00")
    )
    source_date_epoch = str(int(cutoff.timestamp()))
    dockerfile = task_dir / "environment" / "Dockerfile"
    if not dockerfile.is_file():
        raise FileNotFoundError(dockerfile)

    run(
        "python3",
        str(TEMPLATE_DIR / "generate.py"),
        "--check",
        str(task_dir),
    )

    # The Dockerfile fetches its pinned source in a named stage and has no
    # local COPY instructions. An empty context makes it impossible for task
    # tests, the Oracle, or curator files to enter the image accidentally.
    with tempfile.TemporaryDirectory(prefix="ai-infra-build-context-") as context:
        build_command = ["docker", "buildx", "build"]
        if builder is not None:
            build_command.extend(["--builder", builder])
        build_command.extend(
            [
                "--load",
                "--provenance=false",
                "--progress=plain",
                "--build-arg",
                f"SOURCE_DATE_EPOCH={source_date_epoch}",
                "--tag",
                tag,
                "--file",
                str(dockerfile),
                context,
            ]
        )
        run(*build_command)

    inspect = json.loads(run("docker", "image", "inspect", tag, capture=True).stdout)[0]
    image_id = inspect["Id"]
    labels = inspect["Config"].get("Labels") or {}
    expected_base = metadata["metadata"]["base_commit"]
    expected_cutoff = metadata["metadata"]["dependency_cutoff"]
    if labels.get("ai.infra.bench.base-commit") != expected_base:
        raise RuntimeError("built image has the wrong base-commit label")
    if labels.get("ai.infra.bench.dependency-cutoff") != expected_cutoff:
        raise RuntimeError("built image has the wrong dependency-cutoff label")

    versions = json.loads(
        run(
            "docker",
            "run",
            "--rm",
            "--network=none",
            tag,
            "python",
            "-c",
            (
                "import importlib.metadata as m,json;"
                "ds={(d.metadata.get('Name') or '').lower():d.version "
                "for d in m.distributions()};"
                "print(json.dumps({k:ds.get(k) for k in "
                "['vllm','torch','av','opencv-python-headless','numpy','pytest','ray']}))"
            ),
            capture=True,
        ).stdout
    )

    task_metadata = metadata["metadata"]
    runtime_assets = None
    if task_metadata.get("runtime_asset_repository"):
        runtime_assets = {
            "repository": task_metadata["runtime_asset_repository"],
            "revision": task_metadata["runtime_asset_revision"],
            "path": task_metadata["runtime_asset_path"],
            "files": [
                item.strip()
                for item in task_metadata["runtime_asset_files"].split(",")
            ],
            "model_tensors_included": False,
        }
    runtime_file = None
    if task_metadata.get("runtime_file_url"):
        runtime_file = {
            "url": task_metadata["runtime_file_url"],
            "sha256": task_metadata["runtime_file_sha256"],
            "path": task_metadata["runtime_file_path"],
            "license": task_metadata["runtime_file_license"],
            "attribution": task_metadata["runtime_file_attribution"],
        }

    manifest = {
        "schema_version": "vllm_harbor_image.v1",
        "task": metadata["task"]["name"],
        "canonical_tag": tag,
        "image_id": image_id,
        "repo_digests": inspect.get("RepoDigests") or [],
        "size_bytes": inspect["Size"],
        "created": inspect["Created"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "base_commit": expected_base,
        "dependency_cutoff": expected_cutoff,
        "runtime_assets": runtime_assets,
        "runtime_file": runtime_file,
        "dockerfile_sha256": sha256_file(dockerfile),
        "template_sha256": sha256_file(TEMPLATE_DIR / "Dockerfile"),
        "dependency_lock_sha256": (
            sha256_file(task_dir / "environment" / "lock" / "requirements.txt")
            if (task_dir / "environment" / "lock" / "requirements.txt").is_file()
            else None
        ),
        "dependency_lock_manifest_sha256": (
            sha256_file(task_dir / "environment" / "lock" / "manifest.json")
            if (task_dir / "environment" / "lock" / "manifest.json").is_file()
            else None
        ),
        "build_context": "empty",
        "cache_policy": {
            "shared": ["source-independent OCI layers", "uv download cache"],
            "base_lock_and_template_scoped": ["ccache", "CMake FetchContent"],
            "namespace": labels.get("ai.infra.bench.cache-namespace"),
            "remote_cache_imported": False,
        },
        "installed_versions": versions,
    }
    manifest_path = task_dir / "environment" / "image-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"RETAINED {tag} {image_id}")
    print(f"WROTE {manifest_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--builder",
        help="Optional buildx builder name; useful for clean-cache audits.",
    )
    parser.add_argument("task_dirs", nargs="+", type=Path)
    args = parser.parse_args()
    for raw in args.task_dirs:
        task_dir = raw if raw.is_absolute() else REPO_ROOT / raw
        build(task_dir, builder=args.builder)


if __name__ == "__main__":
    main()
