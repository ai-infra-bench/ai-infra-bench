"""Authenticated GitHub GraphQL census snapshot for RQ1."""

from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GITHUB_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"


class GitHubRateLimitError(RuntimeError):
    """GraphQL rate-limit response with the HTTP reset timestamp."""

    def __init__(self, reset_timestamp: int) -> None:
        super().__init__("GitHub GraphQL rate limit exceeded")
        self.reset_timestamp = reset_timestamp

ISSUE_QUERY = """query Rq1Issues(
  $owner: String!, $name: String!, $cursor: String
) {
  repository(owner: $owner, name: $name) {
    issues(
      first: 100, after: $cursor,
      states: [OPEN, CLOSED],
      orderBy: {field: CREATED_AT, direction: ASC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id databaseId number url title body
        createdAt updatedAt closedAt state stateReason locked
        author { login __typename }
        authorAssociation
        labels(first: 100) {
          nodes { name color }
          pageInfo { hasNextPage }
        }
        comments { totalCount }
        timelineItems(
          first: 1, itemTypes: [CLOSED_EVENT, REOPENED_EVENT]
        ) { totalCount }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""

PULL_REQUEST_QUERY = """query Rq1PullRequests(
  $owner: String!, $name: String!, $cursor: String
) {
  repository(owner: $owner, name: $name) {
    pullRequests(
      first: 100, after: $cursor,
      states: [OPEN, CLOSED, MERGED],
      orderBy: {field: CREATED_AT, direction: ASC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id databaseId number url title body
        createdAt updatedAt closedAt mergedAt state isDraft locked
        author { login __typename }
        authorAssociation
        additions deletions changedFiles
        baseRefName baseRefOid headRefName headRefOid
        maintainerCanModify reviewDecision
        mergeCommit { oid }
        mergedBy { login __typename }
        labels(first: 100) {
          nodes { name color }
          pageInfo { hasNextPage }
        }
        comments { totalCount }
        commits { totalCount }
        files { totalCount }
        reviews { totalCount }
        reviewThreads { totalCount }
        timelineItems(
          first: 1,
          itemTypes: [
            CLOSED_EVENT, REOPENED_EVENT, READY_FOR_REVIEW_EVENT,
            CONVERT_TO_DRAFT_EVENT, REVIEW_REQUESTED_EVENT,
            REVIEW_DISMISSED_EVENT, HEAD_REF_FORCE_PUSHED_EVENT
          ]
        ) { totalCount }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""


class GitHubGraphQLClient:
    """Small retrying GraphQL client that never serializes its token."""

    def __init__(
        self,
        token: str,
        *,
        endpoint: str = GITHUB_GRAPHQL_ENDPOINT,
        max_attempts: int = 5,
        wait_on_rate_limit: bool = True,
    ) -> None:
        if not token:
            raise ValueError("GitHub token cannot be empty")
        self._token = token
        self.endpoint = endpoint
        self.max_attempts = max_attempts
        self.wait_on_rate_limit = wait_on_rate_limit

    def execute(
        self, query: str, variables: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute one query with bounded retries and rate-limit handling."""
        payload = json.dumps(
            {"query": query, "variables": variables}, separators=(",", ":")
        ).encode()
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            request = urllib.request.Request(
                self.endpoint,
                data=payload,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                    "User-Agent": "ai-infra-bench-rq1",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    result = json.load(response)
                    reset_timestamp = int(
                        response.headers.get("X-RateLimit-Reset", time.time() + 60)
                    )
                if result.get("errors"):
                    if any(
                        error.get("type") == "RATE_LIMIT"
                        for error in result["errors"]
                    ):
                        raise GitHubRateLimitError(reset_timestamp)
                    raise RuntimeError(
                        "GitHub GraphQL error: "
                        + json.dumps(result["errors"], ensure_ascii=False)
                    )
                return result["data"]
            except (OSError, ValueError, RuntimeError) as error:
                last_error = error
                if isinstance(error, GitHubRateLimitError):
                    if self.wait_on_rate_limit:
                        _wait_until_reset(error.reset_timestamp)
                        continue
                    break
                if isinstance(error, urllib.error.HTTPError):
                    reset = error.headers.get("X-RateLimit-Reset")
                    if error.code in {403, 429} and reset:
                        if self.wait_on_rate_limit:
                            _wait_until_reset(int(reset))
                            continue
                        break
                    if error.code not in {500, 502, 503, 504}:
                        break
                if attempt < self.max_attempts:
                    time.sleep(min(30.0, 2 ** (attempt - 1)) + random.random())
        assert last_error is not None
        raise RuntimeError(
            f"GitHub GraphQL request failed after {self.max_attempts} attempts"
        ) from last_error


def github_token_from_environment() -> str:
    """Read the GitHub token without accepting it as a CLI argument."""
    return os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get(
        "GH_TOKEN", ""
    ).strip()


def collect_base_snapshot(
    output_dir: Path,
    *,
    repository: str,
    cutoff: str,
    client: GitHubGraphQLClient,
) -> dict[str, Any]:
    """Collect complete issue and PR base objects with resumable cursors."""
    owner, name = _split_repository(repository)
    cutoff_value = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    if cutoff_value.tzinfo is None:
        raise ValueError("cutoff must include a timezone")
    cutoff_value = cutoff_value.astimezone(UTC)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for object_type, query, connection_name in (
        ("issue", ISSUE_QUERY, "issues"),
        ("pull_request", PULL_REQUEST_QUERY, "pullRequests"),
    ):
        results[object_type] = _collect_connection(
            output_dir,
            owner=owner,
            name=name,
            repository=repository,
            object_type=object_type,
            query=query,
            connection_name=connection_name,
            cutoff=cutoff,
            cutoff_value=cutoff_value,
            client=client,
        )
    manifest = {
        "schema_version": "1.0",
        "source": "GitHub GraphQL API",
        "repository": repository,
        "cutoff": cutoff,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "objects": results,
    }
    _atomic_json(output_dir / "base_snapshot.manifest.json", manifest)
    return manifest


def _collect_connection(
    output_dir: Path,
    *,
    owner: str,
    name: str,
    repository: str,
    object_type: str,
    query: str,
    connection_name: str,
    cutoff: str,
    cutoff_value: datetime,
    client: GitHubGraphQLClient,
) -> dict[str, Any]:
    output_path = output_dir / f"github_{object_type}s.jsonl"
    checkpoint_path = output_dir / f"github_{object_type}s.checkpoint.json"
    checkpoint = _read_json(checkpoint_path) if checkpoint_path.exists() else {}
    cursor = checkpoint.get("cursor")
    complete = bool(checkpoint.get("complete", False))
    existing_ids = _existing_ids(output_path)
    pages = int(checkpoint.get("pages", 0))
    written = len(existing_ids)
    if complete:
        return {
            "records": written,
            "pages": pages,
            "path": str(output_path),
            "resumed": True,
        }

    with output_path.open("a", encoding="utf-8") as stream:
        while True:
            data = client.execute(
                query,
                {"owner": owner, "name": name, "cursor": cursor},
            )
            connection = data["repository"][connection_name]
            nodes = connection["nodes"]
            before_cutoff = []
            crossed_cutoff = False
            for node in nodes:
                created_at = datetime.fromisoformat(
                    node["createdAt"].replace("Z", "+00:00")
                ).astimezone(UTC)
                if created_at > cutoff_value:
                    crossed_cutoff = True
                    continue
                record = dict(node)
                record.update(
                    {
                        "schema_version": "1.0",
                        "repo": repository,
                        "source_id": (
                            f"vllm__{'issue' if object_type == 'issue' else 'pr'}"
                            f"__{node['number']}"
                        ),
                        "source_type": object_type,
                        "snapshot_cutoff": cutoff,
                    }
                )
                before_cutoff.append(record)

            for record in before_cutoff:
                if record["id"] in existing_ids:
                    continue
                stream.write(
                    json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                )
                existing_ids.add(record["id"])
                written += 1
            stream.flush()

            pages += 1
            page_info = connection["pageInfo"]
            cursor = page_info["endCursor"]
            has_next = bool(page_info["hasNextPage"])
            complete = crossed_cutoff or not has_next
            rate = data["rateLimit"]
            _atomic_json(
                checkpoint_path,
                {
                    "cursor": cursor,
                    "complete": complete,
                    "pages": pages,
                    "records": written,
                    "rate_limit": rate,
                },
            )
            if pages % 25 == 0 or complete:
                print(
                    f"{object_type}: pages={pages} records={written} "
                    f"remaining={rate['remaining']}",
                    file=sys.stderr,
                    flush=True,
                )
            if complete:
                break
            if rate["remaining"] <= max(10, rate["cost"] * 2):
                reset = datetime.fromisoformat(
                    rate["resetAt"].replace("Z", "+00:00")
                ).timestamp()
                _wait_until_reset(int(reset))
    return {
        "records": written,
        "pages": pages,
        "path": str(output_path),
        "resumed": bool(checkpoint),
    }


def _split_repository(repository: str) -> tuple[str, str]:
    parts = repository.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("repository must have owner/name form")
    return parts[0], parts[1]


def _existing_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    result = set()
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                result.add(json.loads(line)["id"])
    return result


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _wait_until_reset(reset_timestamp: int) -> None:
    while True:
        remaining = reset_timestamp - int(time.time()) + 2
        if remaining <= 0:
            return
        print(
            f"GitHub rate limit reached; {remaining}s until reset",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(min(remaining, 60))
