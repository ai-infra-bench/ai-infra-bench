import json
import sqlite3
from pathlib import Path

from ai_infra_bench.rq1.release_label_alignment import (
    align_release_labels,
    build_missing_release_label_manifest,
)


def _classification(source_id: str, subsystem: str) -> dict:
    return {
        "source_id": source_id,
        "subsystems": [subsystem],
        "accelerator_scope": "agnostic",
        "accelerators": [],
        "subsystem_confidence": "high",
        "accelerator_confidence": "high",
        "rationale": "Fixture label",
        "evidence": [],
    }


def _label(number: int, subsystem: str) -> dict:
    source_id = f"vllm__pr__{number}"
    return {
        "source_id": source_id,
        "number": number,
        "classification": _classification(source_id, subsystem),
        "schema_version": "1.0",
        "taxonomy_version": "taxonomy-v1",
        "prompt_version": "prompt-v1",
        "input_sha256": f"hash-{number}",
        "labeled_at": "2026-02-02T00:00:00Z",
        "model": {"requested": "model", "resolved": "model-v1"},
    }


def _database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE dataset_metadata (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE user (id INTEGER, login TEXT, type TEXT);
            CREATE TABLE delta_artifact_raw (
                database_id INTEGER, raw_json TEXT
            );
            CREATE TABLE canonical_artifact (
                database_id INTEGER PRIMARY KEY, number INTEGER,
                repository TEXT, title TEXT, body TEXT,
                author_id INTEGER, author_login TEXT, created_at TEXT,
                state_at_cutoff TEXT, source_layer TEXT,
                representation_may_postdate_cutoff INTEGER
            );
            CREATE TABLE canonical_pull_request (
                database_id INTEGER PRIMARY KEY, artifact_id INTEGER,
                files_cutoff_stable INTEGER
            );
            CREATE TABLE canonical_artifact_label (
                artifact_id INTEGER, label_name TEXT
            );
            CREATE TABLE canonical_pull_request_file (
                pull_request_id INTEGER, path TEXT, additions INTEGER,
                deletions INTEGER, cutoff_stable INTEGER
            );
            CREATE TABLE canonical_pull_request_commit (
                pull_request_id INTEGER, commit_sha TEXT
            );
            CREATE TABLE commit_file (
                commit_sha TEXT, filename TEXT, additions INTEGER,
                deletions INTEGER
            );
            """
        )
        connection.executemany(
            "INSERT INTO dataset_metadata VALUES (?, ?)",
            [
                ("analysis_cutoff", "2026-01-31T23:59:59Z"),
                ("base_cutoff", "2026-01-20T00:00:00Z"),
            ],
        )
        connection.executemany(
            "INSERT INTO user VALUES (?, ?, ?)",
            [(10, "human", "User"), (20, "automation", "Bot")],
        )
        connection.executemany(
            """
            INSERT INTO canonical_artifact VALUES
            (?, ?, 'vllm-project/vllm', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    101,
                    1,
                    "Model support",
                    "Adds a model.",
                    10,
                    "human",
                    "2024-01-01T00:00:00Z",
                    "MERGED",
                    "base",
                    0,
                ),
                (
                    102,
                    2,
                    "Scheduler change",
                    "Changes scheduling.",
                    10,
                    "human",
                    "2025-01-01T00:00:00Z",
                    "OPEN",
                    "base",
                    0,
                ),
                (
                    103,
                    3,
                    "Automation",
                    "Automated change.",
                    20,
                    "automation",
                    "2026-01-01T00:00:00Z",
                    "CLOSED",
                    "delta",
                    1,
                ),
            ],
        )
        connection.executemany(
            "INSERT INTO canonical_pull_request VALUES (?, ?, ?)",
            [(201, 101, 1), (202, 102, 1), (203, 103, 0)],
        )
        connection.execute(
            "INSERT INTO canonical_artifact_label VALUES (101, 'model')"
        )
        connection.execute(
            "INSERT INTO canonical_pull_request_commit VALUES (201, 'abc')"
        )
        connection.execute(
            "INSERT INTO commit_file VALUES ('abc', 'vllm/model.py', 10, 2)"
        )


def test_align_release_labels_preserves_missingness_and_release_denominator(
    tmp_path: Path,
) -> None:
    database = tmp_path / "release.sqlite"
    labels = tmp_path / "labels.jsonl"
    _database(database)
    labels.write_text(
        "".join(
            json.dumps(value) + "\n"
            for value in (
                _label(1, "models"),
                _label(3, "other"),
                _label(4, "scheduling"),
            )
        )
    )

    records, summary = align_release_labels(
        database,
        labels,
        label_source_cutoff="2026-02-01T23:59:59Z",
    )

    assert [record["label_status"] for record in records] == [
        "labeled",
        "missing_release_pr_label",
        "labeled",
    ]
    assert summary["coverage"]["release_prs"] == 3
    assert summary["coverage"]["release_prs_labeled"] == 2
    assert summary["coverage"]["release_prs_missing_labels"] == 1
    assert summary["coverage"]["label_records_outside_release"] == 1
    assert summary["coverage"]["release_human_prs"] == 2
    assert summary["coverage"]["release_human_prs_labeled"] == 1
    assert summary["coverage"]["missing_release_pr_numbers"] == [2]
    assert summary["subsystems"]["overall"]["models"] == {
        "count": 1,
        "percent": 100.0,
    }


def test_build_missing_manifest_recovers_base_merge_commit_files(
    tmp_path: Path,
) -> None:
    database = tmp_path / "release.sqlite"
    labels = tmp_path / "labels.jsonl"
    _database(database)
    labels.write_text(
        "".join(
            json.dumps(value) + "\n"
            for value in (_label(2, "scheduling"), _label(3, "other"))
        )
    )

    records, summary = build_missing_release_label_manifest(database, labels)

    assert len(records) == 1
    assert records[0]["source_id"] == "vllm__pr__1"
    assert records[0]["github_labels"] == ["model"]
    assert records[0]["file_paths_source"] == "base_merge_commit_files"
    assert records[0]["files"] == [
        {"path": "vllm/model.py", "additions": 10, "deletions": 2}
    ]
    assert summary["records_with_file_paths"] == 1
