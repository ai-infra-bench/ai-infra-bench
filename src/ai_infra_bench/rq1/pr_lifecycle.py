"""Derive cutoff-aware PR lifecycle metrics from the frozen base census."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

from ai_infra_bench.rq1.taxonomy import Classification

MAINTAINER_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


def derive_pr_lifecycle(
    labels_path: Path,
    manifest_path: Path,
    github_prs_path: Path,
    *,
    cutoff: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return per-PR lifecycle records and descriptive human-PR summaries."""
    labels = _load_unique_jsonl(labels_path)
    manifests = _load_unique_jsonl(manifest_path)
    github_prs = _load_unique_jsonl(github_prs_path)
    _require_same_population(labels, manifests, github_prs)
    cutoff_at = _parse_time(cutoff)

    records = [
        _derive_record(
            labels[source_id],
            manifests[source_id],
            github_prs[source_id],
            cutoff_at,
        )
        for source_id in labels
    ]
    records.sort(key=lambda record: record["number"])
    human = [record for record in records if record["author_group"] != "bot"]

    periods = sorted({record["period"] for record in human})
    subsystems = sorted(
        {
            subsystem
            for record in human
            for subsystem in record["subsystems"]
        }
    )
    summary = {
        "metadata": {
            "snapshot_cutoff": cutoff,
            "classification_unit": "pull_request",
            "duration_unit": "days",
            "quantile_method": "linear interpolation over observed outcomes",
            "censoring_note": (
                "Closed-only duration distributions are descriptive. "
                "Open PRs are right-censored and closed-unmerged PRs are a "
                "competing outcome for time to merge."
            ),
            "response_metrics_available": False,
        },
        "population": {
            "all_prs": len(records),
            "human_prs": len(human),
            "bot_prs": len(records) - len(human),
            "human_status_at_cutoff": _status_counts(human),
            "human_author_group": dict(
                sorted(Counter(r["author_group"] for r in human).items())
            ),
        },
        "human_outcome_durations": _duration_summary(human),
        "human_by_period": {
            period: _group_summary(
                [record for record in human if record["period"] == period]
            )
            for period in periods
        },
        "human_by_author_group": {
            group: _group_summary(
                [record for record in human if record["author_group"] == group]
            )
            for group in ("maintainer", "external")
        },
        "human_by_subsystem": {
            subsystem: _group_summary(
                [
                    record
                    for record in human
                    if subsystem in record["subsystems"]
                ]
            )
            for subsystem in subsystems
        },
    }
    return records, summary


def write_pr_lifecycle(
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    *,
    records_output: Path,
    summary_output: Path,
) -> None:
    """Write stable JSONL records and a JSON summary."""
    records_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    with records_output.open("w", encoding="utf-8") as destination:
        for record in records:
            destination.write(json.dumps(record, sort_keys=True) + "\n")
    summary_output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _derive_record(
    label_record: dict[str, Any],
    manifest: dict[str, Any],
    github: dict[str, Any],
    cutoff_at: datetime,
) -> dict[str, Any]:
    source_id = manifest["source_id"]
    classification = Classification.from_dict(label_record["classification"])
    if classification.source_id != source_id:
        raise ValueError(f"classification source_id mismatch for {source_id}")

    created_at = _parse_time(manifest["created_at"])
    if created_at > cutoff_at:
        raise ValueError(f"{source_id} was created after the cutoff")
    merged_at = _time_at_or_before(
        manifest.get("merged_at_by_cutoff"), cutoff_at
    )
    closed_value = github.get("closed_at") or github.get("closedAt")
    closed_at = _time_at_or_before(closed_value, cutoff_at)

    if merged_at is not None:
        status = "merged"
        outcome_at = merged_at
        merge_state = "event"
        close_state = "event"
    elif closed_at is not None:
        status = "closed_unmerged"
        outcome_at = closed_at
        merge_state = "competing_event"
        close_state = "event"
    else:
        status = "open"
        outcome_at = cutoff_at
        merge_state = "right_censored"
        close_state = "right_censored"

    if outcome_at < created_at:
        raise ValueError(f"{source_id} has an outcome before creation")

    user = github.get("user") or {}
    login = user.get("login", "")
    association = github.get("author_association") or "NONE"
    is_bot = user.get("type") == "Bot" or login.endswith("[bot]")
    if is_bot:
        author_group = "bot"
    elif association in MAINTAINER_ASSOCIATIONS:
        author_group = "maintainer"
    else:
        author_group = "external"

    return {
        "source_id": source_id,
        "number": manifest["number"],
        "created_at": _format_time(created_at),
        "status_at_cutoff": status,
        "outcome_at": _format_time(outcome_at),
        "observed_duration_days": _days(outcome_at - created_at),
        "merged_at": _format_time(merged_at),
        "closed_at": _format_time(closed_at),
        "time_to_merge_days": (
            _days(merged_at - created_at) if merged_at is not None else None
        ),
        "time_to_close_days": (
            _days(outcome_at - created_at) if close_state == "event" else None
        ),
        "merge_analysis_state": merge_state,
        "close_analysis_state": close_state,
        "period": _period(created_at),
        "author_association": association,
        "author_group": author_group,
        "subsystems": list(classification.subsystems),
        "accelerator_scope": classification.accelerator_scope,
        "accelerators": list(classification.accelerators),
        "file_evidence": (
            manifest.get("file_paths_source")
            == "default_branch_git_history"
        ),
    }


def _group_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(records),
        "status_at_cutoff": _status_counts(records),
        "outcome_durations": _duration_summary(records),
    }


def _duration_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "merged_time_to_merge": _distribution(
            [
                record["time_to_merge_days"]
                for record in records
                if record["status_at_cutoff"] == "merged"
            ]
        ),
        "closed_unmerged_time_to_close": _distribution(
            [
                record["time_to_close_days"]
                for record in records
                if record["status_at_cutoff"] == "closed_unmerged"
            ]
        ),
        "open_age_at_cutoff": _distribution(
            [
                record["observed_duration_days"]
                for record in records
                if record["status_at_cutoff"] == "open"
            ]
        ),
    }


def _distribution(values: list[float]) -> dict[str, int | float | None]:
    if not values:
        return {"count": 0, "median": None, "p75": None, "p90": None}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "median": round(median(ordered), 2),
        "p75": round(_percentile(ordered, 0.75), 2),
        "p90": round(_percentile(ordered, 0.90), 2),
    }


def _percentile(ordered: list[float], fraction: float) -> float:
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(record["status_at_cutoff"] for record in records)
    return {
        status: counts[status]
        for status in ("merged", "closed_unmerged", "open")
    }


def _days(delta: Any) -> float:
    return round(delta.total_seconds() / 86400, 6)


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_time(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _time_at_or_before(value: str | None, cutoff_at: datetime) -> datetime | None:
    if not value:
        return None
    parsed = _parse_time(value)
    return parsed if parsed <= cutoff_at else None


def _period(created_at: datetime) -> str:
    if created_at.year <= 2024:
        return "launch_through_2024"
    if created_at.year == 2025:
        return "2025"
    return "2026_through_cutoff"


def _load_unique_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            value = json.loads(line)
            source_id = value.get("source_id")
            if not isinstance(source_id, str):
                raise ValueError(f"{path}:{line_number} lacks source_id")
            if source_id in records:
                raise ValueError(f"duplicate source_id {source_id} in {path}")
            records[source_id] = value
    return records


def _require_same_population(*populations: dict[str, Any]) -> None:
    expected = set(populations[0])
    for population in populations[1:]:
        if set(population) != expected:
            missing = sorted(expected - set(population))[:5]
            extra = sorted(set(population) - expected)[:5]
            raise ValueError(
                f"PR populations differ; missing examples={missing}, "
                f"extra examples={extra}"
            )
