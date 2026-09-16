import json
from pathlib import Path

from ai_infra_bench.rq1.github_rest import _next_link, collect_rest_base_snapshot


class FakeClient:
    def issue_page(self, repository: str, next_url: str | None):
        assert repository == "vllm-project/vllm"
        if next_url is not None:
            return [], {"limit": 5000, "remaining": 4998, "reset": 0}, None
        common = {
            "labels": [],
            "state": "open",
            "body": "body",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        return [
            {
                **common,
                "id": 1,
                "number": 10,
                "title": "Issue",
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                **common,
                "id": 2,
                "number": 11,
                "title": "PR",
                "created_at": "2026-01-02T00:00:00Z",
                "pull_request": {"merged_at": None},
            },
            {
                **common,
                "id": 3,
                "number": 12,
                "title": "After cutoff",
                "created_at": "2026-09-01T00:00:00Z",
            },
        ], {"limit": 5000, "remaining": 4999, "reset": 0}, None


def test_rest_snapshot_splits_issues_and_prs_and_stops_at_cutoff(
    tmp_path: Path,
) -> None:
    result = collect_rest_base_snapshot(
        tmp_path,
        repository="vllm-project/vllm",
        cutoff="2026-08-08T23:59:59Z",
        client=FakeClient(),
    )
    issue = json.loads((tmp_path / "github_issues.jsonl").read_text())
    pr = json.loads((tmp_path / "github_pull_requests.jsonl").read_text())

    assert result["objects"]["issue"]["records"] == 1
    assert result["objects"]["pull_request"]["records"] == 1
    assert issue["source_id"] == "vllm__issue__10"
    assert pr["source_id"] == "vllm__pr__11"


def test_next_link_extracts_cursor_url() -> None:
    header = (
        '<https://api.github.com/repositories/1/issues?after=abc&page=2>; '
        'rel="next"'
    )

    assert _next_link(header) == (
        "https://api.github.com/repositories/1/issues?after=abc&page=2"
    )
    assert _next_link(None) is None
