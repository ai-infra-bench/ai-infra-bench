import json
from pathlib import Path

import pytest

from ai_infra_bench.rq1.label_findings import summarize_labels


def _write_jsonl(path: Path, values: list[dict]) -> None:
    path.write_text("".join(json.dumps(value) + "\n" for value in values))


def _classification(
    source_id: str,
    *,
    subsystems: list[str],
    scope: str,
    accelerators: list[str],
) -> dict:
    return {
        "source_id": source_id,
        "subsystems": subsystems,
        "accelerator_scope": scope,
        "accelerators": accelerators,
        "subsystem_confidence": "high",
        "accelerator_confidence": "high",
        "rationale": "Test rationale",
        "evidence": [],
    }


def test_summarize_labels_separates_bots_and_multilabels(
    tmp_path: Path,
) -> None:
    labels_path = tmp_path / "labels.jsonl"
    manifest_path = tmp_path / "manifest.jsonl"
    github_path = tmp_path / "github.jsonl"
    source_ids = ["vllm__pr__1", "vllm__pr__2", "vllm__pr__3"]
    _write_jsonl(
        labels_path,
        [
            {
                "source_id": source_ids[0],
                "classification": _classification(
                    source_ids[0],
                    subsystems=["hardware_backends", "kernels_operators"],
                    scope="specific",
                    accelerators=["amd_rocm"],
                ),
                "taxonomy_version": "taxonomy-v1",
                "prompt_version": "prompt-v1",
                "model": {"resolved": "model-v1"},
            },
            {
                "source_id": source_ids[1],
                "classification": _classification(
                    source_ids[1],
                    subsystems=["models"],
                    scope="agnostic",
                    accelerators=[],
                ),
                "taxonomy_version": "taxonomy-v1",
                "prompt_version": "prompt-v1",
                "model": {"resolved": "model-v1"},
            },
            {
                "source_id": source_ids[2],
                "classification": _classification(
                    source_ids[2],
                    subsystems=["other"],
                    scope="agnostic",
                    accelerators=[],
                ),
                "taxonomy_version": "taxonomy-v1",
                "prompt_version": "prompt-v1",
                "model": {"resolved": "model-v1"},
            },
        ],
    )
    _write_jsonl(
        manifest_path,
        [
            {
                "source_id": source_ids[0],
                "created_at": "2024-01-01T00:00:00Z",
                "merged_at_by_cutoff": "2024-01-02T00:00:00Z",
                "file_paths_source": "default_branch_git_history",
                "additions": 10,
                "deletions": 2,
            },
            {
                "source_id": source_ids[1],
                "created_at": "2025-02-01T00:00:00Z",
                "merged_at_by_cutoff": None,
                "file_paths_source": "unavailable_in_base_snapshot",
                "additions": None,
                "deletions": None,
            },
            {
                "source_id": source_ids[2],
                "created_at": "2026-03-01T00:00:00Z",
                "merged_at_by_cutoff": None,
                "file_paths_source": "unavailable_in_base_snapshot",
                "additions": None,
                "deletions": None,
            },
        ],
    )
    _write_jsonl(
        github_path,
        [
            {
                "source_id": source_ids[0],
                "user": {"login": "human", "type": "User"},
                "closed_at": "2024-01-02T00:00:00Z",
            },
            {
                "source_id": source_ids[1],
                "user": {"login": "human2", "type": "User"},
                "closed_at": "2025-03-01T00:00:00Z",
            },
            {
                "source_id": source_ids[2],
                "user": {"login": "dependabot[bot]", "type": "Bot"},
                "closed_at": None,
            },
        ],
    )

    result = summarize_labels(
        labels_path,
        manifest_path,
        github_path,
        cutoff="2026-08-08T23:59:59Z",
    )

    assert result["population"]["all_prs"] == 3
    assert result["population"]["human_prs"] == 2
    assert result["population"]["bot_prs"] == 1
    assert result["population"]["human_status_at_cutoff"] == {
        "closed_unmerged": 1,
        "merged": 1,
    }
    assert result["subsystems"]["multi_subsystem_prs"] == {
        "count": 1,
        "percent": 50.0,
    }
    assert result["subsystems"]["top_cooccurrences"][0] == {
        "labels": ["hardware_backends", "kernels_operators"],
        "count": 1,
    }
    assert result["accelerators"]["vendors_overall"]["amd_rocm"] == {
        "count": 1,
        "percent": 50.0,
    }
    assert result["evidence_quality"][
        "file_backed_churn_median_by_subsystem"
    ]["kernels_operators"] == 12


def test_summarize_labels_rejects_population_mismatch(tmp_path: Path) -> None:
    labels = tmp_path / "labels.jsonl"
    manifest = tmp_path / "manifest.jsonl"
    github = tmp_path / "github.jsonl"
    _write_jsonl(labels, [{"source_id": "vllm__pr__1"}])
    _write_jsonl(manifest, [])
    _write_jsonl(github, [])

    with pytest.raises(ValueError, match="PR populations differ"):
        summarize_labels(
            labels,
            manifest,
            github,
            cutoff="2026-08-08T23:59:59Z",
        )
