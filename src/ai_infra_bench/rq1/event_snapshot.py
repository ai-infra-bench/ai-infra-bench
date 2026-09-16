"""Download a frozen public-event supplement from ClickHouse playground."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PLAYGROUND_ENDPOINT = "https://play.clickhouse.com/"
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
EVENT_TYPES = (
    "IssuesEvent",
    "IssueCommentEvent",
    "PullRequestEvent",
    "PullRequestReviewEvent",
    "PullRequestReviewCommentEvent",
)
EVENT_FIELDS = (
    "event_type",
    "actor_login",
    "repo_name",
    "created_at",
    "updated_at",
    "action",
    "comment_id",
    "body",
    "path",
    "position",
    "line",
    "number",
    "title",
    "labels",
    "state",
    "locked",
    "assignee",
    "assignees",
    "comments",
    "author_association",
    "closed_at",
    "merged_at",
    "merge_commit_sha",
    "requested_reviewers",
    "requested_teams",
    "head_ref",
    "head_sha",
    "base_ref",
    "base_sha",
    "merged",
    "merged_by",
    "review_comments",
    "commits",
    "additions",
    "deletions",
    "changed_files",
    "commit_id",
    "original_commit_id",
    "review_state",
)


def snapshot_query(repository: str, cutoff: str) -> str:
    """Build the stable query used for the event supplement."""
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise ValueError(f"invalid GitHub repository: {repository!r}")
    cutoff_value = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    if cutoff_value.tzinfo is None:
        raise ValueError("cutoff must include a timezone")
    cutoff_utc = cutoff_value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
    fields = ",\n    ".join(EVENT_FIELDS)
    event_types = ", ".join(f"'{value}'" for value in EVENT_TYPES)
    return f"""SELECT DISTINCT
    {fields}
FROM github_events
WHERE repo_name = '{repository}'
  AND created_at >= toDateTime('2023-02-09 00:00:00', 'UTC')
  AND created_at <= toDateTime('{cutoff_utc}', 'UTC')
  AND event_type IN ({event_types})
ORDER BY created_at, event_type, number, actor_login, comment_id, review_state
FORMAT JSONEachRow
"""


def download_snapshot(
    output: Path,
    *,
    repository: str,
    cutoff: str,
    endpoint: str = PLAYGROUND_ENDPOINT,
) -> dict[str, Any]:
    """Stream a compressed event snapshot and write a provenance manifest."""
    query = snapshot_query(repository, cutoff)
    url = endpoint + "?" + urllib.parse.urlencode({"user": "play"})
    request = urllib.request.Request(
        url,
        data=query.encode(),
        headers={"Content-Type": "text/plain; charset=utf-8"},
        method="POST",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    bytes_received = 0
    line_count = 0
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=output.parent, delete=False
        ) as temporary:
            temporary_name = temporary.name
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=temporary,
                mtime=0,
            ) as compressed:
                with urllib.request.urlopen(request, timeout=900) as response:
                    while chunk := response.read(1024 * 1024):
                        digest.update(chunk)
                        compressed.write(chunk)
                        bytes_received += len(chunk)
                        line_count += chunk.count(b"\n")
                        if bytes_received // (16 * 1024 * 1024) != (
                            bytes_received - len(chunk)
                        ) // (16 * 1024 * 1024):
                            print(
                                f"downloaded {bytes_received // (1024 * 1024)} MiB",
                                file=sys.stderr,
                                flush=True,
                            )
        os.replace(temporary_name, output)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)

    manifest = {
        "schema_version": "1.0",
        "source": "ClickHouse playground github_events",
        "source_url": endpoint,
        "repository": repository,
        "cutoff": cutoff,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "event_types": list(EVENT_TYPES),
        "fields": list(EVENT_FIELDS),
        "records": line_count,
        "uncompressed_bytes": bytes_received,
        "uncompressed_sha256": digest.hexdigest(),
        "completeness": "supplement_only",
        "limitations": [
            "The public event table is not a complete census of repository events.",
            "Exact duplicate rows are removed because the source contains duplicates.",
            "Events before the table's first observation require another source.",
        ],
        "query": query,
    }
    manifest_path = output.with_suffix(output.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def read_events(path: Path):
    """Yield decoded rows from a compressed JSONL event snapshot."""
    with gzip.open(path, mode="rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            yield value
