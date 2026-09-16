"""Resumable GitHub GraphQL detail snapshot for issues."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from ai_infra_bench.rq1.github_snapshot import _atomic_json

AUTHOR_FIELDS = "author { login __typename } authorAssociation"
COMMENT_FIELDS = f"""
id databaseId url body createdAt updatedAt {AUTHOR_FIELDS}
"""
TIMELINE_FIELDS = """
__typename
... on ClosedEvent {
  id createdAt actor { login __typename }
}
... on ReopenedEvent {
  id createdAt actor { login __typename }
}
"""

ISSUE_DETAIL_BATCH_QUERY = f"""query Rq1IssueDetailBatch($ids: [ID!]!) {{
  nodes(ids: $ids) {{
    ... on Issue {{
      id databaseId number
      comments(first: 100) {{
        nodes {{ {COMMENT_FIELDS} }}
        pageInfo {{ hasNextPage endCursor }}
        totalCount
      }}
      timelineItems(
        first: 100
        itemTypes: [CLOSED_EVENT, REOPENED_EVENT]
      ) {{
        nodes {{ {TIMELINE_FIELDS} }}
        pageInfo {{ hasNextPage endCursor }}
        totalCount
      }}
    }}
  }}
  rateLimit {{ cost remaining resetAt }}
}}"""

CONNECTION_QUERIES = {
    "comments": f"""query Rq1IssueComments($id: ID!, $cursor: String) {{
      node(id: $id) {{ ... on Issue {{
        comments(first: 100, after: $cursor) {{
          nodes {{ {COMMENT_FIELDS} }}
          pageInfo {{ hasNextPage endCursor }} totalCount
        }}
      }} }}
      rateLimit {{ cost remaining resetAt }}
    }}""",
    "timelineItems": f"""query Rq1IssueTimeline(
      $id: ID!, $cursor: String
    ) {{
      node(id: $id) {{ ... on Issue {{
        timelineItems(
          first: 100
          after: $cursor
          itemTypes: [CLOSED_EVENT, REOPENED_EVENT]
        ) {{
          nodes {{ {TIMELINE_FIELDS} }}
          pageInfo {{ hasNextPage endCursor }} totalCount
        }}
      }} }}
      rateLimit {{ cost remaining resetAt }}
    }}""",
}


class GraphQLExecutor(Protocol):
    """Structural interface used by the issue detail collector."""

    def execute(
        self, query: str, variables: dict[str, Any]
    ) -> dict[str, Any]: ...


def collect_issue_details(
    input_path: Path,
    output_dir: Path,
    *,
    cutoff: str,
    client: GraphQLExecutor,
    batch_size: int = 10,
    concurrency: int = 1,
) -> dict[str, Any]:
    """Collect comments and close/reopen events for every census issue."""
    if batch_size < 1 or batch_size > 25:
        raise ValueError("batch_size must be between 1 and 25")
    if concurrency < 1 or concurrency > 32:
        raise ValueError("concurrency must be between 1 and 32")
    cutoff_at = _parse_time(cutoff)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "github_issue_details.jsonl"
    checkpoint_path = output_dir / "github_issue_details.checkpoint.json"
    completed = _existing_source_ids(output_path)
    pending = [
        record
        for record in _read_jsonl(input_path)
        if record["source_id"] not in completed
    ]
    total = len(completed) + len(pending)
    retrieved_at = datetime.now(UTC).isoformat()
    requests = 0
    batches = [
        pending[start : start + batch_size]
        for start in range(0, len(pending), batch_size)
    ]

    def fetch(batch: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, Any]:
        return _fetch_batch(
            batch,
            cutoff=cutoff,
            cutoff_at=cutoff_at,
            retrieved_at=retrieved_at,
            client=client,
        )

    with (
        ThreadPoolExecutor(max_workers=concurrency) as executor,
        output_path.open("a", encoding="utf-8") as destination,
    ):
        for batch_number, (details, batch_requests, rate) in enumerate(
            executor.map(fetch, batches), start=1
        ):
            requests += batch_requests
            for detail in details:
                destination.write(
                    json.dumps(detail, ensure_ascii=False, sort_keys=True) + "\n"
                )
                completed.add(detail["source_id"])
            destination.flush()
            _atomic_json(
                checkpoint_path,
                {
                    "complete": len(completed) == total,
                    "records": len(completed),
                    "total": total,
                    "requests_this_run": requests,
                },
            )
            if batch_number % 25 == 0 or len(completed) == total:
                print(
                    f"Issue details: records={len(completed)}/{total} "
                    f"requests={requests} token_remaining={rate.get('remaining')}",
                    file=sys.stderr,
                    flush=True,
                )

    manifest = {
        "schema_version": "1.0",
        "source": "GitHub GraphQL API",
        "cutoff": cutoff,
        "retrieved_at": retrieved_at,
        "input": str(input_path),
        "output": str(output_path),
        "records": len(completed),
        "requests_this_run": requests,
        "concurrency": concurrency,
        "complete": len(completed) == total,
        "connections": ["comments", "timelineItems"],
    }
    _atomic_json(output_dir / "github_issue_details.manifest.json", manifest)
    return manifest


def _fetch_batch(
    batch: list[dict[str, Any]],
    *,
    cutoff: str,
    cutoff_at: datetime,
    retrieved_at: str,
    client: GraphQLExecutor,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    ids = [record["node_id"] for record in batch]
    data = client.execute(ISSUE_DETAIL_BATCH_QUERY, {"ids": ids})
    requests = 1
    nodes = data["nodes"]
    if len(nodes) != len(batch):
        raise RuntimeError("GitHub returned an unexpected node count")
    details = []
    for base, node in zip(batch, nodes, strict=True):
        if node is None:
            details.append(_missing_record(base, cutoff, retrieved_at))
            continue
        connections = {}
        for name in ("comments", "timelineItems"):
            connection = node[name]
            values = list(connection["nodes"])
            cursor = connection["pageInfo"]["endCursor"]
            has_next = connection["pageInfo"]["hasNextPage"]
            while has_next:
                page = client.execute(
                    CONNECTION_QUERIES[name],
                    {"id": node["id"], "cursor": cursor},
                )
                requests += 1
                connection_page = page["node"][name]
                values.extend(connection_page["nodes"])
                cursor = connection_page["pageInfo"]["endCursor"]
                has_next = connection_page["pageInfo"]["hasNextPage"]
            frozen = _filter_by_cutoff(values, "createdAt", cutoff_at)
            connections[name] = {
                "observed_total_count": connection["totalCount"],
                "retrieved_count": len(values),
                "at_cutoff_count": len(frozen),
                "nodes": frozen,
            }
        details.append(
            {
                "schema_version": "1.0",
                "repo": base["repo"],
                "source_id": base["source_id"],
                "source_type": "issue_detail",
                "number": base["number"],
                "node_id": base["node_id"],
                "snapshot_cutoff": cutoff,
                "retrieved_at": retrieved_at,
                "api_missing": False,
                **connections,
            }
        )
    return details, requests, data.get("rateLimit", {})


def _missing_record(
    base: dict[str, Any], cutoff: str, retrieved_at: str
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "repo": base["repo"],
        "source_id": base["source_id"],
        "source_type": "issue_detail",
        "number": base["number"],
        "node_id": base["node_id"],
        "snapshot_cutoff": cutoff,
        "retrieved_at": retrieved_at,
        "api_missing": True,
    }


def _filter_by_cutoff(
    values: list[dict[str, Any]], field: str, cutoff: datetime
) -> list[dict[str, Any]]:
    return [value for value in values if _parse_time(value[field]) <= cutoff]


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _existing_source_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as source:
        return {
            json.loads(line)["source_id"] for line in source if line.strip()
        }
