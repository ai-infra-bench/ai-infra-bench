#!/usr/bin/env python3
"""Build the pi-plan-mode image from its task-local recipe and record provenance.

The generated Dockerfile is checked against the template, built from an empty
context (so tests, the Oracle, and curator files cannot enter the image), and
described in environment/image-manifest.json, including the PASS_TO_PASS
baseline the image recorded at build time. No shared template is modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import tomllib

TEMPLATE_DIR = Path(__file__).resolve().parent
TASK_DIR = TEMPLATE_DIR.parents[1]
REPO_ROOT = TASK_DIR.parents[1]
TEMPLATE_PATH = TEMPLATE_DIR / "Dockerfile.template"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_task(task_dir: Path) -> tuple[dict, str]:
    metadata = tomllib.loads((task_dir / "task.toml").read_text())
    short_name = metadata["task"]["name"].rsplit("/", 1)[-1]
    base_commit = metadata["metadata"]["base_commit"]
    return metadata, f"ai-infra-bench/{short_name}:base-{base_commit[:12]}"


def run(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE if capture else None)


def build(task_dir: Path, platform: str | None, build_options: list[str]) -> None:
    task_dir = task_dir.resolve()
    metadata, tag = load_task(task_dir)
    dockerfile = task_dir / "environment" / "Dockerfile"
    if not dockerfile.is_file():
        raise FileNotFoundError(dockerfile)
    run(sys.executable, str(TEMPLATE_DIR / "generate.py"), "--check")

    platform_args = ["--platform", platform] if platform else []
    with tempfile.TemporaryDirectory(prefix="ai-infra-build-context-") as context:
        run(
            "docker",
            "buildx",
            "build",
            "--load",
            "--provenance=false",
            "--progress=plain",
            *build_options,
            *platform_args,
            "--tag",
            tag,
            "--file",
            str(dockerfile),
            context,
        )

    inspect = json.loads(run("docker", "image", "inspect", tag, capture=True).stdout)[0]
    labels = inspect["Config"].get("Labels") or {}
    expected_base = metadata["metadata"]["base_commit"]
    expected_cutoff = metadata["metadata"]["dependency_cutoff"]
    if labels.get("ai.infra.bench.base-commit") != expected_base:
        raise RuntimeError("built image has the wrong base-commit label")
    if labels.get("ai.infra.bench.dependency-cutoff") != expected_cutoff:
        raise RuntimeError("built image has the wrong dependency-cutoff label")
    if labels.get("ai.infra.bench.environment-template") != metadata["metadata"]["environment_template"]:
        raise RuntimeError("built image has the wrong environment-template label")

    probe = (
        "set -e; cd /workspace/pi;"
        ' printf \'{"node":"%s","npm":"%s","fd":"%s","ripgrep":"%s","python3":"%s","git":"%s","pi":"%s","baseline":%s}\\n\''
        ' "$(node --version | sed s/^v//)" "$(npm --version)" "$(fd --version | awk \'{print $2}\')"'
        " \"$(rg --version | head -1 | awk '{print $2}')\" \"$(python3 --version | awk '{print $2}')\""
        ' "$(git --version | awk \'{print $3}\')" "$(node -p "require(\'./packages/coding-agent/package.json\').version")"'
        ' "$(cat /opt/pi-baseline/summary.json)"'
    )
    probe_result = json.loads(
        run(
            "docker",
            "run",
            "--rm",
            "--network=none",
            *platform_args,
            tag,
            "bash",
            "-lc",
            probe,
            capture=True,
        ).stdout
    )
    baseline = probe_result.pop("baseline")
    versions = probe_result
    versions["pi"] = f"{versions['pi']} (workspace build)"

    lock_manifest_path = task_dir / "environment" / "lock" / "manifest.json"
    lock_manifest = json.loads(lock_manifest_path.read_text())
    lock_path = task_dir / lock_manifest["output"]["path"]
    manifest = {
        "schema_version": "pi_harbor_image.v1",
        "task": metadata["task"]["name"],
        "canonical_tag": tag,
        "image_id": inspect["Id"],
        "repo_digests": inspect.get("RepoDigests") or [],
        "platform": f"{inspect.get('Os')}/{inspect.get('Architecture')}",
        "size_bytes": inspect["Size"],
        "created": inspect["Created"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "base_commit": expected_base,
        "dependency_cutoff": expected_cutoff,
        "dockerfile_sha256": sha256_file(dockerfile),
        "template_sha256": sha256_file(TEMPLATE_PATH),
        "template_path": TEMPLATE_PATH.relative_to(task_dir).as_posix(),
        "dependency_lock_sha256": sha256_file(lock_path),
        "dependency_lock_manifest_sha256": sha256_file(lock_manifest_path),
        "build_context": "empty",
        "build_command": "python3 " + shlex.quote(Path(__file__).resolve().relative_to(REPO_ROOT).as_posix())
        + (f" --platform {platform}" if platform else "")
        + (" " + shlex.join(build_options) if build_options else ""),
        "cache_policy": {
            "shared": ["source-independent OCI layers"],
            "base_and_lock_scoped": ["npm ci from the pinned package-lock.json"],
            "namespace": labels.get("ai.infra.bench.cache-namespace"),
            "remote_cache_imported": False,
            "runtime_downloads": "none (fd and ripgrep preinstalled, PI_OFFLINE=1)",
        },
        "installed_versions": versions,
        "pass_to_pass_baseline": {
            "path": "/opt/pi-baseline/coding-agent-junit.xml",
            "tests": baseline["totals"]["tests"],
            "failures": baseline["totals"]["failures"],
            "errors": baseline["totals"]["errors"],
            "skipped": baseline["totals"]["skipped"],
            "failed_on_base": baseline["failed_on_base"],
            "note": "recorded on the unmodified Base inside the image; tests/baseline-pins.json pins its identity and the allowed failures",
        },
    }
    manifest_path = task_dir / "environment" / "image-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"RETAINED {tag} {inspect['Id']}")
    print(f"WROTE {manifest_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--platform", help="docker platform, e.g. linux/amd64 (CI's x64 runners); default: the host"
    )
    parser.add_argument("--builder", help="dedicated Buildx builder to use")
    parser.add_argument("--network", help="network used only during the image build")
    parser.add_argument("--allow", action="append", default=[], help="Buildx entitlement (repeatable)")
    parser.add_argument("--build-arg", action="append", default=[], help="non-secret build argument (repeatable)")
    args = parser.parse_args()
    build_options = []
    for key in ("builder", "network"):
        if getattr(args, key):
            build_options.extend([f"--{key}", getattr(args, key)])
    for key in ("allow", "build_arg"):
        for value in getattr(args, key):
            build_options.extend([f"--{key.replace('_', '-')}", value])
    build(TASK_DIR, args.platform, build_options)


if __name__ == "__main__":
    main()
