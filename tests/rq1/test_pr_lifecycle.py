import json
from pathlib import Path

from ai_infra_bench.rq1.pr_lifecycle import derive_pr_lifecycle


def _write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_text("".join(json.dumps(value) + "\n" for value in values))


def _label(source_id: str, subsystem: str = "models") -> dict:
    return {
        "source_id": source_id,
        "classification": {
            "source_id": source_id,
            "subsystems": [subsystem],
            "accelerator_scope": "agnostic",
            "accelerators": [],
            "subsystem_confidence": "high",
            "accelerator_confidence": "high",
            "rationale": "Test rationale",
            "evidence": [],
        },
    }


def test_lifecycle_distinguishes_events_competing_events_and_censoring(
    tmp_path: Path,
) -> None:
    labels = tmp_path / "labels.jsonl"
    manifest = tmp_path / "manifest.jsonl"
    github = tmp_path / "github.jsonl"
    source_ids = ["vllm__pr__1", "vllm__pr__2", "vllm__pr__3"]
    _write_jsonl(labels, [_label(source_id) for source_id in source_ids])
    _write_jsonl(
        manifest,
        [
            {
                "source_id": source_ids[0],
                "number": 1,
                "created_at": "2024-01-01T00:00:00Z",
                "merged_at_by_cutoff": "2024-01-03T00:00:00Z",
                "file_paths_source": "default_branch_git_history",
            },
            {
                "source_id": source_ids[1],
                "number": 2,
                "created_at": "2025-01-01T00:00:00Z",
                "merged_at_by_cutoff": None,
                "file_paths_source": "unavailable_in_base_snapshot",
            },
            {
                "source_id": source_ids[2],
                "number": 3,
                "created_at": "2026-08-01T00:00:00Z",
                "merged_at_by_cutoff": None,
                "file_paths_source": "unavailable_in_base_snapshot",
            },
        ],
    )
    _write_jsonl(
        github,
        [
            {
                "source_id": source_ids[0],
                "user": {"login": "maintainer", "type": "User"},
                "author_association": "MEMBER",
                "closed_at": "2024-01-03T00:00:00Z",
            },
            {
                "source_id": source_ids[1],
                "user": {"login": "contributor", "type": "User"},
                "author_association": "CONTRIBUTOR",
                "closed_at": "2025-01-05T00:00:00Z",
            },
            {
                "source_id": source_ids[2],
                "user": {"login": "contributor2", "type": "User"},
                "author_association": "NONE",
                "closed_at": "2026-08-10T00:00:00Z",
            },
        ],
    )

    records, summary = derive_pr_lifecycle(
        labels,
        manifest,
        github,
        cutoff="2026-08-08T00:00:00Z",
    )

    assert [record["status_at_cutoff"] for record in records] == [
        "merged",
        "closed_unmerged",
        "open",
    ]
    assert records[0]["time_to_merge_days"] == 2.0
    assert records[0]["author_group"] == "maintainer"
    assert records[1]["merge_analysis_state"] == "competing_event"
    assert records[1]["time_to_close_days"] == 4.0
    assert records[2]["merge_analysis_state"] == "right_censored"
    assert records[2]["observed_duration_days"] == 7.0
    assert summary["human_outcome_durations"]["merged_time_to_merge"] == {
        "count": 1,
        "median": 2.0,
        "p75": 2.0,
        "p90": 2.0,
    }


def test_lifecycle_excludes_bots_from_human_summary(tmp_path: Path) -> None:
    labels = tmp_path / "labels.jsonl"
    manifest = tmp_path / "manifest.jsonl"
    github = tmp_path / "github.jsonl"
    source_id = "vllm__pr__1"
    _write_jsonl(labels, [_label(source_id)])
    _write_jsonl(
        manifest,
        [
            {
                "source_id": source_id,
                "number": 1,
                "created_at": "2026-01-01T00:00:00Z",
                "merged_at_by_cutoff": None,
                "file_paths_source": "unavailable_in_base_snapshot",
            }
        ],
    )
    _write_jsonl(
        github,
        [
            {
                "source_id": source_id,
                "user": {"login": "automation", "type": "Bot"},
                "author_association": "NONE",
                "closed_at": None,
            }
        ],
    )

    records, summary = derive_pr_lifecycle(
        labels,
        manifest,
        github,
        cutoff="2026-08-08T00:00:00Z",
    )

    assert records[0]["author_group"] == "bot"
    assert summary["population"]["human_prs"] == 0
    assert summary["population"]["bot_prs"] == 1
