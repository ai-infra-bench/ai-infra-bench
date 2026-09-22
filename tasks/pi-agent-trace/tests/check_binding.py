#!/usr/bin/env python3
"""Validate curator binding identity without executing candidate or adapter code."""
import hashlib
import json
import sys
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root, manifest_path, adapter):
    if manifest_path.is_symlink() or adapter.is_symlink():
        raise ValueError("binding inputs must be regular curator-owned files")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != "pi-agent-trace-binding.v1":
        raise ValueError("unsupported binding schema")
    if manifest.get("adapter_sha256") != digest(adapter):
        raise ValueError("binding module hash mismatch")
    files = manifest.get("candidate_files")
    if not isinstance(files, dict) or not files:
        raise ValueError("candidate file inventory missing")
    extension = "packages/coding-agent/examples/extensions/agent-trace/index.ts"
    readme = "packages/coding-agent/examples/extensions/agent-trace/README.md"
    # Base and intentionally incomplete controls still require an explicit reviewer decision.
    if manifest.get("kind") not in ("documented", "base", "incomplete-control"):
        raise ValueError("unknown binding kind")
    if extension not in files or readme not in files:
        raise ValueError("binding must identify extension and README (null if absent)")
    if not manifest.get("readme_evidence"):
        raise ValueError("public API evidence or explicit missing-feature rationale required")
    for rel, expected in files.items():
        path = root / rel
        if Path(rel).is_absolute() or ".." in Path(rel).parts or path.is_symlink():
            raise ValueError("unsafe candidate identity path")
        if expected is None:
            if path.exists():
                raise ValueError(f"unexpected candidate file: {rel}")
        elif not path.is_file() or digest(path) != expected:
            raise ValueError(f"candidate file hash mismatch: {rel}")
    return manifest


def main():
    root, manifest_path, adapter, failure = map(Path, sys.argv[1:5])
    try:
        validate(root, manifest_path, adapter)
        failure.unlink(missing_ok=True)
        print("reviewed child binding identity verified")
        return 0
    except (OSError, ValueError, TypeError) as exc:
        failure.parent.mkdir(parents=True, exist_ok=True)
        failure.write_text(json.dumps({"status": "integration_needed", "error": str(exc), "reward": None}, indent=2) + "\n")
        print(f"integration needed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
