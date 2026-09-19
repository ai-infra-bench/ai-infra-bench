"""Read task-scoped build inputs kept outside Harbor task metadata."""

import json
from pathlib import Path


STRING_FIELDS = {
    "runtime_asset_repository", "runtime_asset_revision", "runtime_asset_path",
    "runtime_asset_files", "runtime_file_url", "runtime_file_sha256",
    "runtime_file_path", "runtime_file_license", "runtime_file_attribution",
    "runtime_file_cache_env",
}


def load_build_config(task_dir: Path) -> dict:
    path = task_dir / "environment/build-config.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("schema_version") != "vllm_build_config.v1":
        raise ValueError(f"{path}: unsupported build config schema")
    unknown = data.keys() - STRING_FIELDS - {"schema_version", "dependency_cutoff_overrides"}
    if unknown:
        raise ValueError(f"{path}: unknown build inputs: {sorted(unknown)}")
    for key in STRING_FIELDS & data.keys():
        if not isinstance(data[key], str) or not data[key]:
            raise ValueError(f"{path}: {key} must be a non-empty string")
    overrides = data.get("dependency_cutoff_overrides", [])
    if not isinstance(overrides, list) or not all(isinstance(x, str) and x for x in overrides):
        raise ValueError(f"{path}: dependency_cutoff_overrides must be a list of strings")
    return data
