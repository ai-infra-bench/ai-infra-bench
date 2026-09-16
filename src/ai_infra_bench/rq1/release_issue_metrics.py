"""Adapt the canonical vLLM GitHub release database to issue metrics."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_infra_bench.rq1.issue_metrics import derive_issue_metrics_from_objects

RELEASE_TAG = "vllm-github-data-2026-07-31"
RELEASE_URL = (
    "https://github.com/ai-infra-bench/ai-infra-bench/releases/tag/"
    f"{RELEASE_TAG}"
)
RELEASE_DATABASE_SHA256 = (
    "2ac86507a95f9b8785e6ce0bbf2745e3fbba67c747e37b54020a7e57ce80f8b5"
)
SNAPSHOT_COLLABORATOR_ROLES = frozenset(
    {"triage", "write", "maintain", "admin"}
)


def derive_release_issue_metrics(
    database_path: Path,
    *,
    cutoff: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Derive issue metrics from the canonical release SQLite database."""
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        metadata = _metadata(connection)
        release_cutoff = metadata.get("analysis_cutoff")
        if not release_cutoff:
            raise ValueError("release database has no analysis_cutoff metadata")
        if cutoff is not None and _iso_time(cutoff) != _iso_time(release_cutoff):
            raise ValueError(
                "cutoff must equal the canonical release analysis_cutoff: "
                f"{release_cutoff}"
            )
        cutoff = _iso_time(release_cutoff)
        actor_types, actor_types_by_login = _actor_type_maps(connection)
        roster = _snapshot_collaborators(connection)
        base, database_ids, details = _issues(
            connection,
            actor_types,
            actor_types_by_login,
            roster,
        )
        comment_quality = _comments(
            connection,
            details,
            database_ids,
            actor_types,
            actor_types_by_login,
            roster,
            cutoff,
        )
        lifecycle_quality = _lifecycle_events(
            connection,
            details,
            database_ids,
            actor_types,
            actor_types_by_login,
            cutoff,
        )
        _finalize_connections(base, details)
        inventory = _inventory(connection)

    records, summary = derive_issue_metrics_from_objects(
        details.values(), base, cutoff=cutoff
    )
    records = [_rename_record(record) for record in records]
    summary = _rename_summary(summary)
    _add_release_metadata(
        summary,
        metadata=metadata,
        inventory=inventory,
        roster=roster,
        comment_quality=comment_quality,
        lifecycle_quality=lifecycle_quality,
    )
    return records, summary


def _metadata(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        row["key"]: row["value"]
        for row in connection.execute(
            "SELECT key, value FROM dataset_metadata ORDER BY key"
        )
    }


def _inventory(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        row["table_name"]: int(row["row_count"])
        for row in connection.execute(
            "SELECT table_name, row_count FROM dataset_table_inventory"
        )
    }


def _actor_type_maps(
    connection: sqlite3.Connection,
) -> tuple[dict[int, str], dict[str, str]]:
    by_id: dict[int, str] = {}
    by_login: dict[str, str] = {}
    for row in connection.execute("SELECT id, login, type FROM user"):
        _remember_actor_type(by_id, by_login, row["id"], row["login"], row["type"])
    for table in ("delta_artifact_raw", "delta_issue_comment_raw"):
        for row in connection.execute(f"SELECT raw_json FROM {table}"):
            value = json.loads(row["raw_json"])
            user = value.get("user") or {}
            _remember_actor_type(
                by_id,
                by_login,
                user.get("id") or user.get("databaseId"),
                user.get("login"),
                user.get("type") or user.get("__typename"),
            )
    return by_id, by_login


def _remember_actor_type(
    by_id: dict[int, str],
    by_login: dict[str, str],
    actor_id: int | None,
    login: str | None,
    actor_type: str | None,
) -> None:
    if actor_type not in {"User", "Bot", "Organization"}:
        return
    if actor_id is not None:
        by_id[int(actor_id)] = actor_type
    if login:
        by_login[login.casefold()] = actor_type


def _snapshot_collaborators(connection: sqlite3.Connection) -> dict[str, Any]:
    members = []
    for row in connection.execute(
        """
        SELECT c.user_id, u.login, lower(c.role_name) AS role_name
        FROM repo_collaborator AS c
        JOIN user AS u ON u.id = c.user_id
        WHERE coalesce(c._fivetran_deleted, 0) = 0
        ORDER BY c.user_id
        """
    ):
        if row["role_name"] in SNAPSHOT_COLLABORATOR_ROLES:
            members.append(dict(row))
    role_counts = Counter(member["role_name"] for member in members)
    return {
        "ids": {int(member["user_id"]) for member in members},
        "logins": {
            member["login"].casefold() for member in members if member["login"]
        },
        "count": len(members),
        "role_counts": dict(sorted(role_counts.items())),
        "triage_only_count": role_counts["triage"],
        "write_or_higher_count": sum(
            role_counts[role] for role in ("write", "maintain", "admin")
        ),
    }


def _issues(
    connection: sqlite3.Connection,
    actor_types: dict[int, str],
    actor_types_by_login: dict[str, str],
    roster: dict[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[int, str],
    dict[str, dict[str, Any]],
]:
    base: dict[str, dict[str, Any]] = {}
    database_ids: dict[int, str] = {}
    details: dict[str, dict[str, Any]] = {}
    rows = connection.execute(
        """
        SELECT database_id, number, repository, author_id, author_login,
               author_association, created_at, state_at_cutoff,
               closed_at_cutoff, source_layer,
               representation_may_postdate_cutoff
        FROM canonical_issue
        ORDER BY number
        """
    )
    for row in rows:
        source_id = f"{row['repository'].split('/')[-1]}__issue__{row['number']}"
        actor = _actor(
            row["author_id"],
            row["author_login"],
            actor_types,
            actor_types_by_login,
        )
        base[source_id] = {
            "source_id": source_id,
            "number": int(row["number"]),
            "created_at": _iso_time(row["created_at"]),
            "closed_at": _optional_iso_time(row["closed_at_cutoff"]),
            "state_at_cutoff": row["state_at_cutoff"].lower(),
            "user": actor,
            "author_association": row["author_association"] or "NONE",
            "author_is_snapshot_collaborator": _is_snapshot_collaborator(
                row["author_id"], row["author_login"], roster
            ),
            "source_layer": row["source_layer"],
            "representation_may_postdate_cutoff": bool(
                row["representation_may_postdate_cutoff"]
            ),
        }
        database_ids[int(row["database_id"])] = source_id
        details[source_id] = {
            "source_id": source_id,
            "api_missing": False,
            "comments": {"nodes": []},
            "timelineItems": {"nodes": []},
        }
    return base, database_ids, details


def _comments(
    connection: sqlite3.Connection,
    details: dict[str, dict[str, Any]],
    database_ids: dict[int, str],
    actor_types: dict[int, str],
    actor_types_by_login: dict[str, str],
    roster: dict[str, Any],
    cutoff: str,
) -> dict[str, int]:
    quality = Counter()
    rows = connection.execute(
        """
        SELECT c.artifact_id, c.author_id, c.author_login,
               c.author_association, c.body, c.created_at,
               c.source_layer, c.representation_may_postdate_cutoff
        FROM canonical_issue_comment AS c
        JOIN canonical_issue AS i ON i.database_id = c.artifact_id
        ORDER BY c.artifact_id, c.created_at, c.database_id
        """
    )
    cutoff_at = _parse_time(cutoff)
    for row in rows:
        if _parse_time(row["created_at"]) > cutoff_at:
            quality["comments_after_cutoff_ignored"] += 1
            continue
        source_id = database_ids[int(row["artifact_id"])]
        actor = _actor(
            row["author_id"],
            row["author_login"],
            actor_types,
            actor_types_by_login,
        )
        if actor.get("type") is None:
            quality["comments_with_unknown_actor_type"] += 1
        if row["representation_may_postdate_cutoff"]:
            quality["comments_with_text_may_postdate_cutoff"] += 1
        quality[f"comments_from_{row['source_layer']}"] += 1
        details[source_id]["comments"]["nodes"].append(
            {
                "author": actor,
                "authorAssociation": row["author_association"] or "NONE",
                "isSnapshotCollaborator": _is_snapshot_collaborator(
                    row["author_id"], row["author_login"], roster
                ),
                "body": row["body"],
                "createdAt": _iso_time(row["created_at"]),
            }
        )
    return dict(sorted(quality.items()))


def _lifecycle_events(
    connection: sqlite3.Connection,
    details: dict[str, dict[str, Any]],
    database_ids: dict[int, str],
    actor_types: dict[int, str],
    actor_types_by_login: dict[str, str],
    cutoff: str,
) -> dict[str, int]:
    quality = Counter()
    cutoff_at = _parse_time(cutoff)
    base_rows = connection.execute(
        """
        SELECT h.issue_id AS artifact_id, h.closed, h.updated_at AS created_at,
               cast(h.actor_id AS INTEGER) AS actor_id, u.login AS actor_login
        FROM issue_closed_history AS h
        JOIN canonical_issue AS i ON i.database_id = h.issue_id
        LEFT JOIN user AS u ON u.id = cast(h.actor_id AS INTEGER)
        WHERE i.source_layer = 'base'
        ORDER BY h.issue_id, h.updated_at
        """
    )
    for row in base_rows:
        _append_lifecycle_event(
            row,
            source="base_issue_closed_history",
            details=details,
            database_ids=database_ids,
            actor_types=actor_types,
            actor_types_by_login=actor_types_by_login,
            cutoff_at=cutoff_at,
            quality=quality,
            event_type="ClosedEvent" if row["closed"] else "ReopenedEvent",
        )

    delta_rows = connection.execute(
        """
        SELECT e.artifact_id, e.event_type, e.created_at,
               e.actor_id, e.actor_login
        FROM canonical_maintenance_event AS e
        JOIN canonical_issue AS i ON i.database_id = e.artifact_id
        WHERE i.source_layer = 'delta'
          AND e.event_type IN ('ClosedEvent', 'ReopenedEvent')
        ORDER BY e.artifact_id, e.created_at, e.event_id
        """
    )
    for row in delta_rows:
        _append_lifecycle_event(
            row,
            source="delta_canonical_maintenance_event",
            details=details,
            database_ids=database_ids,
            actor_types=actor_types,
            actor_types_by_login=actor_types_by_login,
            cutoff_at=cutoff_at,
            quality=quality,
            event_type=row["event_type"],
        )
    return dict(sorted(quality.items()))


def _append_lifecycle_event(
    row: sqlite3.Row,
    *,
    source: str,
    details: dict[str, dict[str, Any]],
    database_ids: dict[int, str],
    actor_types: dict[int, str],
    actor_types_by_login: dict[str, str],
    cutoff_at: datetime,
    quality: Counter[str],
    event_type: str,
) -> None:
    if _parse_time(row["created_at"]) > cutoff_at:
        quality["lifecycle_events_after_cutoff_ignored"] += 1
        return
    actor = _actor(
        row["actor_id"],
        row["actor_login"],
        actor_types,
        actor_types_by_login,
    )
    if actor is None or actor.get("type") is None:
        quality["lifecycle_events_with_unknown_actor_type"] += 1
    quality[f"lifecycle_events_from_{source}"] += 1
    source_id = database_ids[int(row["artifact_id"])]
    details[source_id]["timelineItems"]["nodes"].append(
        {
            "__typename": event_type,
            "createdAt": _iso_time(row["created_at"]),
            "actor": actor,
        }
    )


def _finalize_connections(
    base: dict[str, dict[str, Any]],
    details: dict[str, dict[str, Any]],
) -> None:
    for source_id, detail in details.items():
        for name in ("comments", "timelineItems"):
            count = len(detail[name]["nodes"])
            detail[name].update(
                {
                    "observed_total_count": count,
                    "retrieved_count": count,
                    "at_cutoff_count": count,
                }
            )
        base[source_id]["comments"] = len(detail["comments"]["nodes"])


def _actor(
    actor_id: int | None,
    login: str | None,
    actor_types: dict[int, str],
    actor_types_by_login: dict[str, str],
) -> dict[str, Any] | None:
    if actor_id is None and not login:
        return None
    actor_type = None
    if actor_id is not None:
        actor_type = actor_types.get(int(actor_id))
    if actor_type is None and login:
        actor_type = actor_types_by_login.get(login.casefold())
    return {
        "login": login,
        "type": actor_type,
        "_actor_type_policy": "github_user_type",
    }


def _is_snapshot_collaborator(
    actor_id: int | None,
    login: str | None,
    roster: dict[str, Any],
) -> bool:
    return bool(
        (actor_id is not None and int(actor_id) in roster["ids"])
        or (login and login.casefold() in roster["logins"])
    )


def _rename_record(record: dict[str, Any]) -> dict[str, Any]:
    renamed = _rename_keys(record)
    if renamed["author_group"] == "maintainer":
        renamed["author_group"] = "snapshot_collaborator"
    return renamed


def _rename_summary(summary: dict[str, Any]) -> dict[str, Any]:
    renamed = _rename_keys(summary)
    groups = renamed.get("human_by_author_group", {})
    if "maintainer" in groups:
        groups["snapshot_collaborator"] = groups.pop("maintainer")
    metadata = renamed["metadata"]
    metadata.pop("snapshot_collaborator_associations", None)
    metadata["active_snapshot_collaborator_note"] = (
        "Monthly active issue snapshot-collaborator responders are actors in "
        "the frozen collaborator roster with a qualifying non-author issue "
        "comment. This is narrower than the study-wide people denominator."
    )
    return renamed


def _rename_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key.replace("maintainer", "snapshot_collaborator"): _rename_keys(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_rename_keys(item) for item in value]
    return value


def _add_release_metadata(
    summary: dict[str, Any],
    *,
    metadata: dict[str, str],
    inventory: dict[str, int],
    roster: dict[str, Any],
    comment_quality: dict[str, int],
    lifecycle_quality: dict[str, int],
) -> None:
    issue_comment_count = summary["source_counts"].pop("base_comment_count")
    observed_comment_difference = summary["data_quality"].pop(
        "base_minus_observed_comments"
    )
    summary["metadata"].update(
        {
            "primary_source": "canonical release SQLite",
            "release_tag": RELEASE_TAG,
            "release_url": RELEASE_URL,
            "release_database_expected_sha256": RELEASE_DATABASE_SHA256,
            "release_schema_version": metadata.get("schema_version"),
            "base_cutoff": metadata.get("base_cutoff"),
            "collaborator_roster_cutoff": metadata.get("base_cutoff"),
            "snapshot_collaborator_roles": sorted(
                SNAPSHOT_COLLABORATOR_ROLES
            ),
            "snapshot_collaborator_semantics": (
                "The roster is the May 18 repository collaborator snapshot. "
                "It is not historical event-time membership and must not be "
                "interpreted as such."
            ),
            "bot_definition": "GitHub user.type == Bot",
            "substantive_metric_status": (
                "exploratory sensitivity only; formal substantive-response "
                "results require human annotation"
            ),
            "api_supplement_note": (
                "The 2026-08-08 API snapshot is a later supplement and is not "
                "the primary data layer for this release-aligned analysis."
            ),
        }
    )
    summary["source_counts"].update(
        {
            "canonical_artifacts_all_types": inventory.get(
                "canonical_artifact", 0
            ),
            "canonical_conversation_comments_all_types": inventory.get(
                "canonical_issue_comment", 0
            ),
            "canonical_maintenance_events_all_types": inventory.get(
                "canonical_maintenance_event", 0
            ),
            "canonical_issues": summary["population"]["all_issues"],
            "canonical_issue_comments": issue_comment_count,
            "canonical_pull_requests": inventory.get(
                "canonical_pull_request", 0
            ),
            "canonical_pull_request_reviews": inventory.get(
                "canonical_pull_request_review", 0
            ),
            "canonical_inline_review_comments": inventory.get(
                "canonical_review_comment", 0
            ),
            "snapshot_collaborators": roster["count"],
            "snapshot_collaborators_triage_only": roster[
                "triage_only_count"
            ],
            "snapshot_collaborators_write_or_higher": roster[
                "write_or_higher_count"
            ],
        }
    )
    summary["data_quality"].update(comment_quality)
    summary["data_quality"].update(lifecycle_quality)
    summary["data_quality"][
        "canonical_minus_observed_issue_comments"
    ] = observed_comment_difference
    summary["data_quality"]["comment_count_note"] = (
        "Canonical issue comments are the cutoff census. Four delta-layer "
        "comment bodies may reflect edits observed after the cutoff; their "
        "event timestamps remain cutoff-valid."
    )
    summary["data_quality"]["canonical_state_note"] = (
        "canonical_issue.state_at_cutoff is authoritative at the release cutoff; "
        "timeline gaps appear as state reconciliation adjustments."
    )


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso_time(value: str) -> str:
    return _parse_time(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _optional_iso_time(value: str | None) -> str | None:
    return _iso_time(value) if value else None
