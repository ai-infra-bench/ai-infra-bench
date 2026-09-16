"""Derive cutoff-aware PR response and formal-review metrics."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

from ai_infra_bench.rq1.taxonomy import Classification

MAINTAINER_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
FORMAL_REVIEW_STATES = frozenset(
    {"APPROVED", "COMMENTED", "CHANGES_REQUESTED"}
)


def derive_pr_response_metrics(
    responses_path: Path,
    github_prs_path: Path,
    labels_path: Path,
    *,
    cutoff: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return per-PR response metrics and descriptive human-PR summaries."""
    base = _load_base(github_prs_path)
    labels = _load_labels(labels_path)
    cutoff_at = _parse_time(cutoff)
    records = []
    monthly_reviewers: dict[str, set[str]] = defaultdict(set)
    monthly_maintainers: dict[str, set[str]] = defaultdict(set)
    monthly_reviewed_prs: dict[str, set[str]] = defaultdict(set)
    monthly_review_submissions: Counter[str] = Counter()
    seen: set[str] = set()
    with responses_path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            detail = json.loads(line)
            source_id = detail["source_id"]
            if source_id in seen:
                raise ValueError(
                    f"duplicate source_id {source_id} at line {line_number}"
                )
            seen.add(source_id)
            if source_id not in base or source_id not in labels:
                raise ValueError(f"response PR {source_id} is outside the census")
            record, activity = _derive_record(
                detail,
                base[source_id],
                labels[source_id],
                cutoff_at,
            )
            records.append(record)
            for month, login in activity["reviewers"]:
                monthly_reviewers[month].add(login)
                monthly_reviewed_prs[month].add(source_id)
                monthly_review_submissions[month] += 1
            for month, login in activity["maintainers"]:
                monthly_maintainers[month].add(login)
    expected = set(base)
    if seen != expected or seen != set(labels):
        raise ValueError("response, base, and label populations differ")
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
    arrivals = Counter(
        record["created_at"][:7]
        for record in human
    )
    activity_months = sorted(
        set(arrivals)
        | set(monthly_reviewers)
        | set(monthly_maintainers)
        | set(monthly_reviewed_prs)
    )
    summary = {
        "metadata": {
            "snapshot_cutoff": cutoff,
            "classification_unit": "pull_request",
            "duration_unit": "hours",
            "formal_review_states": sorted(FORMAL_REVIEW_STATES),
            "maintainer_associations": sorted(MAINTAINER_ASSOCIATIONS),
            "quantile_method": "linear interpolation over observed events",
            "censoring_note": (
                "Observed-event quantiles exclude PRs without the event. "
                "Closed-without-event and open-right-censored counts are retained."
            ),
        },
        "population": {
            "all_prs": len(records),
            "human_prs": len(human),
            "bot_prs": len(records) - len(human),
            "api_missing": sum(record["api_missing"] for record in records),
        },
        "human_overall": _group_summary(human),
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
        "human_by_creation_month": {
            month: _group_summary(
                [record for record in human if record["created_at"][:7] == month]
            )
            for month in sorted(arrivals)
        },
        "monthly_pr_review_demand": {
            month: _monthly_demand(
                arrivals[month],
                monthly_reviewers[month],
                monthly_maintainers[month],
                monthly_reviewed_prs[month],
                monthly_review_submissions[month],
            )
            for month in activity_months
        },
    }
    return records, summary


def write_pr_response_metrics(
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
    detail: dict[str, Any],
    base: dict[str, Any],
    classification: Classification,
    cutoff_at: datetime,
) -> tuple[dict[str, Any], dict[str, list[tuple[str, str]]]]:
    source_id = detail["source_id"]
    created_at = _parse_time(base["created_at"])
    author_login = _login(base.get("user"))
    association = base.get("author_association") or "NONE"
    author_is_bot = _is_bot(base.get("user"))
    if author_is_bot:
        author_group = "bot"
    elif association in MAINTAINER_ASSOCIATIONS:
        author_group = "maintainer"
    else:
        author_group = "external"

    if detail.get("api_missing"):
        comments = []
        reviews = []
    else:
        comments = detail["comments"]["nodes"]
        reviews = detail["reviews"]["nodes"]

    human_comments = [
        node
        for node in comments
        if _qualifying_actor(node, author_login)
    ]
    maintainer_comments = [
        node
        for node in human_comments
        if node.get("authorAssociation") in MAINTAINER_ASSOCIATIONS
    ]
    formal_reviews = [
        node
        for node in reviews
        if node.get("state") in FORMAL_REVIEW_STATES
        and node.get("submittedAt")
        and _qualifying_actor(node, author_login)
    ]
    maintainer_reviews = [
        node
        for node in formal_reviews
        if node.get("authorAssociation") in MAINTAINER_ASSOCIATIONS
    ]

    first_human_comment = _first(human_comments, "createdAt")
    first_maintainer_comment = _first(maintainer_comments, "createdAt")
    first_review = _first(formal_reviews, "submittedAt")
    first_maintainer_review = _first(maintainer_reviews, "submittedAt")
    first_human_activity_at = _earliest(
        first_human_comment,
        "createdAt",
        first_review,
        "submittedAt",
    )
    first_maintainer_activity_at = _earliest(
        first_maintainer_comment,
        "createdAt",
        first_maintainer_review,
        "submittedAt",
    )

    closed_value = base.get("closed_at") or base.get("closedAt")
    closed_at = _parse_time(closed_value) if closed_value else None
    if closed_at is not None and closed_at <= cutoff_at:
        observation_end = closed_at
        no_event_state = "closed_without_event"
    else:
        observation_end = cutoff_at
        no_event_state = "open_right_censored"

    metrics = {
        "first_human_comment_at": _event_time(
            first_human_comment, "createdAt"
        ),
        "first_maintainer_comment_at": _event_time(
            first_maintainer_comment, "createdAt"
        ),
        "first_formal_review_at": _event_time(first_review, "submittedAt"),
        "first_maintainer_review_at": _event_time(
            first_maintainer_review, "submittedAt"
        ),
        "first_human_activity_at": first_human_activity_at,
        "first_maintainer_activity_at": first_maintainer_activity_at,
    }
    for name, timestamp in list(metrics.items()):
        metric = name.removesuffix("_at")
        metrics[f"time_to_{metric}_hours"] = _elapsed_hours(
            created_at, timestamp
        )

    submitted_reviewers = {
        _login(node.get("author"))
        for node in formal_reviews
        if _login(node.get("author"))
    }
    requested_changes = sum(
        node["state"] == "CHANGES_REQUESTED" for node in formal_reviews
    )
    reviews_updated_after_cutoff = sum(
        bool(node.get("updatedAt"))
        and _parse_time(node["updatedAt"]) > cutoff_at
        for node in reviews
    )
    reviewer_activity = [
        (node["submittedAt"][:7], _login(node.get("author")))
        for node in formal_reviews
    ]
    maintainer_activity = [
        (node["createdAt"][:7], _login(node.get("author")))
        for node in maintainer_comments
    ] + [
        (node["submittedAt"][:7], _login(node.get("author")))
        for node in maintainer_reviews
    ]
    record = {
        "source_id": source_id,
        "number": base["number"],
        "created_at": _format_time(created_at),
        "period": _period(created_at),
        "author_group": author_group,
        "author_association": association,
        "subsystems": list(classification.subsystems),
        "accelerator_scope": classification.accelerator_scope,
        "accelerators": list(classification.accelerators),
        "api_missing": bool(detail.get("api_missing")),
        "conversation_comments_at_cutoff": len(comments),
        "qualifying_human_comments": len(human_comments),
        "qualifying_maintainer_comments": len(maintainer_comments),
        "submitted_formal_reviews": len(formal_reviews),
        "submitted_maintainer_reviews": len(maintainer_reviews),
        "unique_reviewers": len(submitted_reviewers),
        "requested_changes_reviews": requested_changes,
        "any_requested_changes": requested_changes > 0,
        "reviews_updated_after_cutoff": reviews_updated_after_cutoff,
        **metrics,
        "first_maintainer_activity_state": (
            "event" if first_maintainer_activity_at else no_event_state
        ),
        "response_observation_end_at": _format_time(observation_end),
        "response_observation_hours": _elapsed_hours(
            created_at, _format_time(observation_end)
        ),
    }
    activity = {
        "reviewers": [
            (month, login) for month, login in reviewer_activity if login
        ],
        "maintainers": [
            (month, login) for month, login in maintainer_activity if login
        ],
    }
    return record, activity


def _monthly_demand(
    new_prs: int,
    reviewers: set[str],
    maintainers: set[str],
    reviewed_prs: set[str],
    review_submissions: int,
) -> dict[str, int | float | None]:
    reviewer_count = len(reviewers)
    return {
        "new_human_prs": new_prs,
        "active_reviewers": reviewer_count,
        "active_pr_maintainers_lower_bound": len(maintainers),
        "prs_receiving_formal_review": len(reviewed_prs),
        "formal_review_submissions": review_submissions,
        "new_prs_per_active_reviewer": _ratio(new_prs, reviewer_count),
        "reviewed_prs_per_active_reviewer": _ratio(
            len(reviewed_prs), reviewer_count
        ),
        "review_submissions_per_active_reviewer": _ratio(
            review_submissions, reviewer_count
        ),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 2) if denominator else None


def _group_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    denominator = len(records)
    return {
        "count": denominator,
        "first_human_activity": _metric_summary(
            records, "time_to_first_human_activity_hours"
        ),
        "first_maintainer_activity": _metric_summary(
            records, "time_to_first_maintainer_activity_hours"
        ),
        "first_human_comment": _metric_summary(
            records, "time_to_first_human_comment_hours"
        ),
        "first_maintainer_comment": _metric_summary(
            records, "time_to_first_maintainer_comment_hours"
        ),
        "first_formal_review": _metric_summary(
            records, "time_to_first_formal_review_hours"
        ),
        "first_maintainer_review": _metric_summary(
            records, "time_to_first_maintainer_review_hours"
        ),
        "maintainer_activity_state": dict(
            sorted(
                Counter(
                    record["first_maintainer_activity_state"]
                    for record in records
                ).items()
            )
        ),
        "formal_review_submissions": sum(
            record["submitted_formal_reviews"] for record in records
        ),
        "reviews_updated_after_cutoff": sum(
            record["reviews_updated_after_cutoff"] for record in records
        ),
        "prs_with_requested_changes": _count_and_percent(
            sum(record["any_requested_changes"] for record in records),
            denominator,
        ),
    }


def _metric_summary(
    records: list[dict[str, Any]], field: str
) -> dict[str, int | float | None]:
    values = [record[field] for record in records if record[field] is not None]
    result = _distribution(values)
    result["no_observed_event"] = len(records) - len(values)
    result["event_percent"] = (
        round(100 * len(values) / len(records), 1) if records else 0.0
    )
    return result


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


def _first(nodes: list[dict[str, Any]], field: str) -> dict[str, Any] | None:
    return min(nodes, key=lambda node: _parse_time(node[field])) if nodes else None


def _earliest(
    first: dict[str, Any] | None,
    first_field: str,
    second: dict[str, Any] | None,
    second_field: str,
) -> str | None:
    values = [
        _event_time(node, field)
        for node, field in ((first, first_field), (second, second_field))
        if node is not None
    ]
    return min(values, key=_parse_time) if values else None


def _event_time(node: dict[str, Any] | None, field: str) -> str | None:
    return node[field] if node is not None else None


def _qualifying_actor(node: dict[str, Any], author_login: str | None) -> bool:
    actor = node.get("author")
    login = _login(actor)
    return bool(
        login
        and not _is_bot(actor)
        and (author_login is None or login.casefold() != author_login.casefold())
    )


def _login(actor: dict[str, Any] | None) -> str | None:
    if not actor:
        return None
    login = actor.get("login")
    return login if isinstance(login, str) and login else None


def _is_bot(actor: dict[str, Any] | None) -> bool:
    login = _login(actor) or ""
    actor_type = (actor or {}).get("type") or (actor or {}).get("__typename")
    return actor_type == "Bot" or login.endswith("[bot]")


def _elapsed_hours(created_at: datetime, event_at: str | None) -> float | None:
    if event_at is None:
        return None
    elapsed = _parse_time(event_at) - created_at
    if elapsed.total_seconds() < 0:
        raise ValueError("response event precedes PR creation")
    return round(elapsed.total_seconds() / 3600, 3)


def _count_and_percent(count: int, denominator: int) -> dict[str, int | float]:
    return {
        "count": count,
        "percent": round(100 * count / denominator, 1) if denominator else 0.0,
    }


def _load_base(path: Path) -> dict[str, dict[str, Any]]:
    result = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            value = json.loads(line)
            result[value["source_id"]] = {
                "source_id": value["source_id"],
                "number": value["number"],
                "created_at": value["created_at"],
                "closed_at": value.get("closed_at"),
                "user": value.get("user"),
                "author_association": value.get("author_association"),
            }
    return result


def _load_labels(path: Path) -> dict[str, Classification]:
    result = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            value = json.loads(line)
            result[value["source_id"]] = Classification.from_dict(
                value["classification"]
            )
    return result


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _period(created_at: datetime) -> str:
    if created_at.year <= 2024:
        return "launch_through_2024"
    if created_at.year == 2025:
        return "2025"
    return "2026_through_cutoff"
