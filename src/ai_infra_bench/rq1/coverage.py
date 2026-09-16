"""Coverage diagnostics for incomplete public GitHub event sources."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from ai_infra_bench.rq1.event_snapshot import read_events


def event_coverage(events_path: Path, merged_manifest_path: Path) -> dict[str, Any]:
    """Compare observed open events with merged PRs known from Git history."""
    opened_prs: set[int] = set()
    any_pr_event: set[int] = set()
    opened_issues: set[int] = set()
    event_counts: Counter[str] = Counter()
    opened_by_year: Counter[str] = Counter()
    earliest: str | None = None
    latest: str | None = None
    for event in read_events(events_path):
        event_type = event["event_type"]
        event_counts[event_type] += 1
        created_at = event["created_at"]
        earliest = created_at if earliest is None else min(earliest, created_at)
        latest = created_at if latest is None else max(latest, created_at)
        number = int(event["number"])
        if event_type.startswith("PullRequest"):
            any_pr_event.add(number)
        if event_type == "PullRequestEvent" and event["action"] == "opened":
            opened_prs.add(number)
            opened_by_year[f"pr_{created_at[:4]}"] += 1
        if event_type == "IssuesEvent" and event["action"] == "opened":
            opened_issues.add(number)
            opened_by_year[f"issue_{created_at[:4]}"] += 1

    with merged_manifest_path.open(encoding="utf-8") as stream:
        merged_prs = {
            int(value["number"])
            for line in stream
            if line.strip()
            for value in [json.loads(line)]
        }
    return {
        "schema_version": "1.0",
        "event_records": sum(event_counts.values()),
        "event_counts": dict(sorted(event_counts.items())),
        "earliest_event": earliest,
        "latest_event": latest,
        "opened_prs_observed": len(opened_prs),
        "opened_issues_observed": len(opened_issues),
        "opened_by_year": dict(sorted(opened_by_year.items())),
        "merged_prs_in_git": len(merged_prs),
        "merged_prs_with_any_pr_event": len(merged_prs & any_pr_event),
        "merged_pr_event_coverage": (
            len(merged_prs & any_pr_event) / len(merged_prs)
            if merged_prs
            else None
        ),
        "suitable_for_complete_arrival_counts": False,
    }
