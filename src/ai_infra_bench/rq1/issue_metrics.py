"""Derive cutoff-aware issue flow, lifecycle, and response metrics."""

from __future__ import annotations

import calendar
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

MAINTAINER_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
AUTOMATION_LOGINS = frozenset({"vllm-bot"})
SUBSTANTIVE_RULE_VERSION = "rq1-substantive-text-v1"
RESPONSE_WINDOWS_HOURS = (24, 48, 72, 168, 336, 720)

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_MARKDOWN_LINK = re.compile(r"!?\[([^]]*)\]\([^)]*\)")
_MARKDOWN_MARKER = re.compile(r"[`*_~>#-]+")
_TOKEN = re.compile(r"[A-Za-z0-9_]+")
_ACKNOWLEDGEMENT_ONLY = re.compile(
    r"(?:"
    r"(?:thanks?|thank\s+you)(?:\s+for\s+(?:reporting|opening|filing)"
    r"(?:\s+(?:this(?:\s+issue)?|the\s+issue))?)?"
    r"|(?:i(?:'ll|\s+will)|we(?:'ll|\s+will))\s+(?:take\s+a\s+look|"
    r"look\s+into\s+(?:it|this))"
    r"|looking\s+into\s+(?:it|this)"
    r"|ack(?:nowledged)?|noted|same\s+here|following|bump|subscribed?"
    r"|(?:cc|ping)\s+(?:@[A-Za-z0-9_-]+\s*)+"
    r"|duplicate\s+of\s+#\d+|fixed\s+(?:by|in)\s+#\d+"
    r"|/[A-Za-z][A-Za-z0-9_-]*(?:\s+.*)?"
    r")[.!\s]*",
    re.IGNORECASE,
)


def derive_issue_metrics(
    details_path: Path,
    github_issues_path: Path,
    *,
    cutoff: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return per-issue records and descriptive human-issue summaries."""
    base = _load_unique_jsonl(github_issues_path)
    with details_path.open(encoding="utf-8") as source:
        details = (json.loads(line) for line in source)
        return derive_issue_metrics_from_objects(details, base, cutoff=cutoff)


def derive_issue_metrics_from_objects(
    details: Iterable[dict[str, Any]],
    base: dict[str, dict[str, Any]],
    *,
    cutoff: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Derive metrics from normalized issue and detail objects."""
    cutoff_at = _parse_time(cutoff)
    records = []
    seen: set[str] = set()
    source_counts: Counter[str] = Counter()
    monthly_responders: dict[str, set[str]] = defaultdict(set)
    monthly_substantive_responders: dict[str, set[str]] = defaultdict(set)

    for position, detail in enumerate(details, start=1):
        source_id = detail["source_id"]
        if source_id in seen:
            raise ValueError(
                f"duplicate source_id {source_id} at position {position}"
            )
        seen.add(source_id)
        if source_id not in base:
            raise ValueError(f"issue detail {source_id} is outside the census")
        _update_source_counts(source_counts, detail)
        record, activity = _derive_record(detail, base[source_id], cutoff_at)
        records.append(record)
        for month, login in activity["maintainers"]:
            monthly_responders[month].add(login)
        for month, login in activity["substantive_maintainers"]:
            monthly_substantive_responders[month].add(login)

    if seen != set(base):
        missing = len(set(base) - seen)
        extra = len(seen - set(base))
        raise ValueError(
            f"issue detail and base populations differ: missing={missing} "
            f"extra={extra}"
        )
    records.sort(key=lambda record: record["number"])
    human = [
        record
        for record in records
        if record["author_group"] in {"maintainer", "external"}
    ]
    months = _months_in_range(human, cutoff_at)
    flow = _monthly_flow(
        human,
        months,
        cutoff_at,
        monthly_responders,
        monthly_substantive_responders,
    )
    periods = sorted({record["period"] for record in human})
    years = sorted({record["created_at"][:4] for record in human})
    summary = {
        "metadata": {
            "snapshot_cutoff": cutoff,
            "classification_unit": "issue",
            "response_duration_unit": "hours",
            "close_duration_unit": "days",
            "maintainer_associations": sorted(MAINTAINER_ASSOCIATIONS),
            "substantive_rule_version": SUBSTANTIVE_RULE_VERSION,
            "substantive_rule": (
                "After removing HTML comments and Markdown markers, require "
                "at least four alphanumeric tokens or at least three tokens "
                "and 24 visible characters; reject acknowledgement-only, "
                "subscription, ping, duplicate/fixed-reference, and slash-command "
                "comments. Code fences count as substantive."
            ),
            "quantile_method": "linear interpolation over observed events",
            "censoring_note": (
                "Observed-event response quantiles exclude issues without the "
                "event. Fixed-window response rates restrict denominators to "
                "issues with a complete observation window. Time-to-first-close "
                "also includes a Kaplan-Meier estimate over right-censored issues."
            ),
            "active_maintainer_note": (
                "Monthly active issue responders include maintainers with a "
                "qualifying non-author issue comment. They are a narrower "
                "denominator than the study-wide active-maintainer definition."
            ),
        },
        "population": {
            "all_issues": len(records),
            "human_issues": len(human),
            "bot_issues": sum(
                record["author_group"] == "bot" for record in records
            ),
            "unknown_actor_type_issues": sum(
                record["author_group"] == "unknown" for record in records
            ),
            "api_missing": sum(record["api_missing"] for record in records),
            "human_status_at_cutoff": dict(
                sorted(Counter(r["status_at_cutoff"] for r in human).items())
            ),
        },
        "source_counts": {
            "base_comment_count": sum(
                int(issue.get("comments") or 0) for issue in base.values()
            ),
            **dict(sorted(source_counts.items())),
        },
        "data_quality": {
            "base_minus_observed_comments": (
                sum(int(issue.get("comments") or 0) for issue in base.values())
                - source_counts["comments_observed_total"]
            ),
            "lifecycle_base_fallback_issues": sum(
                record["lifecycle_fallback_used"] for record in records
            ),
            "duplicate_close_or_reopen_events_ignored": sum(
                record["redundant_lifecycle_events"] for record in records
            ),
            "comment_count_note": (
                "The REST base comment count can exceed the later GraphQL "
                "observed count when comments are deleted between retrievals."
            ),
        },
        "human_overall": _group_summary(human, cutoff_at),
        "human_by_period": {
            period: _group_summary(
                [record for record in human if record["period"] == period],
                cutoff_at,
            )
            for period in periods
        },
        "human_by_creation_year": {
            year: _group_summary(
                [record for record in human if record["created_at"][:4] == year],
                cutoff_at,
            )
            for year in years
        },
        "human_by_author_group": {
            group: _group_summary(
                [record for record in human if record["author_group"] == group],
                cutoff_at,
            )
            for group in ("maintainer", "external")
        },
        "human_by_creation_month": {
            month: _group_summary(
                [record for record in human if record["created_at"][:7] == month],
                cutoff_at,
            )
            for month in months
        },
        "monthly_issue_flow": flow,
    }
    return records, summary


def _update_source_counts(
    counts: Counter[str], detail: dict[str, Any]
) -> None:
    if detail.get("api_missing"):
        return
    for name, prefix in (
        ("comments", "comments"),
        ("timelineItems", "timeline_items"),
    ):
        connection = detail[name]
        node_count = len(connection["nodes"])
        counts[f"{prefix}_observed_total"] += int(
            connection.get("observed_total_count", node_count)
        )
        counts[f"{prefix}_retrieved"] += int(
            connection.get("retrieved_count", node_count)
        )
        counts[f"{prefix}_at_cutoff"] += int(
            connection.get("at_cutoff_count", node_count)
        )


def write_issue_metrics(
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


def is_substantive_comment(body: str | None) -> bool:
    """Apply the frozen, auditable substantive-response text rule."""
    if not body or not body.strip():
        return False
    has_code_fence = "```" in body
    visible = _HTML_COMMENT.sub(" ", body)
    visible = "\n".join(
        line for line in visible.splitlines() if not line.lstrip().startswith(">")
    )
    visible = _MARKDOWN_LINK.sub(r"\1", visible)
    visible = _MARKDOWN_MARKER.sub(" ", visible)
    visible = " ".join(visible.split()).strip()
    if not visible:
        return False
    if _ACKNOWLEDGEMENT_ONLY.fullmatch(visible):
        return False
    if has_code_fence and _TOKEN.search(visible):
        return True
    tokens = _TOKEN.findall(visible)
    return len(tokens) >= 4 or (len(tokens) >= 3 and len(visible) >= 24)


def _derive_record(
    detail: dict[str, Any],
    base: dict[str, Any],
    cutoff_at: datetime,
) -> tuple[dict[str, Any], dict[str, list[tuple[str, str]]]]:
    created_at = _parse_time(base["created_at"])
    if created_at > cutoff_at:
        raise ValueError(f"{base['source_id']} was created after the cutoff")
    author_login = _login(base.get("user"))
    association = base.get("author_association") or "NONE"
    if _is_bot(base.get("user")):
        author_group = "bot"
    elif not _is_human(base.get("user")):
        author_group = "unknown"
    elif base.get("author_is_snapshot_collaborator"):
        author_group = "maintainer"
    elif association in MAINTAINER_ASSOCIATIONS:
        author_group = "maintainer"
    else:
        author_group = "external"

    if detail.get("api_missing"):
        comments: list[dict[str, Any]] = []
        timeline: list[dict[str, Any]] = []
    else:
        comments = detail["comments"]["nodes"]
        timeline = detail["timelineItems"]["nodes"]

    human_comments = [
        node for node in comments if _qualifying_actor(node, author_login)
    ]
    maintainer_comments = [
        node
        for node in human_comments
        if _is_maintainer_response(node)
    ]
    substantive_comments = [
        node for node in human_comments if is_substantive_comment(node.get("body"))
    ]
    substantive_maintainer_comments = [
        node
        for node in maintainer_comments
        if is_substantive_comment(node.get("body"))
    ]

    first_human = _first(human_comments)
    first_maintainer = _first(maintainer_comments)
    first_substantive = _first(substantive_comments)
    first_substantive_maintainer = _first(substantive_maintainer_comments)
    lifecycle = _normalize_lifecycle(
        timeline,
        base,
        created_at=created_at,
        cutoff_at=cutoff_at,
        api_missing=bool(detail.get("api_missing")),
    )
    first_close_at = next(
        (
            event["created_at"]
            for event in lifecycle["events"]
            if event["type"] == "closed"
        ),
        None,
    )
    first_close_event = next(
        (event for event in lifecycle["events"] if event["type"] == "closed"),
        None,
    )
    status = lifecycle["status_at_cutoff"]
    no_response_state = (
        "closed_without_response"
        if status == "closed"
        else "open_right_censored"
    )
    timestamps = {
        "first_human_response_at": _event_time(first_human),
        "first_maintainer_response_at": _event_time(first_maintainer),
        "first_substantive_response_at": _event_time(first_substantive),
        "first_substantive_maintainer_response_at": _event_time(
            first_substantive_maintainer
        ),
    }
    metrics: dict[str, Any] = dict(timestamps)
    for name, value in timestamps.items():
        metrics[f"time_to_{name.removesuffix('_at')}_hours"] = _elapsed(
            created_at, value, unit="hours"
        )

    record = {
        "source_id": base["source_id"],
        "number": base["number"],
        "created_at": _format_time(created_at),
        "period": _period(created_at),
        "author_association": association,
        "author_group": author_group,
        "api_missing": bool(detail.get("api_missing")),
        "conversation_comments_at_cutoff": len(comments),
        "qualifying_human_comments": len(human_comments),
        "qualifying_maintainer_comments": len(maintainer_comments),
        "substantive_human_comments": len(substantive_comments),
        "substantive_maintainer_comments": len(
            substantive_maintainer_comments
        ),
        **metrics,
        "first_maintainer_response_state": (
            "event" if first_maintainer else no_response_state
        ),
        "first_substantive_response_state": (
            "event" if first_substantive else no_response_state
        ),
        "first_substantive_maintainer_response_state": (
            "event" if first_substantive_maintainer else no_response_state
        ),
        "status_at_cutoff": status,
        "first_close_at": first_close_at,
        "first_close_actor_group": (
            first_close_event["actor_group"] if first_close_event else None
        ),
        "time_to_first_close_days": _elapsed(
            created_at, first_close_at, unit="days"
        ),
        "close_analysis_state": (
            "event" if first_close_at else "right_censored"
        ),
        "observation_end_at": _format_time(cutoff_at),
        "observation_hours": _elapsed(
            created_at, _format_time(cutoff_at), unit="hours"
        ),
        "observation_days": _elapsed(
            created_at, _format_time(cutoff_at), unit="days"
        ),
        "close_transitions": sum(
            event["type"] == "closed" for event in lifecycle["events"]
        ),
        "reopen_transitions": sum(
            event["type"] == "reopened" for event in lifecycle["events"]
        ),
        "lifecycle_events": lifecycle["events"],
        "lifecycle_fallback_used": lifecycle["fallback_used"],
        "redundant_lifecycle_events": lifecycle["redundant_events"],
        "state_at_cutoff_override_used": lifecycle[
            "state_at_cutoff_override_used"
        ],
    }
    activity = {
        "maintainers": _actor_months(maintainer_comments),
        "substantive_maintainers": _actor_months(
            substantive_maintainer_comments
        ),
    }
    return record, activity


def _normalize_lifecycle(
    timeline: list[dict[str, Any]],
    base: dict[str, Any],
    *,
    created_at: datetime,
    cutoff_at: datetime,
    api_missing: bool,
) -> dict[str, Any]:
    values = sorted(
        (
            node
            for node in timeline
            if node.get("__typename") in {"ClosedEvent", "ReopenedEvent"}
            and created_at <= _parse_time(node["createdAt"]) <= cutoff_at
        ),
        key=lambda node: _parse_time(node["createdAt"]),
    )
    state = "open"
    events = []
    redundant = 0
    for node in values:
        event_type = (
            "closed" if node["__typename"] == "ClosedEvent" else "reopened"
        )
        expected = "open" if event_type == "closed" else "closed"
        if state != expected:
            redundant += 1
            continue
        state = "closed" if event_type == "closed" else "open"
        events.append(
            {
                "type": event_type,
                "created_at": _format_time(_parse_time(node["createdAt"])),
                "actor_login": _login(node.get("actor")),
                "actor_group": _actor_group(node.get("actor")),
                "source": "timeline",
            }
        )

    fallback_used = False
    closed_value = base.get("closed_at") or base.get("closedAt")
    closed_at = _parse_time(closed_value) if closed_value else None
    if not events and closed_at and created_at <= closed_at <= cutoff_at:
        events.append(
            {
                "type": "closed",
                "created_at": _format_time(closed_at),
                "actor_login": _login(base.get("closed_by")),
                "actor_group": _actor_group(base.get("closed_by")),
                "source": "base_closed_at_fallback",
            }
        )
        state = "closed"
        fallback_used = True
    elif api_missing and not events:
        fallback_used = True

    authoritative = str(base.get("state_at_cutoff") or "").lower()
    if authoritative in {"open", "closed"}:
        state_override = state != authoritative
        state = authoritative
    else:
        state_override = False

    return {
        "events": events,
        "status_at_cutoff": state,
        "fallback_used": fallback_used,
        "redundant_events": redundant,
        "state_at_cutoff_override_used": state_override,
    }


def _group_summary(
    records: list[dict[str, Any]], cutoff_at: datetime
) -> dict[str, Any]:
    return {
        "count": len(records),
        "status_at_cutoff": dict(
            sorted(Counter(r["status_at_cutoff"] for r in records).items())
        ),
        "first_human_response": _response_summary(
            records, "time_to_first_human_response_hours", cutoff_at
        ),
        "first_maintainer_response": _response_summary(
            records, "time_to_first_maintainer_response_hours", cutoff_at
        ),
        "first_substantive_response": _response_summary(
            records, "time_to_first_substantive_response_hours", cutoff_at
        ),
        "first_substantive_maintainer_response": _response_summary(
            records,
            "time_to_first_substantive_maintainer_response_hours",
            cutoff_at,
        ),
        "time_to_first_close": _close_summary(records),
        "first_close_actor_group": dict(
            sorted(
                Counter(
                    record["first_close_actor_group"] or "no_close_event"
                    for record in records
                ).items()
            )
        ),
        "observed_time_to_first_close_by_actor_group": {
            group: _distribution(
                [
                    record["time_to_first_close_days"]
                    for record in records
                    if record["first_close_actor_group"] == group
                ]
            )
            for group in ("human", "automation", "unknown")
        },
    }


def _response_summary(
    records: list[dict[str, Any]],
    field: str,
    cutoff_at: datetime,
) -> dict[str, Any]:
    values = [record[field] for record in records if record[field] is not None]
    result = _distribution(values)
    result["no_observed_event"] = len(records) - len(values)
    result["event_percent"] = _percent(len(values), len(records))
    result["fixed_windows"] = {
        str(hours): _fixed_window(records, field, cutoff_at, hours)
        for hours in RESPONSE_WINDOWS_HOURS
    }
    return result


def _fixed_window(
    records: list[dict[str, Any]],
    field: str,
    cutoff_at: datetime,
    hours: int,
) -> dict[str, int | float]:
    eligible = [
        record
        for record in records
        if (_parse_time(record["created_at"]) - cutoff_at).total_seconds()
        <= -hours * 3600
    ]
    events = sum(
        record[field] is not None and record[field] <= hours for record in eligible
    )
    low, high = _wilson_interval(events, len(eligible))
    return {
        "eligible": len(eligible),
        "events": events,
        "percent": _percent(events, len(eligible)),
        "wilson_low_percent": low,
        "wilson_high_percent": high,
    }


def _close_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    observed = [
        record["time_to_first_close_days"]
        for record in records
        if record["time_to_first_close_days"] is not None
    ]
    result = _distribution(observed)
    result["right_censored"] = len(records) - len(observed)
    result["event_percent"] = _percent(len(observed), len(records))
    result["kaplan_meier"] = _kaplan_meier(records)
    return result


def _kaplan_meier(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_time: dict[float, Counter[str]] = defaultdict(Counter)
    for record in records:
        event = record["time_to_first_close_days"] is not None
        duration = (
            record["time_to_first_close_days"]
            if event
            else record["observation_days"]
        )
        by_time[float(duration)]["event" if event else "censored"] += 1
    at_risk = len(records)
    survival = 1.0
    curve: list[tuple[float, float]] = []
    for duration in sorted(by_time):
        events = by_time[duration]["event"]
        censored = by_time[duration]["censored"]
        if at_risk and events:
            survival *= 1 - events / at_risk
            curve.append((duration, survival))
        at_risk -= events + censored
    return {
        "median_days": _km_quantile(curve, 0.5),
        "p75_days": _km_quantile(curve, 0.25),
        "p90_days": _km_quantile(curve, 0.10),
        "closure_probability": {
            str(day): round(100 * (1 - _survival_at(curve, day)), 1)
            for day in (1, 7, 30, 90, 180)
        },
    }


def _km_quantile(
    curve: list[tuple[float, float]], threshold: float
) -> float | None:
    value = next((time for time, survival in curve if survival <= threshold), None)
    return round(value, 2) if value is not None else None


def _survival_at(curve: list[tuple[float, float]], day: int) -> float:
    return next(
        (survival for time, survival in reversed(curve) if time <= day), 1.0
    )


def _monthly_flow(
    records: list[dict[str, Any]],
    months: list[str],
    cutoff_at: datetime,
    responders: dict[str, set[str]],
    substantive_responders: dict[str, set[str]],
) -> dict[str, dict[str, int | float | bool | str | None]]:
    arrivals = Counter(record["created_at"][:7] for record in records)
    closes: Counter[str] = Counter()
    reopens: Counter[str] = Counter()
    closes_by_actor: dict[str, Counter[str]] = defaultdict(Counter)
    reopens_by_actor: dict[str, Counter[str]] = defaultdict(Counter)
    unique_closed: dict[str, set[str]] = defaultdict(set)
    unique_closed_by_actor: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for record in records:
        for event in record["lifecycle_events"]:
            month = event["created_at"][:7]
            if event["type"] == "closed":
                closes[month] += 1
                unique_closed[month].add(record["source_id"])
                actor_group = event["actor_group"]
                closes_by_actor[month][actor_group] += 1
                unique_closed_by_actor[month][actor_group].add(
                    record["source_id"]
                )
            else:
                reopens[month] += 1
                reopens_by_actor[month][event["actor_group"]] += 1

    result = {}
    prior_backlog = 0
    for month in months:
        point = min(_month_end(month), cutoff_at)
        backlog = sum(_is_open_at(record, point) for record in records)
        expected = prior_backlog + arrivals[month] - closes[month] + reopens[month]
        reconciliation_adjustment = backlog - expected
        open_records = [
            record for record in records if _is_open_at(record, point)
        ]
        active = len(responders[month])
        active_substantive = len(substantive_responders[month])
        result[month] = {
            "period_end": _format_time(point),
            "complete_month": point == _month_end(month),
            "new_human_issues": arrivals[month],
            "close_transitions": closes[month],
            "unique_issues_closed": len(unique_closed[month]),
            "automated_close_transitions": closes_by_actor[month][
                "automation"
            ],
            "human_close_transitions": closes_by_actor[month]["human"],
            "unknown_actor_close_transitions": closes_by_actor[month][
                "unknown"
            ],
            "unique_issues_closed_by_automation": len(
                unique_closed_by_actor[month]["automation"]
            ),
            "reopen_transitions": reopens[month],
            "automated_reopen_transitions": reopens_by_actor[month][
                "automation"
            ],
            "end_backlog": backlog,
            "end_backlog_older_30_days": _older_than(
                open_records, point, 30
            ),
            "end_backlog_older_90_days": _older_than(
                open_records, point, 90
            ),
            "end_backlog_older_180_days": _older_than(
                open_records, point, 180
            ),
            "backlog_change": backlog - prior_backlog,
            "state_reconciliation_adjustment": reconciliation_adjustment,
            "active_issue_maintainer_responders": active,
            "active_substantive_maintainer_responders": active_substantive,
            "new_issues_per_active_issue_responder": _ratio(
                arrivals[month], active
            ),
            "backlog_per_active_issue_responder": _ratio(backlog, active),
        }
        prior_backlog = backlog
    return result


def _is_open_at(record: dict[str, Any], point: datetime) -> bool:
    if _parse_time(record["created_at"]) > point:
        return False
    state = "open"
    for event in record["lifecycle_events"]:
        if _parse_time(event["created_at"]) > point:
            break
        state = "closed" if event["type"] == "closed" else "open"
    if point == _parse_time(record["observation_end_at"]):
        state = record["status_at_cutoff"]
    return state == "open"


def _older_than(
    records: list[dict[str, Any]], point: datetime, days: int
) -> int:
    return sum(
        (point - _parse_time(record["created_at"])).total_seconds()
        > days * 86400
        for record in records
    )


def _months_in_range(
    records: list[dict[str, Any]], cutoff_at: datetime
) -> list[str]:
    if not records:
        return []
    start = min(_parse_time(record["created_at"]) for record in records)
    year, month = start.year, start.month
    result = []
    while (year, month) <= (cutoff_at.year, cutoff_at.month):
        result.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return result


def _month_end(month: str) -> datetime:
    year, month_number = (int(value) for value in month.split("-"))
    day = calendar.monthrange(year, month_number)[1]
    return datetime(year, month_number, day, 23, 59, 59, tzinfo=UTC)


def _actor_months(nodes: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [
        (node["createdAt"][:7], login)
        for node in nodes
        if (login := _login(node.get("author")))
    ]


def _first(nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not nodes:
        return None
    return min(nodes, key=lambda node: _parse_time(node["createdAt"]))


def _event_time(node: dict[str, Any] | None) -> str | None:
    return node["createdAt"] if node is not None else None


def _qualifying_actor(node: dict[str, Any], author_login: str | None) -> bool:
    actor = node.get("author")
    login = _login(actor)
    return bool(
        login
        and _is_human(actor)
        and (author_login is None or login.casefold() != author_login.casefold())
    )


def _is_maintainer_response(node: dict[str, Any]) -> bool:
    if "isSnapshotCollaborator" in node:
        return bool(node["isSnapshotCollaborator"])
    return node.get("authorAssociation") in MAINTAINER_ASSOCIATIONS


def _login(actor: dict[str, Any] | None) -> str | None:
    if not actor:
        return None
    login = actor.get("login")
    return login if isinstance(login, str) and login else None


def _is_bot(actor: dict[str, Any] | None) -> bool:
    login = _login(actor) or ""
    actor_type = (actor or {}).get("type") or (actor or {}).get("__typename")
    if (actor or {}).get("_actor_type_policy") == "github_user_type":
        return actor_type == "Bot"
    return (
        actor_type == "Bot"
        or login.endswith("[bot]")
        or login.casefold() in AUTOMATION_LOGINS
    )


def _is_human(actor: dict[str, Any] | None) -> bool:
    actor_type = (actor or {}).get("type") or (actor or {}).get("__typename")
    if (actor or {}).get("_actor_type_policy") == "github_user_type":
        return actor_type == "User"
    if actor_type is not None:
        return actor_type == "User" and not _is_bot(actor)
    return bool(_login(actor)) and not _is_bot(actor)


def _actor_group(actor: dict[str, Any] | None) -> str:
    if _is_bot(actor):
        return "automation"
    if _is_human(actor):
        return "human"
    return "unknown"


def _wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return round(100 * (center - margin), 1), round(100 * (center + margin), 1)


def _elapsed(
    created_at: datetime, event_at: str | None, *, unit: str
) -> float | None:
    if event_at is None:
        return None
    elapsed = _parse_time(event_at) - created_at
    if elapsed.total_seconds() < 0:
        raise ValueError("issue event precedes issue creation")
    divisor = 3600 if unit == "hours" else 86400
    return round(elapsed.total_seconds() / divisor, 3)


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


def _percent(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 1) if denominator else 0.0


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 2) if denominator else None


def _load_unique_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    result = {}
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            value = json.loads(line)
            source_id = value["source_id"]
            if source_id in result:
                raise ValueError(
                    f"duplicate source_id {source_id} at line {line_number}"
                )
            result[source_id] = value
    return result


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _format_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _period(created_at: datetime) -> str:
    if created_at.year <= 2024:
        return "launch_through_2024"
    if created_at.year == 2025:
        return "2025"
    return "2026_through_cutoff"
