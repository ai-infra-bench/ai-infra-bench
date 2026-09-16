"""Repository-wide snapshot of line-level pull-request review comments."""

from __future__ import annotations

import http.client
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from ai_infra_bench.rq1.github_rest import _next_link, _wait_until_reset
from ai_infra_bench.rq1.github_snapshot import _atomic_json

GITHUB_API_ENDPOINT = "https://api.github.com"
LAST_LINK_PATTERN = re.compile(r'<([^>]+)>; rel="last"')


class ReviewCommentPageClient(Protocol):
    """Structural interface for repository review-comment pages."""

    def review_comment_page(
        self, repository: str, next_url: str | None
    ) -> tuple[list[dict[str, Any]], dict[str, int], str | None]: ...


class GitHubReviewCommentClient:
    """Retrying client for the repository-wide review-comments endpoint."""

    def __init__(self, token: str, *, max_attempts: int = 5) -> None:
        if not token:
            raise ValueError("GitHub token cannot be empty")
        self._token = token
        self.max_attempts = max_attempts

    def review_comment_page(
        self, repository: str, next_url: str | None
    ) -> tuple[list[dict[str, Any]], dict[str, int], str | None]:
        """Return one chronological page of line-level review comments."""
        if next_url is None:
            query = urllib.parse.urlencode(
                {
                    "sort": "created",
                    "direction": "asc",
                    "per_page": 100,
                }
            )
            request_url = (
                f"{GITHUB_API_ENDPOINT}/repos/{repository}/pulls/comments?{query}"
            )
        else:
            if not next_url.startswith(f"{GITHUB_API_ENDPOINT}/"):
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
                    following = _next_link(response.headers.get("Link"))
                    last_page = _last_page(response.headers.get("Link"))
                    if last_page is not None:
                        rate["last_page"] = last_page
                if not isinstance(values, list):
                    raise ValueError("review-comments endpoint returned non-list")
                return values, rate, following
            except (OSError, ValueError, http.client.HTTPException) as error:
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
        raise RuntimeError("GitHub review-comment request failed") from last_error


def collect_review_comments(
    output_dir: Path,
    *,
    repository: str,
    cutoff: str,
    client: ReviewCommentPageClient,
    concurrency: int = 16,
) -> dict[str, Any]:
    """Collect all repository line-level review comments with checkpoints."""
    if len(repository.split("/")) != 2:
        raise ValueError("repository must have owner/name form")
    if concurrency < 1 or concurrency > 32:
        raise ValueError("concurrency must be between 1 and 32")
    cutoff_at = _parse_time(cutoff)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "github_review_comments.jsonl"
    checkpoint_path = output_dir / "github_review_comments.checkpoint.json"
    checkpoint = (
        json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else {}
    )
    if checkpoint.get("complete"):
        return _manifest(
            repository,
            cutoff,
            output_path,
            requests=int(checkpoint.get("requests", 0)),
            after_cutoff=int(checkpoint.get("after_cutoff", 0)),
        )
    existing = _existing_ids(output_path)
    next_url = checkpoint.get("next_url")
    next_page = int(checkpoint.get("next_page") or _page_number(next_url) or 1)
    requests = int(checkpoint.get("requests", 0))
    after_cutoff = int(checkpoint.get("after_cutoff", 0))

    values, rate, following = client.review_comment_page(repository, next_url)
    requests += 1
    last_page = int(rate.get("last_page") or next_page)
    if following is not None and "last_page" not in rate:
        raise RuntimeError("GitHub pagination did not provide a last page")
    pages = [
        (
            page,
            _review_comment_page_url(repository, page),
        )
        for page in range(next_page + 1, last_page + 1)
    ]

    def fetch(item: tuple[int, str]):
        page, url = item
        page_values, page_rate, _ = client.review_comment_page(repository, url)
        return page, page_values, page_rate

    with (
        ThreadPoolExecutor(max_workers=concurrency) as executor,
        output_path.open("a", encoding="utf-8") as destination,
    ):
        after_cutoff += _write_page(
            values,
            destination,
            existing,
            repository=repository,
            cutoff=cutoff,
            cutoff_at=cutoff_at,
        )
        destination.flush()
        _review_comment_checkpoint(
            checkpoint_path,
            complete=next_page == last_page,
            next_page=next_page + 1,
            last_page=last_page,
            requests=requests,
            records=len(existing),
            after_cutoff=after_cutoff,
            rate=rate,
            repository=repository,
        )
        for page, page_values, page_rate in executor.map(fetch, pages):
            requests += 1
            after_cutoff += _write_page(
                page_values,
                destination,
                existing,
                repository=repository,
                cutoff=cutoff,
                cutoff_at=cutoff_at,
            )
            destination.flush()
            complete = page == last_page
            _review_comment_checkpoint(
                checkpoint_path,
                complete=complete,
                next_page=page + 1,
                last_page=last_page,
                requests=requests,
                records=len(existing),
                after_cutoff=after_cutoff,
                rate=page_rate,
                repository=repository,
            )
            if requests % 25 == 0 or complete:
                print(
                    f"Review comments: pages={requests}/{last_page} "
                    f"records={len(existing)} "
                    f"remaining={page_rate['remaining']}",
                    file=sys.stderr,
                    flush=True,
                )
    manifest = _manifest(
        repository,
        cutoff,
        output_path,
        requests=requests,
        after_cutoff=after_cutoff,
    )
    _atomic_json(output_dir / "github_review_comments.manifest.json", manifest)
    return manifest


def _write_page(
    values: list[dict[str, Any]],
    destination: Any,
    existing: set[int],
    *,
    repository: str,
    cutoff: str,
    cutoff_at: datetime,
) -> int:
    after_cutoff = 0
    for value in values:
        if int(value["id"]) in existing:
            continue
        if _parse_time(value["created_at"]) > cutoff_at:
            after_cutoff += 1
            continue
        number = int(value["pull_request_url"].rstrip("/").split("/")[-1])
        record = dict(value)
        record.update(
            {
                "schema_version": "1.0",
                "repo": repository,
                "source_id": f"vllm__pr__{number}",
                "source_type": "pull_request_review_comment",
                "snapshot_cutoff": cutoff,
            }
        )
        destination.write(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        )
        existing.add(int(value["id"]))
    return after_cutoff


def _review_comment_checkpoint(
    path: Path,
    *,
    complete: bool,
    next_page: int,
    last_page: int,
    requests: int,
    records: int,
    after_cutoff: int,
    rate: dict[str, int],
    repository: str,
) -> None:
    _atomic_json(
        path,
        {
            "complete": complete,
            "next_page": next_page,
            "last_page": last_page,
            "next_url": (
                None
                if complete
                else _review_comment_page_url(repository, next_page)
            ),
            "requests": requests,
            "records": records,
            "after_cutoff": after_cutoff,
            "rate_limit": rate,
        },
    )


def _review_comment_page_url(repository: str, page: int) -> str:
    query = urllib.parse.urlencode(
        {
            "sort": "created",
            "direction": "asc",
            "per_page": 100,
            "page": page,
        }
    )
    return f"{GITHUB_API_ENDPOINT}/repos/{repository}/pulls/comments?{query}"


def _last_page(header: str | None) -> int | None:
    if not header:
        return None
    match = LAST_LINK_PATTERN.search(header)
    return _page_number(match.group(1)) if match else None


def _page_number(url: str | None) -> int | None:
    if not url:
        return None
    values = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    page = values.get("page")
    return int(page[0]) if page else None


def _manifest(
    repository: str,
    cutoff: str,
    output_path: Path,
    *,
    requests: int,
    after_cutoff: int,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source": "GitHub REST API",
        "repository": repository,
        "cutoff": cutoff,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "output": str(output_path),
        "records": len(_existing_ids(output_path)),
        "requests": requests,
        "after_cutoff_excluded": after_cutoff,
        "complete": True,
    }


def _existing_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as source:
        return {int(json.loads(line)["id"]) for line in source if line.strip()}


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(UTC)
