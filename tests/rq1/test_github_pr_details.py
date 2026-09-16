import json
from pathlib import Path

from ai_infra_bench.rq1.github_pr_details import (
    DETAIL_BATCH_QUERY,
    collect_pr_details,
)


class FakeClient:
    def execute(self, query: str, variables: dict):
        assert query == DETAIL_BATCH_QUERY
        assert variables == {"ids": ["PR_node_1"]}
        page = {"hasNextPage": False, "endCursor": None}
        author = {
            "author": {"login": "reviewer", "__typename": "User"},
            "authorAssociation": "MEMBER",
        }
        return {
            "nodes": [
                {
                    "id": "PR_node_1",
                    "databaseId": 1,
                    "number": 1,
                    "comments": {
                        "nodes": [
                            {
                                "id": "comment-1",
                                "databaseId": 10,
                                "url": "https://example.test/comment/1",
                                "body": "Review please",
                                "createdAt": "2026-08-01T01:00:00Z",
                                "updatedAt": "2026-08-01T01:00:00Z",
                                **author,
                            },
                            {
                                "id": "comment-2",
                                "databaseId": 11,
                                "url": "https://example.test/comment/2",
                                "body": "After cutoff",
                                "createdAt": "2026-08-09T01:00:00Z",
                                "updatedAt": "2026-08-09T01:00:00Z",
                                **author,
                            },
                        ],
                        "pageInfo": page,
                        "totalCount": 2,
                    },
                    "reviews": {
                        "nodes": [
                            {
                                "id": "review-1",
                                "databaseId": 20,
                                "url": "https://example.test/review/1",
                                "body": "LGTM",
                                "state": "APPROVED",
                                "createdAt": "2026-08-02T00:00:00Z",
                                "updatedAt": "2026-08-02T00:00:00Z",
                                "submittedAt": "2026-08-02T00:00:00Z",
                                "commit": {"oid": "abc"},
                                **author,
                            }
                        ],
                        "pageInfo": page,
                        "totalCount": 1,
                    },
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "abc",
                                    "authoredDate": "2026-08-01T00:00:00Z",
                                    "committedDate": "2026-08-01T00:00:00Z",
                                    "pushedDate": None,
                                    "author": {"user": {"login": "author"}},
                                    "committer": {
                                        "user": {"login": "author"}
                                    },
                                }
                            }
                        ],
                        "pageInfo": page,
                        "totalCount": 1,
                    },
                    "reviewThreads": {
                        "nodes": [],
                        "pageInfo": page,
                        "totalCount": 0,
                    },
                }
            ],
            "rateLimit": {"cost": 4, "remaining": 4996, "resetAt": ""},
        }


def test_detail_snapshot_filters_cutoff_and_writes_checkpoint(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "prs.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "source_id": "vllm__pr__1",
                "repo": "vllm-project/vllm",
                "number": 1,
                "node_id": "PR_node_1",
            }
        )
        + "\n"
    )

    manifest = collect_pr_details(
        input_path,
        tmp_path / "details",
        cutoff="2026-08-08T23:59:59Z",
        client=FakeClient(),
        batch_size=1,
    )
    detail = json.loads(
        (tmp_path / "details/github_pr_details.jsonl").read_text()
    )
    checkpoint = json.loads(
        (tmp_path / "details/github_pr_details.checkpoint.json").read_text()
    )

    assert manifest["complete"] is True
    assert detail["comments"]["observed_total_count"] == 2
    assert detail["comments"]["at_cutoff_count"] == 1
    assert detail["reviews"]["at_cutoff_count"] == 1
    assert detail["commits"]["nodes"][0]["cutoff_time_source"] == (
        "committedDate_proxy"
    )
    assert checkpoint["complete"] is True


def test_detail_snapshot_resumes_completed_records(tmp_path: Path) -> None:
    input_path = tmp_path / "prs.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "source_id": "vllm__pr__1",
                "repo": "vllm-project/vllm",
                "number": 1,
                "node_id": "PR_node_1",
            }
        )
        + "\n"
    )
    output_dir = tmp_path / "details"
    collect_pr_details(
        input_path,
        output_dir,
        cutoff="2026-08-08T23:59:59Z",
        client=FakeClient(),
        batch_size=1,
    )

    class NoCalls:
        def execute(self, query: str, variables: dict):
            raise AssertionError("completed records must not be requested")

    manifest = collect_pr_details(
        input_path,
        output_dir,
        cutoff="2026-08-08T23:59:59Z",
        client=NoCalls(),
        batch_size=1,
    )

    assert manifest["records"] == 1
    assert sum(
        1 for _ in (output_dir / "github_pr_details.jsonl").open()
    ) == 1
