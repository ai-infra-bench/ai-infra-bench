"""Resumable GitHub GraphQL detail snapshot for pull requests."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from ai_infra_bench.rq1.github_snapshot import (
    GitHubGraphQLClient,
    GitHubRateLimitError,
    _atomic_json,
)

PAGE_SIZE = 100

AUTHOR_FIELDS = "author { login __typename } authorAssociation"
COMMENT_FIELDS = f"""
id databaseId url body createdAt updatedAt {AUTHOR_FIELDS}
"""
REVIEW_FIELDS = f"""
id databaseId url body state createdAt updatedAt submittedAt
commit {{ oid }} {AUTHOR_FIELDS}
"""
COMMIT_FIELDS = """
commit {
  oid authoredDate committedDate pushedDate
  author { user { login } }
  committer { user { login } }
}
"""
THREAD_FIELDS = f"""
id isResolved isOutdated path line originalLine startLine
comments(first: 100) {{
  nodes {{ {COMMENT_FIELDS} }}
  pageInfo {{ hasNextPage endCursor }}
  totalCount
}}
"""

DETAIL_BATCH_QUERY = f"""query Rq1PrDetailBatch($ids: [ID!]!) {{
  nodes(ids: $ids) {{
    ... on PullRequest {{
      id databaseId number
      comments(first: 100) {{
        nodes {{ {COMMENT_FIELDS} }}
        pageInfo {{ hasNextPage endCursor }}
        totalCount
      }}
      reviews(first: 100) {{
        nodes {{ {REVIEW_FIELDS} }}
        pageInfo {{ hasNextPage endCursor }}
        totalCount
      }}
      commits(first: 100) {{
        nodes {{ {COMMIT_FIELDS} }}
        pageInfo {{ hasNextPage endCursor }}
        totalCount
      }}
      reviewThreads(first: 100) {{
        nodes {{ {THREAD_FIELDS} }}
        pageInfo {{ hasNextPage endCursor }}
        totalCount
      }}
    }}
  }}
  rateLimit {{ cost remaining resetAt }}
}}"""

RESPONSE_BATCH_QUERY = f"""query Rq1PrResponseBatch($ids: [ID!]!) {{
  nodes(ids: $ids) {{
    ... on PullRequest {{
      id databaseId number
      comments(first: 100) {{
        nodes {{ {COMMENT_FIELDS} }}
        pageInfo {{ hasNextPage endCursor }}
        totalCount
      }}
      reviews(first: 100) {{
        nodes {{ {REVIEW_FIELDS} }}
        pageInfo {{ hasNextPage endCursor }}
        totalCount
      }}
    }}
  }}
  rateLimit {{ cost remaining resetAt }}
}}"""

COMMIT_BATCH_QUERY = f"""query Rq1PrCommitBatch($ids: [ID!]!) {{
  nodes(ids: $ids) {{
    ... on PullRequest {{
      id databaseId number
      commits(first: 100) {{
        nodes {{ {COMMIT_FIELDS} }}
        pageInfo {{ hasNextPage endCursor }}
        totalCount
      }}
    }}
  }}
  rateLimit {{ cost remaining resetAt }}
}}"""

CONNECTION_QUERIES = {
    "comments": f"""query Rq1PrComments($id: ID!, $cursor: String) {{
      node(id: $id) {{ ... on PullRequest {{
        comments(first: 100, after: $cursor) {{
          nodes {{ {COMMENT_FIELDS} }}
          pageInfo {{ hasNextPage endCursor }} totalCount
        }}
      }} }}
      rateLimit {{ cost remaining resetAt }}
    }}""",
    "reviews": f"""query Rq1PrReviews($id: ID!, $cursor: String) {{
      node(id: $id) {{ ... on PullRequest {{
        reviews(first: 100, after: $cursor) {{
          nodes {{ {REVIEW_FIELDS} }}
          pageInfo {{ hasNextPage endCursor }} totalCount
        }}
      }} }}
      rateLimit {{ cost remaining resetAt }}
    }}""",
    "commits": f"""query Rq1PrCommits($id: ID!, $cursor: String) {{
      node(id: $id) {{ ... on PullRequest {{
        commits(first: 100, after: $cursor) {{
          nodes {{ {COMMIT_FIELDS} }}
          pageInfo {{ hasNextPage endCursor }} totalCount
        }}
      }} }}
      rateLimit {{ cost remaining resetAt }}
    }}""",
    "reviewThreads": f"""query Rq1PrThreads($id: ID!, $cursor: String) {{
      node(id: $id) {{ ... on PullRequest {{
        reviewThreads(first: 100, after: $cursor) {{
          nodes {{ {THREAD_FIELDS} }}
          pageInfo {{ hasNextPage endCursor }} totalCount
        }}
      }} }}
      rateLimit {{ cost remaining resetAt }}
    }}""",
}

THREAD_COMMENTS_QUERY = f"""query Rq1ThreadComments(
  $id: ID!, $cursor: String
) {{
  node(id: $id) {{ ... on PullRequestReviewThread {{
    comments(first: 100, after: $cursor) {{
      nodes {{ {COMMENT_FIELDS} }}
      pageInfo {{ hasNextPage endCursor }} totalCount
    }}
  }} }}
  rateLimit {{ cost remaining resetAt }}
}}"""


class GraphQLExecutor(Protocol):
    """Structural interface used by the detail collector."""

    def execute(
        self, query: str, variables: dict[str, Any]
    ) -> dict[str, Any]: ...


class RotatingGraphQLClient:
    """Round-robin requests across environment-provided GitHub tokens."""

    def __init__(self, tokens: list[str]) -> None:
        if not tokens:
            raise ValueError("at least one GitHub token is required")
        self._clients = [
            GitHubGraphQLClient(
                token,
                max_attempts=3,
                wait_on_rate_limit=False,
            )
            for token in tokens
        ]
        self._next = 0
        self._blocked_until = [0] * len(tokens)
        self._disabled: set[int] = set()
        self._lock = threading.Lock()

    def execute(
        self, query: str, variables: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute with token rotation and wait only if every token is blocked."""
        last_error: Exception | None = None
        while True:
            now = int(time.time())
            index = self._take_available_client(now)
            if index is None:
                if len(self._disabled) == len(self._clients):
                    raise RuntimeError("no usable GitHub tokens remain") from last_error
                with self._lock:
                    earliest = min(
                        self._blocked_until[candidate]
                        for candidate in range(len(self._clients))
                        if candidate not in self._disabled
                    )
                wait = max(1, earliest - now + 2)
                print(
                    f"All GitHub tokens are rate-limited; {wait}s until retry",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(min(wait, 60))
                continue
            try:
                return self._clients[index].execute(query, variables)
            except RuntimeError as error:
                last_error = error
                cause = error.__cause__
                if isinstance(cause, GitHubRateLimitError):
                    with self._lock:
                        self._blocked_until[index] = cause.reset_timestamp
                    continue
                if isinstance(cause, urllib.error.HTTPError):
                    if cause.code == 401:
                        with self._lock:
                            self._disabled.add(index)
                        continue
                    if cause.code in {403, 429}:
                        reset = cause.headers.get("X-RateLimit-Reset")
                        with self._lock:
                            self._blocked_until[index] = (
                                int(reset) if reset else now + 60
                            )
                        continue
                raise

    def _take_available_client(self, now: int) -> int | None:
        with self._lock:
            for offset in range(len(self._clients)):
                index = (self._next + offset) % len(self._clients)
                if index in self._disabled:
                    continue
                if self._blocked_until[index] > now:
                    continue
                self._next = (index + 1) % len(self._clients)
                return index
        return None


def github_tokens_from_environment() -> list[str]:
    """Read and deduplicate tokens without accepting command-line secrets."""
    values = []
    for name in ("GITHUB_TOKENS", "GITHUB_TOKEN", "GH_TOKEN"):
        raw = os.environ.get(name, "")
        values.extend(part.strip() for part in raw.split(",") if part.strip())
    return list(dict.fromkeys(values))


def collect_pr_details(
    input_path: Path,
    output_dir: Path,
    *,
    cutoff: str,
    client: GraphQLExecutor,
    batch_size: int = 10,
    concurrency: int = 1,
) -> dict[str, Any]:
    """Collect comments, reviews, commits, and review threads for every PR."""
    if batch_size < 1 or batch_size > 25:
        raise ValueError("batch_size must be between 1 and 25")
    if concurrency < 1 or concurrency > 32:
        raise ValueError("concurrency must be between 1 and 32")
    cutoff_at = _parse_time(cutoff)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "github_pr_details.jsonl"
    checkpoint_path = output_dir / "github_pr_details.checkpoint.json"
    completed = _existing_source_ids(output_path)
    pending = [
        record
        for record in _read_jsonl(input_path)
        if record["source_id"] not in completed
    ]
    total = len(completed) + len(pending)
    requests = 0
    retrieved_at = datetime.now(UTC).isoformat()

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
                    json.dumps(detail, ensure_ascii=False, sort_keys=True)
                    + "\n"
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
            if batch_number % 10 == 0 or len(completed) == total:
                print(
                    f"PR details: records={len(completed)}/{total} "
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
        "connections": ["comments", "reviews", "commits", "reviewThreads"],
    }
    _atomic_json(output_dir / "github_pr_details.manifest.json", manifest)
    return manifest


def collect_pr_responses(
    input_path: Path,
    output_dir: Path,
    *,
    cutoff: str,
    client: GraphQLExecutor,
    batch_size: int = 10,
    concurrency: int = 1,
) -> dict[str, Any]:
    """Collect the lower-cost comments and reviews response layer."""
    if batch_size < 1 or batch_size > 25:
        raise ValueError("batch_size must be between 1 and 25")
    if concurrency < 1 or concurrency > 32:
        raise ValueError("concurrency must be between 1 and 32")
    cutoff_at = _parse_time(cutoff)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "github_pr_responses.jsonl"
    checkpoint_path = output_dir / "github_pr_responses.checkpoint.json"
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
        return _fetch_response_batch(
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
        for batch_number, (responses, batch_requests, rate) in enumerate(
            executor.map(fetch, batches), start=1
        ):
            requests += batch_requests
            for response in responses:
                destination.write(
                    json.dumps(response, ensure_ascii=False, sort_keys=True)
                    + "\n"
                )
                completed.add(response["source_id"])
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
                    f"PR responses: records={len(completed)}/{total} "
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
        "connections": ["comments", "reviews"],
    }
    _atomic_json(output_dir / "github_pr_responses.manifest.json", manifest)
    return manifest


def collect_pr_commits(
    input_path: Path,
    output_dir: Path,
    *,
    cutoff: str,
    client: GraphQLExecutor,
    batch_size: int = 10,
    concurrency: int = 1,
) -> dict[str, Any]:
    """Collect PR commit timing in a low-cost single-connection pass."""
    if batch_size < 1 or batch_size > 25:
        raise ValueError("batch_size must be between 1 and 25")
    if concurrency < 1 or concurrency > 32:
        raise ValueError("concurrency must be between 1 and 32")
    cutoff_at = _parse_time(cutoff)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "github_pr_commits.jsonl"
    checkpoint_path = output_dir / "github_pr_commits.checkpoint.json"
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
        return _fetch_commit_batch(
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
        for batch_number, (commit_records, batch_requests, rate) in enumerate(
            executor.map(fetch, batches), start=1
        ):
            requests += batch_requests
            for record in commit_records:
                destination.write(
                    json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                )
                completed.add(record["source_id"])
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
                    f"PR commits: records={len(completed)}/{total} "
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
        "connections": ["commits"],
    }
    _atomic_json(output_dir / "github_pr_commits.manifest.json", manifest)
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
    data = client.execute(DETAIL_BATCH_QUERY, {"ids": ids})
    requests = 1
    nodes = data["nodes"]
    if len(nodes) != len(batch):
        raise RuntimeError("GitHub returned an unexpected node count")
    details = []
    for base, node in zip(batch, nodes, strict=True):
        if node is None:
            detail = _missing_record(base, cutoff, retrieved_at)
        else:
            detail, extra = _complete_detail(
                base,
                node,
                cutoff=cutoff,
                cutoff_at=cutoff_at,
                retrieved_at=retrieved_at,
                client=client,
            )
            requests += extra
        details.append(detail)
    return details, requests, data.get("rateLimit", {})


def _fetch_response_batch(
    batch: list[dict[str, Any]],
    *,
    cutoff: str,
    cutoff_at: datetime,
    retrieved_at: str,
    client: GraphQLExecutor,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    ids = [record["node_id"] for record in batch]
    data = client.execute(RESPONSE_BATCH_QUERY, {"ids": ids})
    requests = 1
    nodes = data["nodes"]
    if len(nodes) != len(batch):
        raise RuntimeError("GitHub returned an unexpected node count")
    responses = []
    for base, node in zip(batch, nodes, strict=True):
        if node is None:
            responses.append(_missing_record(base, cutoff, retrieved_at))
            continue
        connections = {}
        for name in ("comments", "reviews"):
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
            if name == "comments":
                frozen = _filter_by_cutoff(values, "createdAt", cutoff_at)
            else:
                frozen = _filter_reviews(values, cutoff_at)
            connections[name] = {
                "observed_total_count": connection["totalCount"],
                "retrieved_count": len(values),
                "at_cutoff_count": len(frozen),
                "nodes": frozen,
            }
        responses.append(
            {
                "schema_version": "1.0",
                "repo": base["repo"],
                "source_id": base["source_id"],
                "source_type": "pull_request_response_detail",
                "number": base["number"],
                "node_id": base["node_id"],
                "snapshot_cutoff": cutoff,
                "retrieved_at": retrieved_at,
                "api_missing": False,
                **connections,
            }
        )
    return responses, requests, data.get("rateLimit", {})


def _fetch_commit_batch(
    batch: list[dict[str, Any]],
    *,
    cutoff: str,
    cutoff_at: datetime,
    retrieved_at: str,
    client: GraphQLExecutor,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    ids = [record["node_id"] for record in batch]
    data = client.execute(COMMIT_BATCH_QUERY, {"ids": ids})
    requests = 1
    nodes = data["nodes"]
    if len(nodes) != len(batch):
        raise RuntimeError("GitHub returned an unexpected node count")
    commit_records = []
    for base, node in zip(batch, nodes, strict=True):
        if node is None:
            commit_records.append(_missing_record(base, cutoff, retrieved_at))
            continue
        connection = node["commits"]
        values = list(connection["nodes"])
        cursor = connection["pageInfo"]["endCursor"]
        has_next = connection["pageInfo"]["hasNextPage"]
        while has_next:
            page = client.execute(
                CONNECTION_QUERIES["commits"],
                {"id": node["id"], "cursor": cursor},
            )
            requests += 1
            connection_page = page["node"]["commits"]
            values.extend(connection_page["nodes"])
            cursor = connection_page["pageInfo"]["endCursor"]
            has_next = connection_page["pageInfo"]["hasNextPage"]
        frozen = _filter_commits(values, cutoff_at)
        commit_records.append(
            {
                "schema_version": "1.0",
                "repo": base["repo"],
                "source_id": base["source_id"],
                "source_type": "pull_request_commit_detail",
                "number": base["number"],
                "node_id": base["node_id"],
                "snapshot_cutoff": cutoff,
                "retrieved_at": retrieved_at,
                "api_missing": False,
                "commits": {
                    "observed_total_count": connection["totalCount"],
                    "retrieved_count": len(values),
                    "at_cutoff_count": len(frozen),
                    "nodes": frozen,
                },
            }
        )
    return commit_records, requests, data.get("rateLimit", {})


def _complete_detail(
    base: dict[str, Any],
    node: dict[str, Any],
    *,
    cutoff: str,
    cutoff_at: datetime,
    retrieved_at: str,
    client: GraphQLExecutor,
) -> tuple[dict[str, Any], int]:
    requests = 0
    connections = {}
    for name in ("comments", "reviews", "commits", "reviewThreads"):
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
        connections[name] = {
            "observed_total_count": connection["totalCount"],
            "retrieved_count": len(values),
            "nodes": values,
        }

    for thread in connections["reviewThreads"]["nodes"]:
        comment_connection = thread["comments"]
        comments = list(comment_connection["nodes"])
        cursor = comment_connection["pageInfo"]["endCursor"]
        has_next = comment_connection["pageInfo"]["hasNextPage"]
        while has_next:
            page = client.execute(
                THREAD_COMMENTS_QUERY,
                {"id": thread["id"], "cursor": cursor},
            )
            requests += 1
            connection_page = page["node"]["comments"]
            comments.extend(connection_page["nodes"])
            cursor = connection_page["pageInfo"]["endCursor"]
            has_next = connection_page["pageInfo"]["hasNextPage"]
        thread["comments"] = {
            "observed_total_count": comment_connection["totalCount"],
            "retrieved_count": len(comments),
            "nodes": _filter_by_cutoff(comments, "createdAt", cutoff_at),
        }

    connections["comments"]["nodes"] = _filter_by_cutoff(
        connections["comments"]["nodes"], "createdAt", cutoff_at
    )
    connections["reviews"]["nodes"] = _filter_reviews(
        connections["reviews"]["nodes"], cutoff_at
    )
    connections["commits"]["nodes"] = _filter_commits(
        connections["commits"]["nodes"], cutoff_at
    )
    connections["reviewThreads"]["nodes"] = [
        thread
        for thread in connections["reviewThreads"]["nodes"]
        if thread["comments"]["nodes"]
    ]
    for connection in connections.values():
        connection["at_cutoff_count"] = len(connection["nodes"])

    return (
        {
            "schema_version": "1.0",
            "repo": base["repo"],
            "source_id": base["source_id"],
            "source_type": "pull_request_detail",
            "number": base["number"],
            "node_id": base["node_id"],
            "snapshot_cutoff": cutoff,
            "retrieved_at": retrieved_at,
            "api_missing": False,
            **connections,
        },
        requests,
    )


def _missing_record(
    base: dict[str, Any], cutoff: str, retrieved_at: str
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "repo": base["repo"],
        "source_id": base["source_id"],
        "source_type": "pull_request_detail",
        "number": base["number"],
        "node_id": base["node_id"],
        "snapshot_cutoff": cutoff,
        "retrieved_at": retrieved_at,
        "api_missing": True,
    }


def _filter_by_cutoff(
    nodes: list[dict[str, Any]], field: str, cutoff_at: datetime
) -> list[dict[str, Any]]:
    return [node for node in nodes if _parse_time(node[field]) <= cutoff_at]


def _filter_reviews(
    nodes: list[dict[str, Any]], cutoff_at: datetime
) -> list[dict[str, Any]]:
    return [
        node
        for node in nodes
        if _parse_time(node.get("submittedAt") or node["createdAt"])
        <= cutoff_at
    ]


def _filter_commits(
    nodes: list[dict[str, Any]], cutoff_at: datetime
) -> list[dict[str, Any]]:
    result = []
    for node in nodes:
        commit = node["commit"]
        observed_at = commit.get("pushedDate") or commit["committedDate"]
        if _parse_time(observed_at) <= cutoff_at:
            value = dict(node)
            value["cutoff_time_source"] = (
                "pushedDate" if commit.get("pushedDate") else "committedDate_proxy"
            )
            result.append(value)
    return result


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
