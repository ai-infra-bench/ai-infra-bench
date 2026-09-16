"""Build a merged-PR bootstrap manifest from a local Git repository."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

PR_SUFFIX = re.compile(r"\s*\(#(?P<number>[1-9][0-9]*)\)\s*$")
RECORD_SEPARATOR = "\x1e"
FIELD_SEPARATOR = "\x1f"


def extract_pr_number(subject: str) -> int | None:
    """Extract the trailing squash-merge PR number from a commit subject."""
    match = PR_SUFFIX.search(subject)
    return int(match.group("number")) if match else None


def strip_pr_suffix(subject: str) -> str:
    """Remove a trailing squash-merge PR number from a commit subject."""
    return PR_SUFFIX.sub("", subject).strip()


def iter_merged_prs(
    repository: Path,
    *,
    cutoff: str,
    source_repo: str = "vllm-project/vllm",
) -> Iterator[dict[str, Any]]:
    """Yield merged PR records reachable from the default branch first parent.

    This is a bootstrap source for semantic labeling, not the complete PR
    population. Closed-unmerged and open PRs require the GitHub snapshot.
    """
    command = [
        "git",
        "-C",
        str(repository),
        "log",
        "--first-parent",
        f"--until={cutoff}",
        f"--format={RECORD_SEPARATOR}%H{FIELD_SEPARATOR}%cI{FIELD_SEPARATOR}%s",
        "--numstat",
        "--no-renames",
    ]
    output = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    seen: set[int] = set()
    for chunk in output.split(RECORD_SEPARATOR):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        header, *numstat_lines = chunk.splitlines()
        fields = header.split(FIELD_SEPARATOR, 2)
        if len(fields) != 3:
            raise ValueError(f"cannot parse git log header: {header!r}")
        commit_sha, merged_at, subject = fields
        number = extract_pr_number(subject)
        if number is None or number in seen:
            continue
        seen.add(number)

        files = []
        total_additions = 0
        total_deletions = 0
        binary_files = 0
        for line in numstat_lines:
            if not line.strip():
                continue
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            additions_text, deletions_text, path = parts
            if additions_text == "-" or deletions_text == "-":
                additions = deletions = None
                binary_files += 1
            else:
                additions = int(additions_text)
                deletions = int(deletions_text)
                total_additions += additions
                total_deletions += deletions
            files.append(
                {
                    "path": path,
                    "additions": additions,
                    "deletions": deletions,
                }
            )

        record = {
            "schema_version": "1.0",
            "source_id": f"vllm__pr__{number}",
            "repo": source_repo,
            "source_type": "pull_request",
            "number": number,
            "url": f"https://github.com/{source_repo}/pull/{number}",
            "title": strip_pr_suffix(subject),
            "merged_at": merged_at,
            "merge_commit_sha": commit_sha,
            "changed_files": len(files),
            "additions": total_additions,
            "deletions": total_deletions,
            "binary_files": binary_files,
            "files": files,
            "source": "default_branch_git_history",
        }
        record["input_sha256"] = input_hash(record)
        yield record


def input_hash(record: dict[str, Any]) -> str:
    """Hash fields that affect semantic classification."""
    material = {
        "source_id": record["source_id"],
        "title": record["title"],
        "body": record.get("body", ""),
        "github_labels": record.get("github_labels", []),
        "files": record["files"],
    }
    encoded = json.dumps(
        material, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def write_manifest(records: Iterator[dict[str, Any]], output: Path) -> int:
    """Write records to JSONL in PR-number order."""
    values = sorted(records, key=lambda item: item["number"])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True))
            stream.write("\n")
    return len(values)
