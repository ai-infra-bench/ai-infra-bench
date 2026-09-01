#!/usr/bin/env python3
"""Generate self-contained vLLM Harbor Dockerfiles from task metadata."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shlex
import sys
from pathlib import Path

TOKEN = "__VLLM_BASE_SHA__"
CUTOFF_TOKEN = "__VLLM_DEPENDENCY_CUTOFF__"
DEPENDENCY_INSTALL_TOKEN = "__VLLM_DEPENDENCY_INSTALL__"
CACHE_NAMESPACE_TOKEN = "__VLLM_CACHE_NAMESPACE__"
SHA_RE = re.compile(r"[0-9a-f]{40}")
CUTOFF_RE = re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
TEMPLATE_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEMPLATE_DIR.parents[1]
TEMPLATE_PATH = TEMPLATE_DIR / "Dockerfile"
ASSET_INSERTION_MARKER = (
    "LABEL ai.infra.bench.environment-template=vllm-harbor-all-in-one \\\n"
)


def metadata_value(task_file: Path, key: str) -> str:
    text = task_file.read_text()
    section_match = re.search(
        r"(?ms)^\[metadata\][ \t]*\n(.*?)(?=^\[|\Z)",
        text,
    )
    if section_match is None:
        raise ValueError(f"{task_file}: missing [metadata] section")
    value_match = re.search(
        rf'(?m)^{re.escape(key)}[ \t]*=[ \t]*"([^"]+)"[ \t]*$',
        section_match.group(1),
    )
    if value_match is None:
        raise ValueError(f"{task_file}: missing string metadata.{key}")
    return value_match.group(1)


def optional_metadata_value(task_file: Path, key: str) -> str | None:
    text = task_file.read_text()
    section_match = re.search(
        r"(?ms)^\[metadata\][ \t]*\n(.*?)(?=^\[|\Z)",
        text,
    )
    if section_match is None:
        raise ValueError(f"{task_file}: missing [metadata] section")
    value_match = re.search(
        rf'(?m)^{re.escape(key)}[ \t]*=[ \t]*"([^"]+)"[ \t]*$',
        section_match.group(1),
    )
    return value_match.group(1) if value_match is not None else None


def runtime_asset_install(task_file: Path) -> str:
    keys = (
        "runtime_asset_repository",
        "runtime_asset_revision",
        "runtime_asset_path",
        "runtime_asset_files",
    )
    values = {key: optional_metadata_value(task_file, key) for key in keys}
    if not any(values.values()):
        return ""
    if not all(values.values()):
        missing = ", ".join(key for key, value in values.items() if value is None)
        raise ValueError(f"{task_file}: incomplete runtime asset metadata: {missing}")

    repository = values["runtime_asset_repository"]
    revision = values["runtime_asset_revision"]
    asset_path = values["runtime_asset_path"]
    raw_files = values["runtime_asset_files"]
    assert repository is not None
    assert revision is not None
    assert asset_path is not None
    assert raw_files is not None

    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise ValueError(f"{task_file}: invalid runtime asset repository")
    if SHA_RE.fullmatch(revision) is None:
        raise ValueError(f"{task_file}: runtime asset revision must be a commit SHA")
    if re.fullmatch(r"/opt/[A-Za-z0-9_./-]+", asset_path) is None or ".." in asset_path:
        raise ValueError(f"{task_file}: invalid runtime asset path")

    files = [item.strip() for item in raw_files.split(",")]
    if not files or any(
        not item or re.fullmatch(r"[A-Za-z0-9_.-]+", item) is None for item in files
    ):
        raise ValueError(f"{task_file}: invalid runtime asset file list")
    forbidden_suffixes = (".bin", ".gguf", ".pt", ".pth", ".safetensors")
    if any(item.endswith(forbidden_suffixes) for item in files):
        raise ValueError(f"{task_file}: model tensor files are forbidden runtime assets")

    python_files = repr(files)
    checks = (" \\" + "\n && ").join(
        f"test -f {shlex.quote(asset_path + '/' + item)}" for item in files
    )
    return f"""# Optional task-scoped runtime metadata, pinned before the task base commit.
# Only the allow-listed files are downloaded; model tensors are forbidden.
RUN python - <<'VLLM_RUNTIME_ASSET_EOF'
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id={repository!r},
    revision={revision!r},
    local_dir={asset_path!r},
    allow_patterns={python_files},
)
VLLM_RUNTIME_ASSET_EOF
RUN rm -rf {shlex.quote(asset_path + '/.cache')} /root/.cache/huggingface \\
 && {checks} \\
 && test -z "$(find {shlex.quote(asset_path)} -type f \\
      \\( -name '*.bin' -o -name '*.gguf' -o -name '*.pt' -o -name '*.pth' -o -name '*.safetensors' \\) \\
      -print -quit)"
LABEL ai.infra.bench.runtime-asset-repository={repository} \\
      ai.infra.bench.runtime-asset-revision={revision}

"""


def runtime_file_install(task_file: Path) -> str:
    keys = (
        "runtime_file_url",
        "runtime_file_sha256",
        "runtime_file_path",
        "runtime_file_license",
        "runtime_file_attribution",
    )
    values = {key: optional_metadata_value(task_file, key) for key in keys}
    if not any(values.values()):
        return ""
    if not all(values.values()):
        missing = ", ".join(key for key, value in values.items() if value is None)
        raise ValueError(f"{task_file}: incomplete runtime file metadata: {missing}")

    url = values["runtime_file_url"]
    digest = values["runtime_file_sha256"]
    file_path = values["runtime_file_path"]
    license_name = values["runtime_file_license"]
    attribution = values["runtime_file_attribution"]
    cache_env = optional_metadata_value(task_file, "runtime_file_cache_env")
    assert url is not None
    assert digest is not None
    assert file_path is not None
    assert license_name is not None
    assert attribution is not None

    if re.fullmatch(r"https://[A-Za-z0-9_./?&=%:+~-]+", url) is None:
        raise ValueError(f"{task_file}: invalid runtime file URL")
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError(f"{task_file}: runtime file SHA-256 must be 64 lowercase hex")
    if re.fullmatch(r"/opt/[A-Za-z0-9_./-]+", file_path) is None or ".." in file_path:
        raise ValueError(f"{task_file}: invalid runtime file path")
    if any(char in license_name + attribution for char in "\r\n"):
        raise ValueError(f"{task_file}: runtime file attribution must be one line")
    if cache_env is not None and re.fullmatch(r"[A-Z][A-Z0-9_]*", cache_env) is None:
        raise ValueError(f"{task_file}: invalid runtime file cache environment variable")

    parent = file_path.rsplit("/", 1)[0]
    attribution_path = f"{parent}/ATTRIBUTION.txt"
    cache_env_line = f"ENV {cache_env}={parent}\n" if cache_env is not None else ""
    return f"""# Optional task-scoped runtime fixture with pinned content and license metadata.
RUN mkdir -p {shlex.quote(parent)} \\
 && curl --http1.1 -L --retry 10 --retry-all-errors --connect-timeout 30 --max-time 600 \\
      --proto '=https' --tlsv1.2 -sSf {shlex.quote(url)} -o {shlex.quote(file_path)} \\
 && printf '%s  %s\\n' {shlex.quote(digest)} {shlex.quote(file_path)} | sha256sum -c - \\
 && printf '%s\\n' \\
      {shlex.quote('Source: ' + url)} \\
      {shlex.quote('License: ' + license_name)} \\
      {shlex.quote('Attribution: ' + attribution)} \\
      > {shlex.quote(attribution_path)}
{cache_env_line}LABEL ai.infra.bench.runtime-file-source={json.dumps(url)} \\
      ai.infra.bench.runtime-file-sha256={digest} \\
      ai.infra.bench.runtime-file-license={json.dumps(license_name)}

"""


def reproduction_install(task_dir: Path) -> str:
    """Embed task-owned reproduction files without exposing the build context."""
    source_dir = task_dir / "environment" / "repro"
    if not source_dir.exists():
        return ""
    if not source_dir.is_dir():
        raise ValueError(f"{source_dir}: reproduction path must be a directory")

    files = sorted(path for path in source_dir.rglob("*") if path.is_file())
    if not files:
        raise ValueError(f"{source_dir}: reproduction directory is empty")

    allowed_suffixes = {".json", ".py", ".rs", ".sh", ".txt"}
    source_root = source_dir.resolve()
    commands = ["RUN install -d /opt/repro"]
    for path in files:
        relative = path.relative_to(source_dir)
        if path.is_symlink() or not path.resolve().is_relative_to(source_root):
            raise ValueError(f"{path}: reproduction files must not use symlinks")
        if path.suffix not in allowed_suffixes:
            raise ValueError(f"{path}: unsupported reproduction file type")
        if any(part in {"tests", "solution", "validation", ".."} for part in relative.parts):
            raise ValueError(f"{path}: forbidden reproduction path component")
        content = path.read_bytes()
        if len(content) > 256 * 1024:
            raise ValueError(f"{path}: reproduction file exceeds 256 KiB")
        destination = Path("/opt/repro") / relative
        encoded = base64.b64encode(content).decode("ascii")
        commands.append(
            f" && install -d {shlex.quote(str(destination.parent))}"
            f" \\\n && printf '%s' {shlex.quote(encoded)} | base64 -d > {shlex.quote(str(destination))}"
        )
        if path.suffix == ".sh":
            commands.append(f" \\\n && chmod 0755 {shlex.quote(str(destination))}")
    commands.append("\n")
    return "".join(commands)


def render(task_dir: Path, template: str) -> tuple[Path, str]:
    task_file = task_dir / "task.toml"
    if metadata_value(task_file, "repository") != "vllm-project/vllm":
        raise ValueError(f"{task_file}: not a vllm-project/vllm task")

    base_commit = metadata_value(task_file, "base_commit")
    if SHA_RE.fullmatch(base_commit) is None:
        raise ValueError(
            f"{task_file}: base_commit must be 40 lowercase hex characters"
        )

    dependency_cutoff = metadata_value(task_file, "dependency_cutoff")
    if CUTOFF_RE.fullmatch(dependency_cutoff) is None:
        raise ValueError(
            f"{task_file}: dependency_cutoff must be an RFC 3339 UTC timestamp"
        )

    environment_digest = hashlib.sha256(template.encode()).hexdigest()[:16]

    lock_path = task_dir / "environment" / "lock" / "requirements.txt"
    if lock_path.is_file():
        lock = lock_path.read_text().rstrip()
        lock_digest = hashlib.sha256((lock + "\n").encode()).hexdigest()
        cache_namespace = f"{base_commit}-{lock_digest[:16]}-{environment_digest}"
        dependency_install = f"""# Exact task dependency lock (sha256:{lock_digest}) is embedded so this
# Dockerfile remains independently buildable with an empty context.
RUN --mount=type=cache,id=vllm-uv-downloads-v3,target=/root/.cache/uv,sharing=locked <<'VLLM_INSTALL_EOF'
set -eu
cat > /tmp/vllm-requirements.lock <<'VLLM_REQUIREMENTS_EOF'
{lock}
VLLM_REQUIREMENTS_EOF
uv pip install --system --index-strategy first-index \\
  --torch-backend cpu -r /tmp/vllm-requirements.lock
rm -f /tmp/vllm-requirements.lock
VLLM_INSTALL_EOF"""
    else:
        cache_namespace = (
            f"{base_commit}-unlocked-{dependency_cutoff[:10]}-{environment_digest}"
        )
        dependency_install = """# Fallback for staged tasks whose exact lock has not been materialized yet.
# Resolution is bounded by the base timestamp; release builds require a lock.
COPY --from=source /src/vllm/requirements/ /tmp/vllm-requirements/
RUN --mount=type=cache,id=vllm-uv-downloads-v3,target=/root/.cache/uv,sharing=locked \\
    uv pip install --system \\
      --exclude-newer \"$VLLM_DEPENDENCY_CUTOFF\" \\
      --index-strategy unsafe-best-match \\
      -r /tmp/vllm-requirements/cpu.txt \\
      -r /tmp/vllm-requirements/build/cpu.txt \\
      --torch-backend cpu \\
 && uv pip install --system \\
      --exclude-newer \"$VLLM_DEPENDENCY_CUTOFF\" \\
      --index-strategy unsafe-best-match \\
      'setuptools-rust>=1.9.0' av==16.1.0 \\
      pytest pytest-asyncio pytest-forked \\
      pytest-rerunfailures pytest-shard pytest-timeout pytest-cov tblib \\
 && rm -rf /tmp/vllm-requirements"""

    output = task_dir / "environment" / "Dockerfile"
    generated = template.replace(TOKEN, base_commit).replace(
        CUTOFF_TOKEN, dependency_cutoff
    ).replace(DEPENDENCY_INSTALL_TOKEN, dependency_install).replace(
        CACHE_NAMESPACE_TOKEN, cache_namespace
    )
    asset_install = (
        runtime_asset_install(task_file)
        + runtime_file_install(task_file)
        + reproduction_install(task_dir)
    )
    if asset_install:
        if generated.count(ASSET_INSERTION_MARKER) != 1:
            raise ValueError(
                f"{TEMPLATE_PATH}: expected exactly one runtime asset insertion marker"
            )
        generated = generated.replace(
            ASSET_INSERTION_MARKER,
            asset_install + ASSET_INSERTION_MARKER,
        )
    return output, generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "task_dirs",
        nargs="+",
        type=Path,
        help="Task directories, absolute or relative to the repository root",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if a generated Dockerfile is missing or stale",
    )
    args = parser.parse_args()

    template = TEMPLATE_PATH.read_text()
    if template.count(TOKEN) != 1:
        raise ValueError(f"{TEMPLATE_PATH}: expected exactly one {TOKEN} token")
    if template.count(CUTOFF_TOKEN) != 1:
        raise ValueError(f"{TEMPLATE_PATH}: expected exactly one {CUTOFF_TOKEN} token")
    if template.count(DEPENDENCY_INSTALL_TOKEN) != 1:
        raise ValueError(
            f"{TEMPLATE_PATH}: expected exactly one {DEPENDENCY_INSTALL_TOKEN} token"
        )
    if template.count(CACHE_NAMESPACE_TOKEN) != 1:
        raise ValueError(
            f"{TEMPLATE_PATH}: expected exactly one {CACHE_NAMESPACE_TOKEN} token"
        )

    stale = False
    for raw_task_dir in args.task_dirs:
        task_dir = (
            raw_task_dir if raw_task_dir.is_absolute() else REPO_ROOT / raw_task_dir
        )
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
