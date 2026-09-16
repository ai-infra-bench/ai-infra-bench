"""Join GitHub PR metadata with final default-branch Git evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ai_infra_bench.rq1.git_manifest import input_hash


def merge_pr_manifests(
    github_path: Path,
    git_path: Path,
    output_path: Path,
    *,
    cutoff: str,
) -> dict[str, int]:
    """Create the complete model-input PR manifest."""
    cutoff_value = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    if cutoff_value.tzinfo is None:
        raise ValueError("cutoff must include a timezone")
    cutoff_value = cutoff_value.astimezone(UTC)
    git_records = {
        int(record["number"]): record for record in _read_jsonl(git_path)
    }
    counts = {
        "pull_requests": 0,
        "with_git_files": 0,
        "without_git_files": 0,
        "updated_after_cutoff": 0,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as stream:
        for github in _read_jsonl(github_path):
            number = int(github["number"])
            git_record = git_records.get(number)
            labels_value = github["labels"]
            if isinstance(labels_value, dict):
                labels = sorted(
                    node["name"] for node in labels_value["nodes"]
                )
                github_source = "github_graphql_base"
            else:
                labels = sorted(label["name"] for label in labels_value)
                github_source = "github_rest_base"
            merged_at_observed = github.get("mergedAt") or github.get(
                "pull_request", {}
            ).get("merged_at")
            merged_at = _at_or_before(merged_at_observed, cutoff_value)
            updated_at = github.get("updatedAt") or github["updated_at"]
            updated_after_cutoff = not _at_or_before(
                updated_at, cutoff_value
            )
            if updated_after_cutoff:
                counts["updated_after_cutoff"] += 1

            files = git_record["files"] if git_record is not None else []
            if files:
                counts["with_git_files"] += 1
            else:
                counts["without_git_files"] += 1
            changed_files = github.get("changedFiles")
            additions = github.get("additions")
            deletions = github.get("deletions")
            if git_record is not None:
                changed_files = git_record.get("changed_files", len(files))
                additions = git_record.get("additions", additions)
                deletions = git_record.get("deletions", deletions)
            record = {
                "schema_version": "1.0",
                "source_id": f"vllm__pr__{number}",
                "repo": github["repo"],
                "source_type": "pull_request",
                "number": number,
                "url": github.get("html_url") or github["url"],
                "title": github["title"],
                "body": github.get("body") or "",
                "github_labels": labels,
                "created_at": github.get("createdAt") or github["created_at"],
                "updated_at": updated_at,
                "updated_after_cutoff": updated_after_cutoff,
                "state_observed_at_retrieval": github["state"],
                "merged_at_by_cutoff": merged_at,
                "merge_commit_sha": (
                    git_record["merge_commit_sha"]
                    if git_record is not None
                    else None
                ),
                "changed_files": (
                    int(changed_files) if changed_files is not None else None
                ),
                "additions": int(additions) if additions is not None else None,
                "deletions": int(deletions) if deletions is not None else None,
                "files": files,
                "file_paths_source": (
                    "default_branch_git_history"
                    if files
                    else "unavailable_in_base_snapshot"
                ),
                "snapshot_cutoff": cutoff,
                "sources": [
                    github_source,
                    *(
                        ["default_branch_git_history"]
                        if git_record is not None
                        else []
                    ),
                ],
            }
            record["input_sha256"] = input_hash(record)
            stream.write(
                json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            )
            counts["pull_requests"] += 1
    return counts


def _at_or_before(value: str | None, cutoff: datetime) -> str | None:
    if not value:
        return None
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        UTC
    )
    return value if timestamp <= cutoff else None


def _read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            yield value
