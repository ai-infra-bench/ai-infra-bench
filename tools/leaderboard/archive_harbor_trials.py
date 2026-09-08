#!/usr/bin/env python3
"""Archive completed Harbor trial directories in a task-first NAS layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import tomllib


SAFE_SEGMENT = re.compile(r"[^A-Za-z0-9._-]+")


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object in {path}")
    return value


def safe_segment(value: str) -> str:
    cleaned = SAFE_SEGMENT.sub("-", value).strip("-.")
    if not cleaned or cleaned in {".", ".."}:
        raise RuntimeError(f"unsafe empty path segment derived from {value!r}")
    return cleaned


def model_effort(config: dict) -> str:
    config_path = config.get("agent", {}).get("kwargs", {}).get("config")
    if not isinstance(config_path, str):
        raise RuntimeError("trial config does not identify the Codex config")
    try:
        parsed = tomllib.loads(Path(config_path).read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise RuntimeError(f"cannot read model config {config_path}: {error}") from error
    effort = parsed.get("model_reasoning_effort")
    if not isinstance(effort, str) or not effort:
        raise RuntimeError(f"model config has no reasoning effort: {config_path}")
    return effort


def digest_tree(root: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    total_size = 0
    file_count = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(oct(stat.S_IMODE(metadata.st_mode)).encode())
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"L\0")
            digest.update(os.readlink(path).encode())
            continue
        if path.is_dir():
            digest.update(b"D\0")
            continue
        if path.is_file():
            digest.update(b"F\0")
            total_size += metadata.st_size
            file_count += 1
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            continue
        raise RuntimeError(f"unsupported filesystem entry: {path}")
    return digest.hexdigest(), total_size, file_count


def trajectory_integrity(trial: Path) -> tuple[bool, list[str]]:
    path = trial / "agent/trajectory.json"
    if not path.is_file():
        return False, ["missing_trajectory"]
    trajectory = read_json(path)
    reasons: list[str] = []
    if not trajectory.get("final_metrics"):
        reasons.append("missing_final_metrics")
    if any(
        "<turn_aborted>" in str(step.get("message") or "")
        for step in trajectory.get("steps", [])
        if isinstance(step, dict)
    ):
        reasons.append("turn_aborted")
    return not reasons, reasons


def archive_trial(
    trial: Path,
    job: Path,
    release: str,
    root: Path,
) -> str:
    result = read_json(trial / "result.json")
    if not result.get("finished_at"):
        return "incomplete"
    config = read_json(trial / "config.json")

    raw_task = result.get("task_name")
    if not isinstance(raw_task, str):
        raw_task = str(config.get("task", {}).get("path", "")).rstrip("/").rsplit("/", 1)[-1]
    task = safe_segment(raw_task.removeprefix("ai-infra-bench/"))
    model = safe_segment(str(config.get("agent", {}).get("model_name", "")))
    effort = safe_segment(model_effort(config))
    agent_name = safe_segment(str(config.get("agent", {}).get("name", "agent")))
    agent_version = safe_segment(str(config.get("agent", {}).get("kwargs", {}).get("version", "unknown")))
    agent = f"{agent_name}-{agent_version}"
    trial_name = safe_segment(trial.name)

    relative = Path(release) / task / model / effort / agent / trial_name
    destination = root / "archive" / relative
    manifest_path = root / "manifests" / relative.parent / f"{trial_name}.json"
    source_digest, source_size, source_files = digest_tree(trial)

    if destination.exists():
        destination_digest, destination_size, destination_files = digest_tree(destination)
        if (destination_digest, destination_size, destination_files) != (
            source_digest,
            source_size,
            source_files,
        ):
            raise RuntimeError(f"existing archive differs from source: {destination}")
        action = "verified"
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.parent / f".{trial_name}.tmp-{os.getpid()}-{time.time_ns()}"
        if temporary.exists():
            raise RuntimeError(f"temporary path already exists: {temporary}")
        try:
            subprocess.run(
                ["rsync", "-a", "--", f"{trial}/", f"{temporary}/"],
                check=True,
            )
            copied_digest, copied_size, copied_files = digest_tree(temporary)
            if (copied_digest, copied_size, copied_files) != (
                source_digest,
                source_size,
                source_files,
            ):
                raise RuntimeError(f"archive verification failed for {trial}")
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        action = "archived"

    trajectory_ok, trajectory_reasons = trajectory_integrity(trial)
    exception = result.get("exception_info")
    status_value = "valid" if exception is None and trajectory_ok else "excluded"
    manifest = {
        "schema_version": "ai_infra_bench_harbor_archive.v1",
        "release": release,
        "task": task,
        "model": model,
        "reasoning_effort": effort,
        "agent": agent_name,
        "agent_version": agent_version,
        "trial_name": trial.name,
        "task_checksum": result.get("task_checksum"),
        "status": status_value,
        "exclusion_reasons": [
            *(trajectory_reasons if not trajectory_ok else []),
            *([str(exception.get("exception_type", "exception"))] if isinstance(exception, dict) else []),
        ],
        "reward": (result.get("verifier_result") or {}).get("rewards", {}).get("reward"),
        "started_at": result.get("started_at"),
        "finished_at": result.get("finished_at"),
        "source_job": str(job.resolve()),
        "source_trial": str(trial.resolve()),
        "archive_trial": str(destination),
        "tree_sha256": source_digest,
        "size_bytes": source_size,
        "file_count": source_files,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_manifest = manifest_path.with_name(f".{manifest_path.name}.{os.getpid()}.tmp")
    temporary_manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary_manifest.chmod(0o644)
    os.replace(temporary_manifest, manifest_path)
    manifest_path.chmod(0o644)
    print(f"{action}\t{relative}\t{source_size}", flush=True)
    return action


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/mnt/nas/ai-infra-bench/leaderboard"),
    )
    parser.add_argument("jobs", nargs="+", type=Path)
    args = parser.parse_args()

    release = safe_segment(args.release)
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    counts = {"archived": 0, "verified": 0, "incomplete": 0}
    for job in args.jobs:
        job = job.resolve()
        if not job.is_dir():
            raise RuntimeError(f"not a Harbor job directory: {job}")
        for trial in sorted(job.iterdir()):
            if not trial.is_dir() or not (trial / "config.json").is_file():
                continue
            action = archive_trial(trial, job, release, root)
            counts[action] += 1
    print(json.dumps({"release": release, "root": str(root), **counts}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
