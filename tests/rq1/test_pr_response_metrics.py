import json
from pathlib import Path

from ai_infra_bench.rq1.pr_response_metrics import derive_pr_response_metrics


def _write(path: Path, values: list[dict]) -> None:
    path.write_text("".join(json.dumps(value) + "\n" for value in values))


def test_response_metrics_exclude_author_and_bot_activity(tmp_path: Path) -> None:
    source_id = "vllm__pr__1"
    responses = tmp_path / "responses.jsonl"
    github = tmp_path / "github.jsonl"
    labels = tmp_path / "labels.jsonl"
    author = {"login": "author", "__typename": "User"}
    bot = {"login": "bot[bot]", "__typename": "Bot"}
    maintainer = {"login": "maintainer", "__typename": "User"}
    _write(
        responses,
        [
            {
                "source_id": source_id,
                "api_missing": False,
                "comments": {
                    "nodes": [
                        {
                            "author": author,
                            "authorAssociation": "CONTRIBUTOR",
                            "createdAt": "2026-01-01T01:00:00Z",
                        },
                        {
                            "author": bot,
                            "authorAssociation": "NONE",
                            "createdAt": "2026-01-01T02:00:00Z",
                        },
                        {
                            "author": maintainer,
                            "authorAssociation": "MEMBER",
                            "createdAt": "2026-01-01T03:00:00Z",
                        },
                    ]
                },
                "reviews": {
                    "nodes": [
                        {
                            "author": maintainer,
                            "authorAssociation": "MEMBER",
                            "state": "APPROVED",
                            "submittedAt": "2026-01-01T02:30:00Z",
                            "createdAt": "2026-01-01T02:00:00Z",
                        }
                    ]
                },
            }
        ],
    )
    _write(
        github,
        [
            {
                "source_id": source_id,
                "number": 1,
                "created_at": "2026-01-01T00:00:00Z",
                "closed_at": "2026-01-02T00:00:00Z",
                "user": {"login": "author", "type": "User"},
                "author_association": "CONTRIBUTOR",
            }
        ],
    )
    _write(
        labels,
        [
            {
                "source_id": source_id,
                "classification": {
                    "source_id": source_id,
                    "subsystems": ["models"],
                    "accelerator_scope": "agnostic",
                    "accelerators": [],
                    "subsystem_confidence": "high",
                    "accelerator_confidence": "high",
                    "rationale": "test",
                    "evidence": [],
                },
            }
        ],
    )

    records, summary = derive_pr_response_metrics(
        responses,
        github,
        labels,
        cutoff="2026-08-08T23:59:59Z",
    )

    record = records[0]
    assert record["qualifying_human_comments"] == 1
    assert record["time_to_first_maintainer_comment_hours"] == 3.0
    assert record["time_to_first_formal_review_hours"] == 2.5
    assert record["time_to_first_maintainer_activity_hours"] == 2.5
    assert record["first_maintainer_activity_state"] == "event"
    assert summary["human_overall"]["first_maintainer_activity"]["median"] == 2.5
    assert summary["monthly_pr_review_demand"]["2026-01"] == {
        "new_human_prs": 1,
        "active_reviewers": 1,
        "active_pr_maintainers_lower_bound": 1,
        "prs_receiving_formal_review": 1,
        "formal_review_submissions": 1,
        "new_prs_per_active_reviewer": 1.0,
        "reviewed_prs_per_active_reviewer": 1.0,
        "review_submissions_per_active_reviewer": 1.0,
    }


def test_response_metrics_retain_right_censoring(tmp_path: Path) -> None:
    source_id = "vllm__pr__2"
    responses = tmp_path / "responses.jsonl"
    github = tmp_path / "github.jsonl"
    labels = tmp_path / "labels.jsonl"
    _write(
        responses,
        [
            {
                "source_id": source_id,
                "api_missing": False,
                "comments": {"nodes": []},
                "reviews": {"nodes": []},
            }
        ],
    )
    _write(
        github,
        [
            {
                "source_id": source_id,
                "number": 2,
                "created_at": "2026-08-01T00:00:00Z",
                "closed_at": None,
                "user": {"login": "author", "type": "User"},
                "author_association": "NONE",
            }
        ],
    )
    _write(
        labels,
        [
            {
                "source_id": source_id,
                "classification": {
                    "source_id": source_id,
                    "subsystems": ["other"],
                    "accelerator_scope": "agnostic",
                    "accelerators": [],
                    "subsystem_confidence": "high",
                    "accelerator_confidence": "high",
                    "rationale": "test",
                    "evidence": [],
                },
            }
        ],
    )

    records, _ = derive_pr_response_metrics(
        responses,
        github,
        labels,
        cutoff="2026-08-08T00:00:00Z",
    )

    assert records[0]["first_maintainer_activity_state"] == (
        "open_right_censored"
    )
    assert records[0]["response_observation_hours"] == 168.0
