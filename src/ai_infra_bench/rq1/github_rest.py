"""Efficient authenticated REST census for GitHub issues and pull requests."""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GITHUB_API_ENDPOINT = "https://api.github.com"
NEXT_LINK_PATTERN = re.compile(r'<([^>]+)>; rel="next"')


class GitHubRestClient:
    """Small authenticated REST client with retry and rate-limit handling."""

    def __init__(
        self,
        token: str,
        *,
        endpoint: str = GITHUB_API_ENDPOINT,
        max_attempts: int = 5,
    ) -> None:
        if not token:
            raise ValueError("GitHub token cannot be empty")
        self._token = token
        self.endpoint = endpoint.rstrip("/")
        self.max_attempts = max_attempts

    def issue_page(
        self, repository: str, next_url: str | None
    ) -> tuple[list[dict[str, Any]], dict[str, int], str | None]:
        """Return one creation-ordered page containing issues and PRs."""
        if next_url is None:
            path = f"/repos/{repository}/issues"
            query = urllib.parse.urlencode(
                {
                    "state": "all",
                    "sort": "created",
                    "direction": "asc",
                    "per_page": 100,
                }
            )
            request_url = f"{self.endpoint}{path}?{query}"
        else:
            if not next_url.startswith(f"{self.endpoint}/"):
                raise ValueError("GitHub next URL has an unexpected origin")
            request_url = next_url
        request = urllib.request.Request(
            request_url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "ai-infra-bench-rq1",
            },
        )
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    values = json.load(response)
                    rate = {
                        "limit": int(response.headers["X-RateLimit-Limit"]),
                        "remaining": int(
                            response.headers["X-RateLimit-Remaining"]
                        ),
                        "reset": int(response.headers["X-RateLimit-Reset"]),
                    }
                    next_link = _next_link(response.headers.get("Link"))
                if not isinstance(values, list):
                    raise ValueError("GitHub issues endpoint did not return a list")
                return values, rate, next_link
            except (OSError, ValueError) as error:
                last_error = error
                if isinstance(error, urllib.error.HTTPError):
                    reset = error.headers.get("X-RateLimit-Reset")
                    if error.code in {403, 429} and reset:
                        _wait_until_reset(int(reset))
                        continue
                    if error.code not in {500, 502, 503, 504}:
                        break
                if attempt < self.max_attempts:
                    time.sleep(min(30.0, 2 ** (attempt - 1)) + random.random())
        assert last_error is not None
        raise RuntimeError(
            f"GitHub REST request failed after {self.max_attempts} attempts"
        ) from last_error


def collect_rest_base_snapshot(
    output_dir: Path,
    *,
    repository: str,
    cutoff: str,
    client: GitHubRestClient,
) -> dict[str, Any]:
    """Collect the complete issue/PR census with a resumable page checkpoint."""
    if len(repository.split("/")) != 2:
        raise ValueError("repository must have owner/name form")
    cutoff_value = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    if cutoff_value.tzinfo is None:
        raise ValueError("cutoff must include a timezone")
    cutoff_value = cutoff_value.astimezone(UTC)

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "issue": output_dir / "github_issues.jsonl",
        "pull_request": output_dir / "github_pull_requests.jsonl",
    }
    checkpoint_path = output_dir / "github_rest.checkpoint.json"
    checkpoint = _read_json(checkpoint_path) if checkpoint_path.exists() else {}
    if checkpoint.get("complete"):
        return _manifest(output_dir, repository, cutoff, paths, resumed=True)

    existing = {kind: _existing_ids(path) for kind, path in paths.items()}
    next_url = checkpoint.get("next_url")
    requests = int(checkpoint.get("requests", checkpoint.get("last_page", 0)))
    streams = {
        kind: path.open("a", encoding="utf-8") for kind, path in paths.items()
    }
    try:
        while True:
            values, rate, following_url = client.issue_page(
                repository, next_url
            )
            crossed_cutoff = False
            for value in values:
                created_at = datetime.fromisoformat(
                    value["created_at"].replace("Z", "+00:00")
                ).astimezone(UTC)
                if created_at > cutoff_value:
                    crossed_cutoff = True
                    continue
                kind = "pull_request" if "pull_request" in value else "issue"
                if int(value["id"]) in existing[kind]:
                    continue
                record = dict(value)
                record.update(
                    {
                        "schema_version": "1.0",
                        "repo": repository,
                        "source_id": (
                            f"vllm__{'pr' if kind == 'pull_request' else 'issue'}"
                            f"__{value['number']}"
                        ),
                        "source_type": kind,
                        "snapshot_cutoff": cutoff,
                    }
                )
                streams[kind].write(
                    json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                )
                existing[kind].add(int(value["id"]))
            for stream in streams.values():
                stream.flush()

            complete = not values or crossed_cutoff or following_url is None
            requests += 1
            _atomic_json(
                checkpoint_path,
                {
                    "complete": complete,
                    "next_url": following_url,
                    "requests": requests,
                    "records": {
                        kind: len(ids) for kind, ids in existing.items()
                    },
                    "rate_limit": rate,
                },
            )
            if requests % 25 == 0 or complete:
                print(
                    f"REST requests={requests} issues={len(existing['issue'])} "
                    f"prs={len(existing['pull_request'])} "
                    f"remaining={rate['remaining']}",
                    file=sys.stderr,
                    flush=True,
                )
            if complete:
                break
            if rate["remaining"] <= 10:
                _wait_until_reset(rate["reset"])
            next_url = following_url
    finally:
        for stream in streams.values():
            stream.close()

    manifest = _manifest(
        output_dir, repository, cutoff, paths, resumed=bool(checkpoint)
    )
    _atomic_json(output_dir / "rest_base_snapshot.manifest.json", manifest)
    return manifest


def _manifest(
    output_dir: Path,
    repository: str,
    cutoff: str,
    paths: dict[str, Path],
    *,
    resumed: bool,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source": "GitHub REST API",
        "repository": repository,
        "cutoff": cutoff,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "resumed": resumed,
        "objects": {
            kind: {"records": len(_existing_ids(path)), "path": str(path)}
            for kind, path in paths.items()
        },
    }


def _existing_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as stream:
        return {
            int(json.loads(line)["id"]) for line in stream if line.strip()
        }


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


def _next_link(header: str | None) -> str | None:
    if not header:
        return None
    match = NEXT_LINK_PATTERN.search(header)
    return match.group(1) if match else None
