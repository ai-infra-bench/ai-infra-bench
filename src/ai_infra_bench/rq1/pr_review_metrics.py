"""Derive PR review-count and revision-separated round proxies."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from itertools import zip_longest
from pathlib import Path
from statistics import median
from typing import Any

from ai_infra_bench.rq1.pr_response_metrics import FORMAL_REVIEW_STATES
from ai_infra_bench.rq1.taxonomy import Classification


def derive_pr_review_metrics(
    responses_path: Path,
    commits_path: Path,
    review_comments_path: Path,
    github_prs_path: Path,
    labels_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return per-PR review metrics with explicit timing-proxy flags."""
    base = _load_base(github_prs_path)
    labels = _load_labels(labels_path)
    comment_counts, orphan_comments = _review_comment_counts(
        review_comments_path, set(base)
    )
    records = []
    seen: set[str] = set()
    with (
        responses_path.open(encoding="utf-8") as responses,
        commits_path.open(encoding="utf-8") as commits,
    ):
        for response_line, commit_line in zip_longest(responses, commits):
            if response_line is None or commit_line is None:
                raise ValueError("response and commit populations differ")
            response = json.loads(response_line)
            commit_detail = json.loads(commit_line)
            source_id = response["source_id"]
            if commit_detail["source_id"] != source_id:
                raise ValueError("response and commit ordering differs")
            if source_id in seen:
                raise ValueError(f"duplicate source_id {source_id}")
            seen.add(source_id)
            records.append(
                _derive_record(
                    response,
                    commit_detail,
                    base[source_id],
                    labels[source_id],
                    comment_counts[source_id],
                )
            )
    if seen != set(base) or seen != set(labels):
        raise ValueError("review, base, and label populations differ")
    records.sort(key=lambda record: record["number"])
    human = [record for record in records if record["author_group"] != "bot"]
    subsystems = sorted(
        {
            subsystem
            for record in human
            for subsystem in record["subsystems"]
        }
    )
    summary = {
        "metadata": {
            "classification_unit": "pull_request",
            "review_round_proxy": (
                "A new round starts when a qualifying formal review follows "
                "an author commit made after the previous qualifying review."
            ),
            "commit_time_note": (
                "pushedDate is used when present; committedDate is an explicit proxy."
            ),
        },
        "population": {
            "all_prs": len(records),
            "human_prs": len(human),
            "bot_prs": len(records) - len(human),
            "orphan_review_comments": orphan_comments,
        },
        "human_overall": _group_summary(human),
        "human_by_period": {
            period: _group_summary(
                [record for record in human if record["period"] == period]
            )
            for period in (
                "launch_through_2024",
                "2025",
                "2026_through_cutoff",
            )
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


def write_pr_review_metrics(
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
    response: dict[str, Any],
    commit_detail: dict[str, Any],
    base: dict[str, Any],
    classification: Classification,
    comment_counts: Counter[str],
) -> dict[str, Any]:
    author_login = _login(base.get("user"))
    author_group = _author_group(base)
    reviews = [] if response.get("api_missing") else response["reviews"]["nodes"]
    formal_reviews = [
        review
        for review in reviews
        if review.get("state") in FORMAL_REVIEW_STATES
        and review.get("submittedAt")
        and _qualifying_actor(review.get("author"), author_login)
    ]
    commits = (
        []
        if commit_detail.get("api_missing")
        else commit_detail["commits"]["nodes"]
    )
    commit_connection_truncated = bool(
        not commit_detail.get("api_missing")
        and commit_detail["commits"]["retrieved_count"]
        != commit_detail["commits"]["observed_total_count"]
    )
    author_commits = [
        commit
        for commit in commits
        if _commit_by_author(commit, author_login)
    ]
    reviewer_logins = {
        _login(review.get("author"))
        for review in formal_reviews
        if _login(review.get("author"))
    }
    rounds = _review_rounds(formal_reviews, author_commits)
    requested_changes = sum(
        review["state"] == "CHANGES_REQUESTED" for review in formal_reviews
    )
    created_at = _parse_time(base["created_at"])
    return {
        "source_id": response["source_id"],
        "number": base["number"],
        "period": _period(created_at),
        "author_group": author_group,
        "subsystems": list(classification.subsystems),
        "accelerator_scope": classification.accelerator_scope,
        "accelerators": list(classification.accelerators),
        "formal_review_submissions": len(formal_reviews),
        "unique_formal_reviewers": len(reviewer_logins),
        "requested_changes_reviews": requested_changes,
        "any_requested_changes": requested_changes > 0,
        "review_rounds_proxy": rounds,
        "line_review_comments": comment_counts["all"],
        "human_line_review_comments": comment_counts["human"],
        "bot_line_review_comments": comment_counts["bot"],
        "commits_at_cutoff": len(commits),
        "author_commits_at_cutoff": len(author_commits),
        "commits_using_committed_date_proxy": sum(
            commit.get("cutoff_time_source") == "committedDate_proxy"
            for commit in commits
        ),
        "missing_push_timing": any(
            commit.get("cutoff_time_source") == "committedDate_proxy"
            for commit in commits
        ),
        "commit_connection_truncated": commit_connection_truncated,
        "review_rounds_input_complete": bool(
            not response.get("api_missing")
            and not commit_detail.get("api_missing")
            and not commit_connection_truncated
        ),
        "response_api_missing": bool(response.get("api_missing")),
        "commit_api_missing": bool(commit_detail.get("api_missing")),
    }


def _review_rounds(
    reviews: list[dict[str, Any]], commits: list[dict[str, Any]]
) -> int:
    if not reviews:
        return 0
    review_times = sorted(_parse_time(review["submittedAt"]) for review in reviews)
    commit_times = sorted(_commit_time(commit) for commit in commits)
    rounds = 1
    previous_review = review_times[0]
    for review_time in review_times[1:]:
        if any(previous_review < commit <= review_time for commit in commit_times):
            rounds += 1
        previous_review = review_time
    return rounds


def _group_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    denominator = len(records)
    with_reviews = [record for record in records if record["formal_review_submissions"]]
    with_comments = [record for record in records if record["line_review_comments"]]
    with_rounds = [record for record in records if record["review_rounds_proxy"]]
    return {
        "count": denominator,
        "prs_with_formal_review": _count_percent(len(with_reviews), denominator),
        "prs_with_line_review_comments": _count_percent(
            len(with_comments), denominator
        ),
        "prs_with_requested_changes": _count_percent(
            sum(record["any_requested_changes"] for record in records), denominator
        ),
        "formal_review_submissions": _distribution(
            [record["formal_review_submissions"] for record in with_reviews]
        ),
        "unique_formal_reviewers": _distribution(
            [record["unique_formal_reviewers"] for record in with_reviews]
        ),
        "line_review_comments": _distribution(
            [record["line_review_comments"] for record in with_comments]
        ),
        "review_rounds_proxy": _distribution(
            [record["review_rounds_proxy"] for record in with_rounds]
        ),
        "total_formal_review_submissions": sum(
            record["formal_review_submissions"] for record in records
        ),
        "total_line_review_comments": sum(
            record["line_review_comments"] for record in records
        ),
        "prs_missing_push_timing": _count_percent(
            sum(record["missing_push_timing"] for record in records), denominator
        ),
        "prs_with_truncated_commit_connection": _count_percent(
            sum(record["commit_connection_truncated"] for record in records),
            denominator,
        ),
    }


def _review_comment_counts(
    path: Path, census: set[str]
) -> tuple[dict[str, Counter[str]], dict[str, int]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    orphan_prs: set[str] = set()
    orphan_comments = 0
    with path.open(encoding="utf-8") as source:
        for line in source:
            value = json.loads(line)
            source_id = value["source_id"]
            if source_id not in census:
                orphan_prs.add(source_id)
                orphan_comments += 1
                continue
            counts[source_id]["all"] += 1
            counts[source_id]["bot" if _is_bot(value.get("user")) else "human"] += 1
    return counts, {"comments": orphan_comments, "pull_requests": len(orphan_prs)}


def _distribution(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {"count": 0, "median": None, "p75": None, "p90": None}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "median": median(ordered),
        "p75": round(_percentile(ordered, 0.75), 2),
        "p90": round(_percentile(ordered, 0.90), 2),
    }


def _percentile(ordered: list[int], fraction: float) -> float:
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _count_percent(count: int, denominator: int) -> dict[str, int | float]:
    return {
        "count": count,
        "percent": round(100 * count / denominator, 1) if denominator else 0.0,
    }


def _commit_time(node: dict[str, Any]) -> datetime:
    commit = node["commit"]
    value = commit.get("pushedDate") or commit["committedDate"]
    return _parse_time(value)


def _commit_by_author(node: dict[str, Any], author_login: str | None) -> bool:
    if author_login is None:
        return False
    commit = node["commit"]
    logins = {
        _login((commit.get("author") or {}).get("user")),
        _login((commit.get("committer") or {}).get("user")),
    }
    return author_login.casefold() in {
        login.casefold() for login in logins if login
    }


def _qualifying_actor(
    actor: dict[str, Any] | None, author_login: str | None
) -> bool:
    login = _login(actor)
    return bool(
        login
        and not _is_bot(actor)
        and (author_login is None or login.casefold() != author_login.casefold())
    )


def _author_group(base: dict[str, Any]) -> str:
    if _is_bot(base.get("user")):
        return "bot"
    if base.get("author_association") in {"OWNER", "MEMBER", "COLLABORATOR"}:
        return "maintainer"
    return "external"


def _is_bot(actor: dict[str, Any] | None) -> bool:
    actor = actor or {}
    login = _login(actor) or ""
    actor_type = actor.get("type") or actor.get("__typename")
    return actor_type == "Bot" or login.endswith("[bot]")


def _login(actor: dict[str, Any] | None) -> str | None:
    login = (actor or {}).get("login")
    return login if isinstance(login, str) and login else None


def _load_base(path: Path) -> dict[str, dict[str, Any]]:
    result = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            value = json.loads(line)
            result[value["source_id"]] = {
                "number": value["number"],
                "created_at": value["created_at"],
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


def _period(created_at: datetime) -> str:
    if created_at.year <= 2024:
        return "launch_through_2024"
    if created_at.year == 2025:
        return "2025"
    return "2026_through_cutoff"
