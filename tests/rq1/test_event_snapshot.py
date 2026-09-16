import gzip
import json
from pathlib import Path

import pytest

from ai_infra_bench.rq1.coverage import event_coverage
from ai_infra_bench.rq1.event_snapshot import snapshot_query


def test_snapshot_query_freezes_repository_cutoff_and_event_types() -> None:
    query = snapshot_query("vllm-project/vllm", "2026-08-08T23:59:59Z")

    assert "repo_name = 'vllm-project/vllm'" in query
    assert "2026-08-08 23:59:59" in query
    assert "PullRequestReviewEvent" in query
    assert "SELECT DISTINCT" in query


def test_snapshot_query_rejects_injection_and_naive_time() -> None:
    with pytest.raises(ValueError, match="invalid GitHub repository"):
        snapshot_query("vllm-project/vllm' OR 1=1", "2026-08-08T00:00:00Z")
    with pytest.raises(ValueError, match="timezone"):
        snapshot_query("vllm-project/vllm", "2026-08-08T00:00:00")


def test_coverage_marks_event_source_as_incomplete(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl.gz"
    rows = [
        {
            "event_type": "PullRequestEvent",
            "action": "opened",
            "number": 2,
            "created_at": "2025-01-01 00:00:00",
        },
        {
            "event_type": "IssuesEvent",
            "action": "opened",
            "number": 3,
            "created_at": "2025-01-02 00:00:00",
        },
    ]
    with gzip.open(events, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")
    merged = tmp_path / "merged.jsonl"
    merged.write_text(
        json.dumps({"number": 1}) + "\n" + json.dumps({"number": 2}) + "\n"
    )

    result = event_coverage(events, merged)

    assert result["merged_pr_event_coverage"] == 0.5
    assert result["suitable_for_complete_arrival_counts"] is False
