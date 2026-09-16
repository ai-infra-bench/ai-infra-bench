"""Deterministic audit and pilot sampling for PR manifests."""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

BACKEND_PATTERNS = {
    "ascend_npu": re.compile(r"ascend|(^|[^a-z])npu([^a-z]|$)", re.I),
    "cambricon_mlu": re.compile(
        r"cambricon|(^|[^a-z])mlu([^a-z]|$)", re.I
    ),
    "amd_rocm": re.compile(r"rocm|(^|[^a-z])amd([^a-z]|$)", re.I),
    "intel_xpu": re.compile(
        r"(^|[^a-z])xpu([^a-z]|$)|intel.?gpu", re.I
    ),
    "nvidia_cuda": re.compile(r"cuda|nvidia", re.I),
    "cpu": re.compile(r"(^|[^a-z])cpu([^a-z]|$)", re.I),
}


def period(record: dict[str, Any]) -> str:
    """Map a PR to the preregistered reporting period."""
    timestamp = record.get("merged_at") or record.get("created_at")
    if not timestamp:
        raise ValueError("record needs merged_at or created_at")
    year = int(timestamp[:4])
    if year <= 2024:
        return "launch_through_2024"
    return str(year)


def patch_size(record: dict[str, Any]) -> str:
    """Assign a coarse churn stratum without treating churn as human effort."""
    additions = record.get("additions")
    deletions = record.get("deletions")
    if additions is None or deletions is None:
        return "unknown"
    churn = int(additions) + int(deletions)
    if churn <= 20:
        return "small"
    if churn <= 200:
        return "medium"
    return "large"


def stratified_sample(
    records: list[dict[str, Any]], *, count: int, seed: int
) -> list[dict[str, Any]]:
    """Sample as evenly as possible across reporting period and patch size."""
    if count < 1:
        raise ValueError("count must be positive")
    if count > len(records):
        raise ValueError("count cannot exceed the population")

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[(period(record), patch_size(record))].append(record)

    rng = random.Random(seed)
    for values in groups.values():
        rng.shuffle(values)

    selected: list[dict[str, Any]] = []
    active = sorted(groups)
    while len(selected) < count and active:
        next_active = []
        for key in active:
            values = groups[key]
            if values and len(selected) < count:
                record = values.pop()
                record = dict(record)
                record["sample"] = {
                    "kind": "period_patch_size_stratified",
                    "seed": seed,
                    "period": key[0],
                    "patch_size": key[1],
                }
                selected.append(record)
            if values:
                next_active.append(key)
        active = next_active
    return sorted(selected, key=lambda value: value["number"])


def sample_jsonl(
    input_path: Path, output_path: Path, *, count: int, seed: int
) -> int:
    """Read a manifest and write a deterministic stratified JSONL sample."""
    with input_path.open(encoding="utf-8") as stream:
        records = [json.loads(line) for line in stream if line.strip()]
    values = stratified_sample(records, count=count, seed=seed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True))
            stream.write("\n")
    return len(values)


def backend_keyword_sample(
    records: list[dict[str, Any]], *, per_backend: int, seed: int
) -> list[dict[str, Any]]:
    """Oversample explicit backend terms for taxonomy validation.

    Keyword matches are sampling hints, not ground-truth labels.
    """
    if per_backend < 1:
        raise ValueError("per_backend must be positive")
    rng = random.Random(seed)
    selected: dict[str, dict[str, Any]] = {}
    for backend, pattern in BACKEND_PATTERNS.items():
        candidates = []
        for record in records:
            text = " ".join(
                [record["title"], *(item["path"] for item in record["files"])]
            )
            if pattern.search(text):
                candidates.append(record)
        rng.shuffle(candidates)
        for original in candidates[:per_backend]:
            source_id = original["source_id"]
            record = selected.setdefault(source_id, dict(original))
            sample = record.setdefault(
                "sample",
                {
                    "kind": "backend_keyword_oversample",
                    "seed": seed,
                    "matched_backend_hints": [],
                },
            )
            sample["matched_backend_hints"].append(backend)
    return sorted(selected.values(), key=lambda value: value["number"])


def backend_sample_jsonl(
    input_path: Path,
    output_path: Path,
    *,
    per_backend: int,
    seed: int,
) -> int:
    """Read a manifest and write the backend-keyword audit sample."""
    with input_path.open(encoding="utf-8") as stream:
        records = [json.loads(line) for line in stream if line.strip()]
    values = backend_keyword_sample(
        records, per_backend=per_backend, seed=seed
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True))
            stream.write("\n")
    return len(values)
