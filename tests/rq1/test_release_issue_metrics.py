import sqlite3
from pathlib import Path

import pytest

from ai_infra_bench.rq1.release_issue_metrics import (
    derive_release_issue_metrics,
)


def _database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE dataset_metadata (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE dataset_table_inventory (
                table_name TEXT PRIMARY KEY, layer TEXT, row_count INTEGER,
                notes TEXT
            );
            CREATE TABLE user (id INTEGER, login TEXT, type TEXT);
            CREATE TABLE repo_collaborator (
                user_id INTEGER, role_name TEXT, _fivetran_deleted INTEGER
            );
            CREATE TABLE delta_artifact_raw (
                database_id INTEGER, raw_json TEXT
            );
            CREATE TABLE delta_issue_comment_raw (id INTEGER, raw_json TEXT);
            CREATE TABLE canonical_artifact (
                database_id INTEGER PRIMARY KEY, number INTEGER,
                artifact_type TEXT, repository TEXT, author_id INTEGER,
                author_login TEXT, author_association TEXT, created_at TEXT,
                state_at_cutoff TEXT, closed_at_cutoff TEXT, source_layer TEXT,
                representation_may_postdate_cutoff INTEGER
            );
            CREATE VIEW canonical_issue AS
                SELECT * FROM canonical_artifact WHERE artifact_type = 'Issue';
            CREATE TABLE canonical_issue_comment (
                database_id INTEGER PRIMARY KEY, artifact_id INTEGER,
                author_id INTEGER, author_login TEXT,
                author_association TEXT, body TEXT, created_at TEXT,
                source_layer TEXT,
                representation_may_postdate_cutoff INTEGER
            );
            CREATE TABLE issue_closed_history (
                closed INTEGER, issue_id INTEGER, updated_at TEXT,
                actor_id REAL
            );
            CREATE TABLE canonical_maintenance_event (
                event_id TEXT PRIMARY KEY, artifact_id INTEGER,
                event_type TEXT, created_at TEXT, actor_id INTEGER,
                actor_login TEXT
            );
            """
        )
        connection.executemany(
            "INSERT INTO dataset_metadata VALUES (?, ?)",
            [
                ("analysis_cutoff", "2026-01-31T23:59:59Z"),
                ("base_cutoff", "2026-01-20T00:00:00Z"),
                ("schema_version", "1.0.0"),
            ],
        )
        connection.executemany(
            "INSERT INTO dataset_table_inventory VALUES (?, ?, ?, ?)",
            [
                ("canonical_artifact", "canonical_cutoff", 2, ""),
                ("canonical_issue_comment", "canonical_cutoff", 3, ""),
                ("canonical_maintenance_event", "canonical_cutoff", 0, ""),
            ],
        )
        connection.executemany(
            "INSERT INTO user VALUES (?, ?, ?)",
            [
                (1, "reporter", "User"),
                (2, "collaborator", "User"),
                (3, "automation", "Bot"),
                (4, "community", "User"),
            ],
        )
        connection.execute(
            "INSERT INTO repo_collaborator VALUES (2, 'write', 0)"
        )
        connection.executemany(
            """
            INSERT INTO canonical_artifact VALUES
            (?, ?, 'Issue', 'vllm-project/vllm', ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            [
                (
                    101,
                    1,
                    1,
                    "reporter",
                    "NONE",
                    "2026-01-01T00:00:00Z",
                    "CLOSED",
                    "2026-01-10T00:00:00Z",
                    "base",
                ),
                (
                    102,
                    2,
                    2,
                    "collaborator",
                    "MEMBER",
                    "2026-01-15T00:00:00Z",
                    "OPEN",
                    None,
                    "delta",
                ),
            ],
        )
        connection.executemany(
            """
            INSERT INTO canonical_issue_comment VALUES
            (?, ?, ?, ?, 'NONE', ?, ?, ?, 0)
            """,
            [
                (
                    201,
                    101,
                    3,
                    "automation",
                    "automated reply",
                    "2026-01-01T01:00:00Z",
                    "base",
                ),
                (
                    202,
                    101,
                    2,
                    "collaborator",
                    "Please provide a complete reproducer.",
                    "2026-01-02T00:00:00Z",
                    "base",
                ),
                (
                    203,
                    102,
                    999,
                    "unknown-actor",
                    "This has no verified GitHub actor type.",
                    "2026-01-15T01:00:00Z",
                    "delta",
                ),
            ],
        )
        connection.execute(
            """
            INSERT INTO issue_closed_history
            VALUES (1, 101, '2026-01-10T00:00:00Z', 2)
            """
        )


def test_release_adapter_uses_canonical_state_and_snapshot_roster(
    tmp_path: Path,
) -> None:
    database = tmp_path / "release.sqlite"
    _database(database)

    records, summary = derive_release_issue_metrics(database)

    first = records[0]
    assert first["status_at_cutoff"] == "closed"
    assert first["time_to_first_human_response_hours"] == 24.0
    assert first["time_to_first_snapshot_collaborator_response_hours"] == 24.0
    assert first["qualifying_human_comments"] == 1
    assert records[1]["author_group"] == "snapshot_collaborator"
    assert records[1]["qualifying_human_comments"] == 0
    assert "first_snapshot_collaborator_response" in summary["human_overall"]
    assert summary["source_counts"]["snapshot_collaborators"] == 1
    assert summary["metadata"]["collaborator_roster_cutoff"] == (
        "2026-01-20T00:00:00Z"
    )
    assert summary["data_quality"][
        "lifecycle_events_from_base_issue_closed_history"
    ] == 1
    assert summary["data_quality"]["comments_with_unknown_actor_type"] == 1


def test_release_adapter_rejects_a_noncanonical_cutoff(tmp_path: Path) -> None:
    database = tmp_path / "release.sqlite"
    _database(database)

    with pytest.raises(ValueError, match="canonical release analysis_cutoff"):
        derive_release_issue_metrics(
            database,
            cutoff="2026-01-30T23:59:59Z",
        )
