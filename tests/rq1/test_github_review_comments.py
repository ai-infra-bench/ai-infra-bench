import json
from pathlib import Path

from ai_infra_bench.rq1.github_review_comments import collect_review_comments


class FakeClient:
    def review_comment_page(self, repository: str, next_url: str | None):
        assert repository == "vllm-project/vllm"
        assert next_url is None
        return [
            {
                "id": 1,
                "created_at": "2026-08-01T00:00:00Z",
                "pull_request_url": (
                    "https://api.github.com/repos/vllm-project/vllm/pulls/10"
                ),
            },
            {
                "id": 2,
                "created_at": "2026-08-09T00:00:00Z",
                "pull_request_url": (
                    "https://api.github.com/repos/vllm-project/vllm/pulls/11"
                ),
            },
        ], {"limit": 5000, "remaining": 4999, "reset": 0}, None


def test_review_comments_filter_cutoff_and_map_pr(tmp_path: Path) -> None:
    manifest = collect_review_comments(
        tmp_path,
        repository="vllm-project/vllm",
        cutoff="2026-08-08T23:59:59Z",
        client=FakeClient(),
    )
    record = json.loads((tmp_path / "github_review_comments.jsonl").read_text())

    assert record["source_id"] == "vllm__pr__10"
    assert manifest["records"] == 1
    assert manifest["after_cutoff_excluded"] == 1
