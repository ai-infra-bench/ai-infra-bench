#!/usr/bin/env python3
"""Generate self-contained pi (earendil-works/pi) Harbor Dockerfiles from task metadata.

The rendered Dockerfile has no local COPY instructions, so it builds from an
empty context. Inputs come from task.toml, environment/lock/ and the optional
environment/pi-template.json runtime selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path

REPOSITORY = "earendil-works/pi"
TOKENS = {
    "base_commit": "__PI_BASE_SHA__",
    "dependency_cutoff": "__PI_DEPENDENCY_CUTOFF__",
    "cache_namespace": "__PI_CACHE_NAMESPACE__",
    "lock_sha256": "__PI_LOCK_SHA256__",
    "node_image": "__PI_NODE_IMAGE__",
    "create_agent_user": "__PI_CREATE_AGENT_USER__",
    "source_cli": "__PI_SOURCE_CLI__",
    "npm_ignore_scripts": "__PI_NPM_IGNORE_SCRIPTS__",
    "workspace": "__PI_WORKSPACE__",
    "build_manifest_check": "__PI_BUILD_MANIFEST_CHECK__",
    "workspace_label": "__PI_WORKSPACE_LABEL__",
}
AGENT_USER_TOKEN = "__PI_AGENT_USER__"
DEFAULT_NODE_IMAGE = "node:22.19.0-bookworm-slim@sha256:4a4884e8a44826194dff92ba316264f392056cbe243dcc9fd3551e71cea02b90"
NODE_IMAGES = {
    DEFAULT_NODE_IMAGE,
    "node:22.23.2-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5",
}
SHA_RE = re.compile(r"[0-9a-f]{40}")
CUTOFF_RE = re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
TEMPLATE_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEMPLATE_DIR.parents[1]
TEMPLATE_PATH = TEMPLATE_DIR / "Dockerfile"


def runtime_config(task_dir: Path) -> dict[str, str | bool]:
    """Allow only reviewed runtime images and non-root account names."""
    path = task_dir / "environment/pi-template.json"
    config = json.loads(path.read_text()) if path.is_file() else {}
    allowed = {"node_image", "agent_user", "source_cli", "npm_ignore_scripts", "workspace_mode"}
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError(f"{path}: expected an object with only {', '.join(sorted(allowed))}")
    options = {}
    for name in ("source_cli", "npm_ignore_scripts"):
        value = config.get(name, False)
        if type(value) is not bool:
            raise ValueError(f"{path}: {name} must be a boolean")
        options[name] = value
    workspace_mode = config.get("workspace_mode", "prebuilt")
    if workspace_mode not in ("prebuilt", "source"):
        raise ValueError(f"{path}: workspace_mode must be prebuilt or source")
    if workspace_mode == "source" and not (options["source_cli"] and options["npm_ignore_scripts"]):
        raise ValueError(f"{path}: source requires source_cli and npm_ignore_scripts")
    node_image = config.get("node_image", DEFAULT_NODE_IMAGE)
    agent_user = config.get("agent_user", "node")
    if not isinstance(node_image, str) or node_image not in NODE_IMAGES:
        raise ValueError(f"{path}: node_image must be a reviewed digest-pinned Node image")
    if agent_user not in ("node", "agent"):
        raise ValueError(f"{path}: agent_user must be node or agent")
    task = tomllib.loads((task_dir / "task.toml").read_text())
    if task.get("agent", {}).get("user") != agent_user:
        raise ValueError(f"{path}: agent_user must match task.toml [agent].user")
    return {"node_image": node_image, "agent_user": agent_user, "workspace_mode": workspace_mode, **options}


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
    # task.toml [metadata] carries only task_type, base_commit and dependency_cutoff; the lock
    # manifest records which repository the pinned checkout comes from.
    lock_manifest = json.loads((task_dir / "environment/lock/manifest.json").read_text())
    if lock_manifest.get("repository") != REPOSITORY:
        raise ValueError(f"{task_dir}: not an {REPOSITORY} task")
    base_commit = metadata_value(task_file, "base_commit")
    if SHA_RE.fullmatch(base_commit) is None:
        raise ValueError(f"{task_file}: base_commit must be 40 lowercase hex characters")
    dependency_cutoff = metadata_value(task_file, "dependency_cutoff")
    if CUTOFF_RE.fullmatch(dependency_cutoff) is None:
        raise ValueError(f"{task_file}: dependency_cutoff must be an RFC 3339 UTC timestamp")
    lock = lock_sha256(task_dir)
    runtime = runtime_config(task_dir)
    # Older manifests append human-readable platform digest notes after the image.
    recorded_image = lock_manifest.get("node_image", "")
    if not isinstance(recorded_image, str) or recorded_image.split(" ", 1)[0] != runtime["node_image"]:
        raise ValueError(f"{task_dir}: node_image differs from lock manifest")
    values = {
        "base_commit": base_commit,
        "dependency_cutoff": dependency_cutoff,
        "cache_namespace": f"{base_commit}-{lock[:16]}",
        "lock_sha256": lock,
        "node_image": runtime["node_image"],
        "create_agent_user": (
            "RUN useradd --create-home --shell /bin/bash agent\n"
            if runtime["agent_user"] == "agent" else ""
        ),
        "source_cli": (
            (TEMPLATE_DIR / "source-cli.Dockerfile").read_text()
            if runtime["source_cli"] else ""
        ),
        "npm_ignore_scripts": " --ignore-scripts" if runtime["npm_ignore_scripts"] else "",
        "workspace": (TEMPLATE_DIR / f"{runtime['workspace_mode']}-workspace.Dockerfile").read_text() + ("\n" if runtime["workspace_mode"] == "prebuilt" else ""),
        "build_manifest_check": (
            "test \"$(grep -c -E '  packages/ai/src/providers/data/[^/]+[.]json$' /opt/pi-baseline/build-manifest.sha256)\" -ge 40"
            if runtime["workspace_mode"] == "source" else
            "test \"$(grep -c -E '  packages/coding-agent/dist/' /opt/pi-baseline/build-manifest.sha256)\" -gt 500"
        ),
        "workspace_label": "LABEL ai.infra.bench.workspace-mode=source\n" if runtime["workspace_mode"] == "source" else "",
    }
    generated = template
    for key, token in TOKENS.items():
        generated = generated.replace(token, values[key])
    generated = generated.replace(AGENT_USER_TOKEN, runtime["agent_user"])
    return task_dir / "environment" / "Dockerfile", generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "task_dirs",
        nargs="+",
        type=Path,
        help="Task directories, absolute or relative to the repository root",
    )
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

    stale = False
    for raw in args.task_dirs:
        task_dir = raw if raw.is_absolute() else REPO_ROOT / raw
        output, generated = render(task_dir.resolve(), template)
        digest = hashlib.sha256(generated.encode()).hexdigest()
        if args.check:
            if not output.is_file() or output.read_text() != generated:
                print(f"STALE {output}", file=sys.stderr)
                stale = True
            else:
                print(f"OK {digest} {output}")
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(generated)
            print(f"WROTE {digest} {output}")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
