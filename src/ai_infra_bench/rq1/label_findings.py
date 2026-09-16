"""Reproducible aggregates for RQ1 PR semantic labels."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from itertools import combinations
from pathlib import Path
from statistics import mean, median
from typing import Any

from ai_infra_bench.rq1.taxonomy import (
    ACCELERATOR_SCOPES,
    ACCELERATORS,
    SUBSYSTEMS,
    Classification,
)

PERIODS = ("launch_through_2024", "2025", "2026_through_cutoff")


def summarize_labels(
    labels_path: Path,
    manifest_path: Path,
    github_prs_path: Path,
    *,
    cutoff: str,
) -> dict[str, Any]:
    """Join frozen PR data and produce descriptive label aggregates."""
    labels = _load_unique_jsonl(labels_path)
    manifests = _load_unique_jsonl(manifest_path)
    github_prs = _load_unique_jsonl(github_prs_path)
    _require_same_population(labels, manifests, github_prs)

    cutoff_at = _parse_time(cutoff)
    records = []
    taxonomy_versions: set[str] = set()
    prompt_versions: set[str] = set()
    resolved_models: set[str] = set()

    for source_id, label_record in labels.items():
        classification = Classification.from_dict(label_record["classification"])
        if classification.source_id != source_id:
            raise ValueError(f"classification source_id mismatch for {source_id}")

        manifest = manifests[source_id]
        github = github_prs[source_id]
        created_at = _parse_time(manifest["created_at"])
        if created_at > cutoff_at:
            raise ValueError(f"{source_id} was created after the cutoff")

        user = github.get("user") or {}
        login = user.get("login", "")
        is_bot = user.get("type") == "Bot" or login.endswith("[bot]")
        file_evidence = manifest.get("file_paths_source") == (
            "default_branch_git_history"
        )
        additions = manifest.get("additions")
        deletions = manifest.get("deletions")
        churn = (
            additions + deletions
            if isinstance(additions, int) and isinstance(deletions, int)
            else None
        )
        records.append(
            {
                "source_id": source_id,
                "is_bot": is_bot,
                "created_at": created_at,
                "period": _period(created_at),
                "status": _status_at_cutoff(manifest, github, cutoff_at),
                "file_evidence": file_evidence,
                "churn": churn,
                "classification": classification,
            }
        )
        taxonomy_versions.add(label_record["taxonomy_version"])
        prompt_versions.add(label_record["prompt_version"])
        resolved_models.add(label_record["model"]["resolved"])

    human = [record for record in records if not record["is_bot"]]
    bots = [record for record in records if record["is_bot"]]
    by_period = {
        period: [record for record in human if record["period"] == period]
        for period in PERIODS
    }
    file_backed = [record for record in human if record["file_evidence"]]
    no_files = [record for record in human if not record["file_evidence"]]

    monthly = Counter(
        record["created_at"].strftime("%Y-%m") for record in human
    )
    yearly: dict[str, dict[str, int | float]] = {}
    cutoff_month = cutoff_at.strftime("%Y-%m")
    for year in sorted({month[:4] for month in monthly}):
        observed_months = sorted(
            month for month in monthly if month[:4] == year
        )
        observed = [monthly[month] for month in observed_months]
        complete = [
            monthly[month] for month in observed_months if month != cutoff_month
        ]
        yearly[year] = {
            "count": sum(observed),
            "months_observed": len(observed),
            "mean_including_partial_month": round(mean(observed), 1),
            "complete_months": len(complete),
            "complete_month_mean": (
                round(mean(complete), 1) if complete else 0.0
            ),
        }

    subsystem_counts = _label_counts(human, "subsystems", SUBSYSTEMS)
    accelerator_counts = _label_counts(
        human, "accelerators", ACCELERATORS
    )
    scope_counts = Counter(
        record["classification"].accelerator_scope for record in human
    )
    subsystem_pairs = Counter(
        pair
        for record in human
        for pair in combinations(record["classification"].subsystems, 2)
    )
    named_vendor = [
        record for record in human if record["classification"].accelerators
    ]

    return {
        "metadata": {
            "snapshot_cutoff": cutoff,
            "taxonomy_versions": sorted(taxonomy_versions),
            "prompt_versions": sorted(prompt_versions),
            "resolved_models": sorted(resolved_models),
            "classification_unit": "pull_request",
            "percentages": "human PR denominator; multi-label totals may exceed 100%",
        },
        "population": {
            "all_prs": len(records),
            "human_prs": len(human),
            "bot_prs": len(bots),
            "human_by_period": {
                period: len(period_records)
                for period, period_records in by_period.items()
            },
            "human_status_at_cutoff": dict(
                sorted(Counter(record["status"] for record in human).items())
            ),
            "human_with_file_evidence": len(file_backed),
            "human_without_file_evidence": len(no_files),
        },
        "arrivals": {
            "human_prs_by_month": dict(sorted(monthly.items())),
            "human_prs_by_year": yearly,
        },
        "subsystems": {
            "overall": _count_table(subsystem_counts, len(human)),
            "by_period": {
                period: _count_table(
                    _label_counts(records, "subsystems", SUBSYSTEMS),
                    len(records),
                )
                for period, records in by_period.items()
            },
            "average_labels_per_pr": round(
                mean(
                    len(record["classification"].subsystems)
                    for record in human
                ),
                3,
            ),
            "multi_subsystem_prs": _count_and_percent(
                sum(
                    len(record["classification"].subsystems) > 1
                    for record in human
                ),
                len(human),
            ),
            "top_cooccurrences": [
                {"labels": list(pair), "count": count}
                for pair, count in sorted(
                    subsystem_pairs.items(),
                    key=lambda item: (-item[1], item[0]),
                )[:10]
            ],
        },
        "accelerators": {
            "scope_overall": _count_table(scope_counts, len(human)),
            "scope_by_period": {
                period: _count_table(
                    Counter(
                        record["classification"].accelerator_scope
                        for record in records
                    ),
                    len(records),
                    labels=ACCELERATOR_SCOPES,
                )
                for period, records in by_period.items()
            },
            "vendors_overall": _count_table(accelerator_counts, len(human)),
            "vendors_by_period": {
                period: _count_table(
                    _label_counts(records, "accelerators", ACCELERATORS),
                    len(records),
                )
                for period, records in by_period.items()
            },
            "any_named_vendor": _count_and_percent(
                len(named_vendor), len(human)
            ),
            "multi_vendor_prs": _count_and_percent(
                sum(
                    len(record["classification"].accelerators) > 1
                    for record in human
                ),
                len(human),
            ),
            "vendor_mix_among_named": _count_table(
                accelerator_counts, len(named_vendor)
            ),
        },
        "evidence_quality": {
            "with_file_evidence": _quality_table(file_backed),
            "without_file_evidence": _quality_table(no_files),
            "file_backed_churn_median_by_subsystem": {
                label: _median_churn(file_backed, label)
                for label in sorted(SUBSYSTEMS)
            },
        },
    }


def write_label_summary(summary: dict[str, Any], output: Path) -> None:
    """Write a stable, human-readable JSON summary."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _period(created_at: datetime) -> str:
    if created_at.year <= 2024:
        return "launch_through_2024"
    if created_at.year == 2025:
        return "2025"
    return "2026_through_cutoff"


def _status_at_cutoff(
    manifest: dict[str, Any],
    github: dict[str, Any],
    cutoff_at: datetime,
) -> str:
    merged_at = manifest.get("merged_at_by_cutoff")
    if merged_at and _parse_time(merged_at) <= cutoff_at:
        return "merged"
    closed_at = github.get("closed_at") or github.get("closedAt")
    if closed_at and _parse_time(closed_at) <= cutoff_at:
        return "closed_unmerged"
    return "open_at_cutoff"


def _label_counts(
    records: list[dict[str, Any]],
    field: str,
    labels: frozenset[str],
) -> Counter[str]:
    counts = Counter(
        label
        for record in records
        for label in getattr(record["classification"], field)
    )
    return Counter({label: counts[label] for label in labels})


def _count_table(
    counts: Counter[str],
    denominator: int,
    *,
    labels: frozenset[str] | None = None,
) -> dict[str, dict[str, int | float]]:
    names = labels or frozenset(counts)
    return {
        label: _count_and_percent(counts[label], denominator)
        for label in sorted(names)
    }


def _count_and_percent(count: int, denominator: int) -> dict[str, int | float]:
    percent = round(100 * count / denominator, 1) if denominator else 0.0
    return {"count": count, "percent": percent}


def _quality_table(records: list[dict[str, Any]]) -> dict[str, Any]:
    denominator = len(records)
    return {
        "total": denominator,
        "subsystem_unknown": _count_and_percent(
            sum("unknown" in r["classification"].subsystems for r in records),
            denominator,
        ),
        "subsystem_low_confidence": _count_and_percent(
            sum(
                r["classification"].subsystem_confidence == "low"
                for r in records
            ),
            denominator,
        ),
        "accelerator_unknown": _count_and_percent(
            sum(
                r["classification"].accelerator_scope == "unknown"
                for r in records
            ),
            denominator,
        ),
        "accelerator_low_confidence": _count_and_percent(
            sum(
                r["classification"].accelerator_confidence == "low"
                for r in records
            ),
            denominator,
        ),
    }


def _median_churn(records: list[dict[str, Any]], label: str) -> float | None:
    values = [
        record["churn"]
        for record in records
        if label in record["classification"].subsystems
        and record["churn"] is not None
    ]
    return median(values) if values else None
