import json
from pathlib import Path

from ai_infra_bench.rq1.pr_manifest import merge_pr_manifests


def write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_text("".join(json.dumps(value) + "\n" for value in values))


def test_merge_uses_github_text_and_git_file_evidence(tmp_path: Path) -> None:
    github = tmp_path / "github.jsonl"
    git = tmp_path / "git.jsonl"
    output = tmp_path / "output.jsonl"
    write_jsonl(
        github,
        [
            {
                "number": 10,
                "repo": "vllm-project/vllm",
                "url": "https://github.com/vllm-project/vllm/pull/10",
                "title": "ROCm fix",
                "body": "Fix the AMD backend.",
                "labels": {"nodes": [{"name": "rocm"}]},
                "createdAt": "2026-01-01T00:00:00Z",
                "updatedAt": "2026-08-09T00:00:00Z",
                "mergedAt": "2026-08-01T00:00:00Z",
                "state": "MERGED",
                "changedFiles": 1,
                "additions": 2,
                "deletions": 1,
            }
        ],
    )
    write_jsonl(
        git,
        [
            {
                "number": 10,
                "merge_commit_sha": "a" * 40,
                "files": [
                    {"path": "vllm/platforms/rocm.py", "additions": 2}
                ],
            }
        ],
    )

    counts = merge_pr_manifests(
        github,
        git,
        output,
        cutoff="2026-08-08T23:59:59Z",
    )
    result = json.loads(output.read_text())

    assert counts["pull_requests"] == 1
    assert result["github_labels"] == ["rocm"]
    assert result["files"][0]["path"] == "vllm/platforms/rocm.py"
    assert result["updated_after_cutoff"] is True
    assert result["merged_at_by_cutoff"] == "2026-08-01T00:00:00Z"
    assert len(result["input_sha256"]) == 64


def test_merge_accepts_rest_issue_shaped_prs_without_git_files(
    tmp_path: Path,
) -> None:
    github = tmp_path / "github.jsonl"
    git = tmp_path / "git.jsonl"
    output = tmp_path / "output.jsonl"
    write_jsonl(
        github,
        [
            {
                "number": 11,
                "repo": "vllm-project/vllm",
                "url": "https://api.github.com/repos/vllm-project/vllm/issues/11",
                "html_url": "https://github.com/vllm-project/vllm/pull/11",
                "title": "Feature",
                "body": "Generic feature",
                "labels": [{"name": "frontend"}],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-02T00:00:00Z",
                "pull_request": {"merged_at": None},
                "state": "open",
            }
        ],
    )
    write_jsonl(git, [])

    merge_pr_manifests(
        github,
        git,
        output,
        cutoff="2026-08-08T23:59:59Z",
    )
    result = json.loads(output.read_text())

    assert result["github_labels"] == ["frontend"]
    assert result["changed_files"] is None
    assert result["file_paths_source"] == "unavailable_in_base_snapshot"
    assert result["sources"] == ["github_rest_base"]
