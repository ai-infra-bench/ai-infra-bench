import json
from pathlib import Path

from ai_infra_bench.rq1.github_issue_details import (
    CONNECTION_QUERIES,
    ISSUE_DETAIL_BATCH_QUERY,
    collect_issue_details,
)


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, query: str, variables: dict):
        self.calls += 1
        author = {
            "author": {"login": "maintainer", "__typename": "User"},
            "authorAssociation": "MEMBER",
        }
        if query == ISSUE_DETAIL_BATCH_QUERY:
            assert variables == {"ids": ["I_node_1"]}
            return {
                "nodes": [
                    {
                        "id": "I_node_1",
                        "databaseId": 1,
                        "number": 1,
                        "comments": {
                            "nodes": [
                                {
                                    "id": "comment-1",
                                    "body": "Please share the logs.",
                                    "createdAt": "2026-08-01T01:00:00Z",
                                    "updatedAt": "2026-08-01T01:00:00Z",
                                    **author,
                                }
                            ],
                            "pageInfo": {
                                "hasNextPage": True,
                                "endCursor": "comment-cursor",
                            },
                            "totalCount": 2,
                        },
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "ClosedEvent",
                                    "id": "close-1",
                                    "createdAt": "2026-08-02T00:00:00Z",
                                    "actor": {
                                        "login": "maintainer",
                                        "__typename": "User",
                                    },
                                },
                                {
                                    "__typename": "ReopenedEvent",
                                    "id": "reopen-after-cutoff",
                                    "createdAt": "2026-08-09T00:00:00Z",
                                    "actor": {
                                        "login": "maintainer",
                                        "__typename": "User",
                                    },
                                },
                            ],
                            "pageInfo": {
                                "hasNextPage": False,
                                "endCursor": None,
                            },
                            "totalCount": 2,
                        },
                    }
                ],
                "rateLimit": {"remaining": 4990},
            }
        assert query == CONNECTION_QUERIES["comments"]
        assert variables == {"id": "I_node_1", "cursor": "comment-cursor"}
        return {
            "node": {
                "comments": {
                    "nodes": [
                        {
                            "id": "comment-after-cutoff",
                            "body": "Late response",
                            "createdAt": "2026-08-10T00:00:00Z",
                            "updatedAt": "2026-08-10T00:00:00Z",
                            **author,
                        }
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "totalCount": 2,
                }
            },
            "rateLimit": {"remaining": 4989},
        }


def test_issue_details_paginate_filter_cutoff_and_resume(tmp_path: Path) -> None:
    input_path = tmp_path / "issues.jsonl"
    input_path.write_text(
        json.dumps(
            {
                "source_id": "vllm__issue__1",
                "repo": "vllm-project/vllm",
                "number": 1,
                "node_id": "I_node_1",
            }
        )
        + "\n"
    )
    output_dir = tmp_path / "details"
    client = FakeClient()

    manifest = collect_issue_details(
        input_path,
        output_dir,
        cutoff="2026-08-08T23:59:59Z",
        client=client,
        batch_size=1,
    )
    detail = json.loads(
        (output_dir / "github_issue_details.jsonl").read_text()
    )

    assert manifest["complete"] is True
    assert manifest["requests_this_run"] == 2
    assert client.calls == 2
    assert detail["comments"]["retrieved_count"] == 2
    assert detail["comments"]["at_cutoff_count"] == 1
    assert detail["timelineItems"]["at_cutoff_count"] == 1

    class NoCalls:
        def execute(self, query: str, variables: dict):
            raise AssertionError("completed records must not be requested")

    resumed = collect_issue_details(
        input_path,
        output_dir,
        cutoff="2026-08-08T23:59:59Z",
        client=NoCalls(),
        batch_size=1,
    )
    assert resumed["records"] == 1
    assert resumed["requests_this_run"] == 0
