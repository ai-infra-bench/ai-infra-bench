import json
from pathlib import Path

from ai_infra_bench.rq1.issue_metrics import (
    derive_issue_metrics,
    is_substantive_comment,
)


def _write(path: Path, values: list[dict]) -> None:
    path.write_text("".join(json.dumps(value) + "\n" for value in values))


def _comment(
    login: str,
    body: str,
    created_at: str,
    *,
    association: str = "NONE",
    actor_type: str = "User",
) -> dict:
    return {
        "author": {"login": login, "__typename": actor_type},
        "authorAssociation": association,
        "body": body,
        "createdAt": created_at,
    }


def _event(
    kind: str,
    created_at: str,
    *,
    login: str = "maintainer",
    actor_type: str = "User",
) -> dict:
    return {
        "__typename": kind,
        "createdAt": created_at,
        "actor": {"login": login, "__typename": actor_type},
    }


def test_substantive_rule_rejects_administration_and_acknowledgement() -> None:
    assert not is_substantive_comment(None)
    assert not is_substantive_comment("Thanks for reporting this issue!")
    assert not is_substantive_comment("/assign @maintainer")
    assert not is_substantive_comment("> quoted diagnostic text")
    assert is_substantive_comment("Could you please share the server logs?")
    assert is_substantive_comment("Try this:\n```python\nrun()\n```")


def test_issue_metrics_reconstruct_flow_response_and_censoring(
    tmp_path: Path,
) -> None:
    github = tmp_path / "issues.jsonl"
    details = tmp_path / "details.jsonl"
    _write(
        github,
        [
            {
                "source_id": "vllm__issue__1",
                "number": 1,
                "created_at": "2026-01-01T00:00:00Z",
                "closed_at": "2026-01-20T00:00:00Z",
                "user": {"login": "author", "type": "User"},
                "author_association": "CONTRIBUTOR",
            },
            {
                "source_id": "vllm__issue__2",
                "number": 2,
                "created_at": "2026-01-15T00:00:00Z",
                "closed_at": None,
                "user": {"login": "author2", "type": "User"},
                "author_association": "NONE",
            },
            {
                "source_id": "vllm__issue__3",
                "number": 3,
                "created_at": "2026-01-10T00:00:00Z",
                "closed_at": None,
                "user": {"login": "automation[bot]", "type": "Bot"},
                "author_association": "NONE",
            },
        ],
    )
    _write(
        details,
        [
            {
                "source_id": "vllm__issue__1",
                "api_missing": False,
                "comments": {
                    "nodes": [
                        _comment(
                            "author",
                            "Self reply with more details",
                            "2026-01-01T01:00:00Z",
                        ),
                        _comment(
                            "helper[bot]",
                            "Automated response with many words",
                            "2026-01-01T02:00:00Z",
                            actor_type="Bot",
                        ),
                        _comment(
                            "contributor",
                            "Thanks for reporting this issue!",
                            "2026-01-01T03:00:00Z",
                        ),
                        _comment(
                            "maintainer",
                            "Could you please share the full server logs?",
                            "2026-01-01T04:00:00Z",
                            association="MEMBER",
                        ),
                    ]
                },
                "timelineItems": {
                    "nodes": [
                        _event("ClosedEvent", "2026-01-05T00:00:00Z"),
                        _event("ReopenedEvent", "2026-01-10T00:00:00Z"),
                        _event("ClosedEvent", "2026-01-20T00:00:00Z"),
                    ]
                },
            },
            {
                "source_id": "vllm__issue__2",
                "api_missing": False,
                "comments": {"nodes": []},
                "timelineItems": {"nodes": []},
            },
            {
                "source_id": "vllm__issue__3",
                "api_missing": False,
                "comments": {"nodes": []},
                "timelineItems": {"nodes": []},
            },
        ],
    )

    records, summary = derive_issue_metrics(
        details,
        github,
        cutoff="2026-01-31T23:59:59Z",
    )

    first = records[0]
    assert first["qualifying_human_comments"] == 2
    assert first["time_to_first_human_response_hours"] == 3.0
    assert first["time_to_first_maintainer_response_hours"] == 4.0
    assert first["time_to_first_substantive_response_hours"] == 4.0
    assert first["time_to_first_close_days"] == 4.0
    assert first["status_at_cutoff"] == "closed"
    assert first["close_transitions"] == 2
    assert first["reopen_transitions"] == 1

    assert summary["population"] == {
        "all_issues": 3,
        "human_issues": 2,
        "bot_issues": 1,
        "unknown_actor_type_issues": 0,
        "api_missing": 0,
        "human_status_at_cutoff": {"closed": 1, "open": 1},
    }
    response = summary["human_overall"]["first_maintainer_response"]
    assert response["event_percent"] == 50.0
    assert response["fixed_windows"]["24"] == {
        "eligible": 2,
        "events": 1,
        "percent": 50.0,
        "wilson_low_percent": 9.5,
        "wilson_high_percent": 90.5,
    }
    close = summary["human_overall"]["time_to_first_close"]
    assert close["right_censored"] == 1
    assert close["kaplan_meier"]["median_days"] == 4.0
    assert summary["monthly_issue_flow"]["2026-01"] == {
        "period_end": "2026-01-31T23:59:59Z",
        "complete_month": True,
        "new_human_issues": 2,
        "close_transitions": 2,
        "unique_issues_closed": 1,
        "automated_close_transitions": 0,
        "human_close_transitions": 2,
        "unknown_actor_close_transitions": 0,
        "unique_issues_closed_by_automation": 0,
        "reopen_transitions": 1,
        "automated_reopen_transitions": 0,
        "end_backlog": 1,
        "end_backlog_older_30_days": 0,
        "end_backlog_older_90_days": 0,
        "end_backlog_older_180_days": 0,
        "backlog_change": 1,
        "state_reconciliation_adjustment": 0,
        "active_issue_maintainer_responders": 1,
        "active_substantive_maintainer_responders": 1,
        "new_issues_per_active_issue_responder": 2.0,
        "backlog_per_active_issue_responder": 1.0,
    }


def test_issue_metrics_fall_back_to_base_close_when_timeline_is_missing(
    tmp_path: Path,
) -> None:
    github = tmp_path / "issues.jsonl"
    details = tmp_path / "details.jsonl"
    _write(
        github,
        [
            {
                "source_id": "vllm__issue__9",
                "number": 9,
                "created_at": "2025-01-01T00:00:00Z",
                "closed_at": "2025-01-03T00:00:00Z",
                "closed_by": {"login": "maintainer", "type": "User"},
                "user": {"login": "author", "type": "User"},
                "author_association": "NONE",
            }
        ],
    )
    _write(
        details,
        [{"source_id": "vllm__issue__9", "api_missing": True}],
    )

    records, summary = derive_issue_metrics(
        details,
        github,
        cutoff="2025-01-31T23:59:59Z",
    )

    assert records[0]["lifecycle_fallback_used"] is True
    assert records[0]["status_at_cutoff"] == "closed"
    assert records[0]["time_to_first_close_days"] == 2.0
    assert summary["population"]["api_missing"] == 1


def test_issue_metrics_report_automated_closures_separately(
    tmp_path: Path,
) -> None:
    github = tmp_path / "issues.jsonl"
    details = tmp_path / "details.jsonl"
    _write(
        github,
        [
            {
                "source_id": "vllm__issue__10",
                "number": 10,
                "created_at": "2025-01-01T00:00:00Z",
                "closed_at": "2025-01-10T00:00:00Z",
                "user": {"login": "author", "type": "User"},
                "author_association": "NONE",
            }
        ],
    )
    _write(
        details,
        [
            {
                "source_id": "vllm__issue__10",
                "api_missing": False,
                "comments": {"nodes": []},
                "timelineItems": {
                    "nodes": [
                        _event(
                            "ClosedEvent",
                            "2025-01-10T00:00:00Z",
                            login="github-actions",
                            actor_type="Bot",
                        )
                    ]
                },
            }
        ],
    )

    records, summary = derive_issue_metrics(
        details,
        github,
        cutoff="2025-01-31T23:59:59Z",
    )

    assert records[0]["first_close_actor_group"] == "automation"
    flow = summary["monthly_issue_flow"]["2025-01"]
    assert flow["automated_close_transitions"] == 1
    assert flow["human_close_transitions"] == 0
    assert summary["human_overall"]["first_close_actor_group"] == {
        "automation": 1
    }
