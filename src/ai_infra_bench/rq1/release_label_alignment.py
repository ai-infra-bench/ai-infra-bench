"""Map model-produced PR labels onto the canonical release population."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from statistics import mean
from typing import Any

from ai_infra_bench.rq1.release_issue_metrics import RELEASE_TAG, RELEASE_URL
from ai_infra_bench.rq1.taxonomy import (
    ACCELERATOR_SCOPES,
    ACCELERATORS,
    SUBSYSTEMS,
    Classification,
)

PERIODS = ("launch_through_2024", "2025", "2026_through_cutoff")


def align_release_labels(
    database_path: Path,
    labels_path: Path | list[Path],
    *,
    label_source_cutoff: str | list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return release PR records with matched labels and coverage summaries."""
    labels = _load_labels(
        labels_path,
        source_cutoffs=label_source_cutoff,
    )
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        metadata = dict(
            connection.execute(
                "SELECT key, value FROM dataset_metadata ORDER BY key"
            )
        )
        rows = list(
            connection.execute(
                """
                SELECT a.database_id, a.number, a.author_id, a.author_login,
                       coalesce(json_extract(d.raw_json, '$.user.type'), u.type)
                           AS author_type,
                       a.created_at, a.state_at_cutoff, a.source_layer,
                       a.representation_may_postdate_cutoff,
                       p.files_cutoff_stable
                FROM canonical_artifact AS a
                JOIN canonical_pull_request AS p
                  ON p.artifact_id = a.database_id
                LEFT JOIN user AS u ON u.id = a.author_id
                LEFT JOIN delta_artifact_raw AS d
                  ON d.database_id = a.database_id
                ORDER BY a.number
                """
            )
        )

    records = []
    matched_source_ids: set[str] = set()
    taxonomy_versions: set[str] = set()
    prompt_versions: set[str] = set()
    resolved_models: set[str] = set()
    for row in rows:
        source_id = f"vllm__pr__{row['number']}"
        label = labels.get(source_id)
        record = {
            "source_id": source_id,
            "number": int(row["number"]),
            "release_created_at": _iso_time(row["created_at"]),
            "release_state_at_cutoff": row["state_at_cutoff"].lower(),
            "release_source_layer": row["source_layer"],
            "release_files_cutoff_stable": bool(row["files_cutoff_stable"]),
            "release_representation_may_postdate_cutoff": bool(
                row["representation_may_postdate_cutoff"]
            ),
            "author": {
                "id": row["author_id"],
                "login": row["author_login"],
                "type": row["author_type"],
            },
            "label_status": "labeled" if label else "missing_release_pr_label",
            "classification": None,
            "label_provenance": None,
        }
        if label:
            classification = Classification.from_dict(label["classification"])
            if classification.source_id != source_id:
                raise ValueError(f"classification source_id mismatch: {source_id}")
            if int(label.get("number", row["number"])) != row["number"]:
                raise ValueError(f"label number mismatch: {source_id}")
            record["classification"] = classification.to_dict()
            record["label_provenance"] = {
                "schema_version": label.get("schema_version"),
                "taxonomy_version": label.get("taxonomy_version"),
                "prompt_version": label.get("prompt_version"),
                "input_sha256": label.get("input_sha256"),
                "labeled_at": label.get("labeled_at"),
                "model": label.get("model"),
                "input_snapshot_cutoff": label["_input_snapshot_cutoff"],
            }
            matched_source_ids.add(source_id)
            taxonomy_versions.add(label["taxonomy_version"])
            prompt_versions.add(label["prompt_version"])
            resolved_models.add(label["model"]["resolved"])
        records.append(record)

    release_source_ids = {record["source_id"] for record in records}
    summary = _summarize(
        records,
        release_cutoff=metadata["analysis_cutoff"],
        base_cutoff=metadata.get("base_cutoff"),
        label_source_cutoffs=sorted(
            {label["_input_snapshot_cutoff"] for label in labels.values()}
        ),
        extra_label_source_ids=sorted(set(labels) - release_source_ids),
        taxonomy_versions=taxonomy_versions,
        prompt_versions=prompt_versions,
        resolved_models=resolved_models,
    )
    if len(matched_source_ids) != summary["coverage"]["release_prs_labeled"]:
        raise AssertionError("matched label count is inconsistent")
    return records, summary


def build_missing_release_label_manifest(
    database_path: Path,
    labels_path: Path | list[Path],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build model inputs for canonical Release PRs without labels."""
    labels = _load_labels(labels_path)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        metadata = dict(
            connection.execute(
                "SELECT key, value FROM dataset_metadata ORDER BY key"
            )
        )
        artifacts = list(
            connection.execute(
                """
                SELECT a.database_id AS artifact_id,
                       p.database_id AS pull_request_id,
                       a.number, a.repository, a.title, a.body,
                       a.created_at, a.state_at_cutoff, a.source_layer,
                       a.representation_may_postdate_cutoff,
                       p.files_cutoff_stable
                FROM canonical_artifact AS a
                JOIN canonical_pull_request AS p
                  ON p.artifact_id = a.database_id
                ORDER BY a.number
                """
            )
        )
        missing = [
            row
            for row in artifacts
            if f"vllm__pr__{row['number']}" not in labels
        ]
        artifact_ids = [int(row["artifact_id"]) for row in missing]
        pull_request_ids = [int(row["pull_request_id"]) for row in missing]
        github_labels = _release_github_labels(connection, artifact_ids)
        canonical_files = _canonical_pr_files(connection, pull_request_ids)
        base_commit_files = _base_commit_files(connection, pull_request_ids)

    records = []
    source_counts = Counter()
    for row in missing:
        artifact_id = int(row["artifact_id"])
        pull_request_id = int(row["pull_request_id"])
        files = canonical_files[pull_request_id]
        file_source = "canonical_release_pr_files"
        if not files and row["state_at_cutoff"] == "MERGED":
            files = base_commit_files[pull_request_id]
            file_source = "base_merge_commit_files"
        if not files:
            file_source = "unavailable"
        source_counts[file_source] += 1
        evidence_risks = []
        if row["representation_may_postdate_cutoff"]:
            evidence_risks.append("text_representation_may_postdate_cutoff")
        if not row["files_cutoff_stable"]:
            evidence_risks.append("files_not_cutoff_stable")
        if not files:
            evidence_risks.append("file_paths_unavailable")
        source_id = f"vllm__pr__{row['number']}"
        record = {
            "schema_version": "1.0",
            "source_id": source_id,
            "repo": row["repository"],
            "source_type": "pull_request",
            "number": int(row["number"]),
            "title": row["title"] or "",
            "body": row["body"] or "",
            "created_at": _iso_time(row["created_at"]),
            "snapshot_cutoff": _iso_time(metadata["analysis_cutoff"]),
            "github_labels": github_labels[artifact_id],
            "files": files,
            "changed_files": len(files) if files else None,
            "additions": _sum_file_field(files, "additions"),
            "deletions": _sum_file_field(files, "deletions"),
            "file_paths_source": file_source,
            "file_paths_unavailable": not files,
            "release_source_layer": row["source_layer"],
            "release_state_at_cutoff": row["state_at_cutoff"].lower(),
            "release_representation_may_postdate_cutoff": bool(
                row["representation_may_postdate_cutoff"]
            ),
            "release_files_cutoff_stable": bool(row["files_cutoff_stable"]),
            "evidence_risks": evidence_risks,
        }
        record["input_sha256"] = _manifest_input_sha256(record)
        records.append(record)
    summary = {
        "release_tag": RELEASE_TAG,
        "release_cutoff": _iso_time(metadata["analysis_cutoff"]),
        "missing_label_inputs": len(records),
        "text_representation_cutoff_stable": sum(
            not record["release_representation_may_postdate_cutoff"]
            for record in records
        ),
        "files_cutoff_stable": sum(
            record["release_files_cutoff_stable"] for record in records
        ),
        "file_evidence_sources": dict(sorted(source_counts.items())),
        "records_with_file_paths": sum(bool(record["files"]) for record in records),
        "records_without_file_paths": sum(
            not record["files"] for record in records
        ),
    }
    return records, summary


def write_release_label_manifest(
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    *,
    output: Path,
    summary_output: Path,
) -> None:
    """Write missing-label inputs and their evidence audit."""
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as destination:
        for record in records:
            destination.write(json.dumps(record, sort_keys=True) + "\n")
    summary_output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_release_label_alignment(
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    *,
    records_output: Path,
    summary_output: Path,
) -> None:
    """Write the release-label sidecar and its aggregate summary."""
    records_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    with records_output.open("w", encoding="utf-8") as destination:
        for record in records:
            destination.write(json.dumps(record, sort_keys=True) + "\n")
    summary_output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _summarize(
    records: list[dict[str, Any]],
    *,
    release_cutoff: str,
    base_cutoff: str | None,
    label_source_cutoffs: list[str],
    extra_label_source_ids: list[str],
    taxonomy_versions: set[str],
    prompt_versions: set[str],
    resolved_models: set[str],
) -> dict[str, Any]:
    labeled = [record for record in records if record["classification"]]
    human = [record for record in records if record["author"]["type"] == "User"]
    labeled_human = [record for record in human if record["classification"]]
    missing = [record for record in records if not record["classification"]]
    missing_human = [record for record in human if not record["classification"]]
    labels_by_input_cutoff = Counter(
        record["label_provenance"]["input_snapshot_cutoff"]
        for record in labeled
    )
    actor_types = Counter(record["author"]["type"] or "unknown" for record in records)
    human_arrivals = Counter(
        record["release_created_at"][:7] for record in human
    )
    human_arrivals_by_year = Counter(
        record["release_created_at"][:4] for record in human
    )
    by_period = {
        period: [record for record in labeled_human if _period(record) == period]
        for period in PERIODS
    }
    coverage_by_period = {}
    for period in PERIODS:
        population = [record for record in human if _period(record) == period]
        period_labeled = [record for record in population if record["classification"]]
        coverage_by_period[period] = {
            "release_human_prs": len(population),
            "labeled": len(period_labeled),
            "missing": len(population) - len(period_labeled),
            "coverage_percent": _percent(len(period_labeled), len(population)),
        }

    subsystem_counts = _multi_label_counts(labeled_human, "subsystems", SUBSYSTEMS)
    accelerator_counts = _multi_label_counts(
        labeled_human, "accelerators", ACCELERATORS
    )
    scope_counts = Counter(
        record["classification"]["accelerator_scope"] for record in labeled_human
    )
    subsystem_pairs = Counter(
        pair
        for record in labeled_human
        for pair in combinations(record["classification"]["subsystems"], 2)
    )
    return {
        "metadata": {
            "release_tag": RELEASE_TAG,
            "release_url": RELEASE_URL,
            "release_cutoff": _iso_time(release_cutoff),
            "release_base_cutoff": base_cutoff,
            "label_input_snapshot_cutoffs": [
                _iso_time(value) for value in label_source_cutoffs
            ],
            "classification_unit": "pull_request",
            "taxonomy_versions": sorted(taxonomy_versions),
            "prompt_versions": sorted(prompt_versions),
            "resolved_models": sorted(resolved_models),
            "audit_status": "provisional_pending_stratified_human_audit",
            "temporality_note": (
                "Labels combine the original August 8 API/Git manifest with "
                "a July 31 Release-derived supplement. Per-record provenance "
                "identifies the input cutoff; original labels may use text or "
                "file evidence observed after the Release cutoff."
            ),
            "missingness_note": (
                "All Release PRs have model labels. Taxonomy unknown remains "
                "an evidence-insufficiency label, not a missing record."
                if not missing
                else "Release PRs without a model label remain missing and "
                "are not converted to taxonomy unknown."
            ),
        },
        "coverage": {
            "release_prs": len(records),
            "release_prs_labeled": len(labeled),
            "release_prs_missing_labels": len(missing),
            "release_label_coverage_percent": _percent(len(labeled), len(records)),
            "label_records_outside_release": len(extra_label_source_ids),
            "release_human_prs": len(human),
            "release_human_prs_labeled": len(labeled_human),
            "release_human_prs_missing_labels": len(missing_human),
            "release_human_label_coverage_percent": _percent(
                len(labeled_human), len(human)
            ),
            "labels_by_input_snapshot_cutoff": dict(
                sorted(labels_by_input_cutoff.items())
            ),
            "release_prs_by_actor_type": dict(sorted(actor_types.items())),
            "by_period": coverage_by_period,
            "missing_release_pr_numbers": [record["number"] for record in missing],
            "label_records_outside_release_examples": extra_label_source_ids[:20],
        },
        "release_population": {
            "human_state_at_cutoff": dict(
                sorted(
                    Counter(
                        record["release_state_at_cutoff"] for record in human
                    ).items()
                )
            ),
            "human_prs_by_month": dict(sorted(human_arrivals.items())),
            "human_prs_by_year": dict(sorted(human_arrivals_by_year.items())),
            "human_prs_by_period": {
                period: sum(_period(record) == period for record in human)
                for period in PERIODS
            },
        },
        "subsystems": {
            "denominator": "labeled release human PRs",
            "overall": _count_table(subsystem_counts, len(labeled_human)),
            "by_period": {
                period: _count_table(
                    _multi_label_counts(period_records, "subsystems", SUBSYSTEMS),
                    len(period_records),
                )
                for period, period_records in by_period.items()
            },
            "average_labels_per_pr": round(
                mean(
                    len(record["classification"]["subsystems"])
                    for record in labeled_human
                ),
                3,
            )
            if labeled_human
            else 0.0,
            "multi_subsystem_prs": _count_and_percent(
                sum(
                    len(record["classification"]["subsystems"]) > 1
                    for record in labeled_human
                ),
                len(labeled_human),
            ),
            "top_cooccurrences": [
                {"labels": list(pair), "count": count}
                for pair, count in sorted(
                    subsystem_pairs.items(), key=lambda item: (-item[1], item[0])
                )[:10]
            ],
        },
        "accelerators": {
            "denominator": "labeled release human PRs",
            "scope_overall": _count_table(
                scope_counts, len(labeled_human), labels=ACCELERATOR_SCOPES
            ),
            "scope_by_period": {
                period: _count_table(
                    Counter(
                        record["classification"]["accelerator_scope"]
                        for record in period_records
                    ),
                    len(period_records),
                    labels=ACCELERATOR_SCOPES,
                )
                for period, period_records in by_period.items()
            },
            "vendors_overall": _count_table(
                accelerator_counts, len(labeled_human), labels=ACCELERATORS
            ),
            "vendors_by_period": {
                period: _count_table(
                    _multi_label_counts(
                        period_records, "accelerators", ACCELERATORS
                    ),
                    len(period_records),
                    labels=ACCELERATORS,
                )
                for period, period_records in by_period.items()
            },
        },
        "label_quality": {
            "subsystem_unknown": _count_and_percent(
                sum(
                    "unknown" in record["classification"]["subsystems"]
                    for record in labeled_human
                ),
                len(labeled_human),
            ),
            "subsystem_low_confidence": _count_and_percent(
                sum(
                    record["classification"]["subsystem_confidence"] == "low"
                    for record in labeled_human
                ),
                len(labeled_human),
            ),
            "accelerator_unknown": _count_and_percent(
                sum(
                    record["classification"]["accelerator_scope"] == "unknown"
                    for record in labeled_human
                ),
                len(labeled_human),
            ),
            "accelerator_low_confidence": _count_and_percent(
                sum(
                    record["classification"]["accelerator_confidence"] == "low"
                    for record in labeled_human
                ),
                len(labeled_human),
            ),
            "release_files_cutoff_stable": _count_and_percent(
                sum(record["release_files_cutoff_stable"] for record in labeled_human),
                len(labeled_human),
            ),
            "release_representation_may_postdate_cutoff": _count_and_percent(
                sum(
                    record["release_representation_may_postdate_cutoff"]
                    for record in labeled_human
                ),
                len(labeled_human),
            ),
        },
    }


def _release_github_labels(
    connection: sqlite3.Connection, artifact_ids: list[int]
) -> defaultdict[int, list[str]]:
    result: defaultdict[int, list[str]] = defaultdict(list)
    if not artifact_ids:
        return result
    placeholders = ",".join("?" for _ in artifact_ids)
    rows = connection.execute(
        f"""
        SELECT artifact_id, label_name
        FROM canonical_artifact_label
        WHERE artifact_id IN ({placeholders})
        ORDER BY artifact_id, label_name
        """,
        artifact_ids,
    )
    for row in rows:
        result[int(row["artifact_id"])].append(row["label_name"])
    return result


def _canonical_pr_files(
    connection: sqlite3.Connection, pull_request_ids: list[int]
) -> defaultdict[int, list[dict[str, Any]]]:
    result: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    if not pull_request_ids:
        return result
    placeholders = ",".join("?" for _ in pull_request_ids)
    rows = connection.execute(
        f"""
        SELECT pull_request_id, path, additions, deletions
        FROM canonical_pull_request_file
        WHERE pull_request_id IN ({placeholders}) AND cutoff_stable = 1
        ORDER BY pull_request_id, path
        """,
        pull_request_ids,
    )
    for row in rows:
        result[int(row["pull_request_id"])].append(
            {
                "path": row["path"],
                "additions": row["additions"],
                "deletions": row["deletions"],
            }
        )
    return result


def _base_commit_files(
    connection: sqlite3.Connection, pull_request_ids: list[int]
) -> defaultdict[int, list[dict[str, Any]]]:
    result: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    if not pull_request_ids:
        return result
    placeholders = ",".join("?" for _ in pull_request_ids)
    rows = connection.execute(
        f"""
        SELECT pc.pull_request_id, f.filename AS path,
               f.additions, f.deletions
        FROM canonical_pull_request_commit AS pc
        JOIN commit_file AS f ON f.commit_sha = pc.commit_sha
        WHERE pc.pull_request_id IN ({placeholders})
        ORDER BY pc.pull_request_id, f.filename
        """,
        pull_request_ids,
    )
    by_path: dict[tuple[int, str], dict[str, Any]] = {}
    for row in rows:
        pull_request_id = int(row["pull_request_id"])
        key = (pull_request_id, row["path"])
        value = by_path.setdefault(
            key,
            {"path": row["path"], "additions": 0, "deletions": 0},
        )
        value["additions"] += int(row["additions"] or 0)
        value["deletions"] += int(row["deletions"] or 0)
    for (pull_request_id, _), value in sorted(by_path.items()):
        result[pull_request_id].append(value)
    return result


def _sum_file_field(files: list[dict[str, Any]], field: str) -> int | None:
    if not files:
        return None
    return sum(int(file.get(field) or 0) for file in files)


def _manifest_input_sha256(record: dict[str, Any]) -> str:
    payload = json.dumps(
        record,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _load_labels(
    path: Path | list[Path],
    *,
    source_cutoffs: str | list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    labels = {}
    paths = [path] if isinstance(path, Path) else path
    if source_cutoffs is None:
        cutoffs: list[str | None] = [None] * len(paths)
    elif isinstance(source_cutoffs, str):
        cutoffs = [source_cutoffs] * len(paths)
    elif len(source_cutoffs) == 1:
        cutoffs = source_cutoffs * len(paths)
    elif len(source_cutoffs) == len(paths):
        cutoffs = source_cutoffs
    else:
        raise ValueError("label paths and source cutoffs must have equal lengths")
    for current_path, source_cutoff in zip(paths, cutoffs, strict=True):
        with current_path.open(encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                value = json.loads(line)
                source_id = value.get("source_id")
                if not isinstance(source_id, str):
                    raise ValueError(
                        f"{current_path}:{line_number} lacks source_id"
                    )
                if source_id in labels:
                    raise ValueError(
                        f"duplicate source_id {source_id} in {current_path}"
                    )
                value["_input_snapshot_cutoff"] = (
                    value.get("input_snapshot_cutoff") or source_cutoff
                )
                if source_cutoffs is not None and not value[
                    "_input_snapshot_cutoff"
                ]:
                    raise ValueError(
                        f"{current_path}:{line_number} lacks input cutoff"
                    )
                labels[source_id] = value
    return labels


def _period(record: dict[str, Any]) -> str:
    year = int(record["release_created_at"][:4])
    if year <= 2024:
        return "launch_through_2024"
    if year == 2025:
        return "2025"
    return "2026_through_cutoff"


def _multi_label_counts(
    records: list[dict[str, Any]], field: str, labels: frozenset[str]
) -> Counter[str]:
    counts = Counter(
        label
        for record in records
        for label in record["classification"][field]
    )
    return Counter({label: counts[label] for label in labels})


def _count_table(
    counts: Counter[str],
    denominator: int,
    *,
    labels: frozenset[str] | None = None,
) -> dict[str, dict[str, int | float]]:
    return {
        label: _count_and_percent(counts[label], denominator)
        for label in sorted(labels or frozenset(counts))
    }


def _count_and_percent(count: int, denominator: int) -> dict[str, int | float]:
    return {"count": count, "percent": _percent(count, denominator)}


def _percent(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 1) if denominator else 0.0


def _iso_time(value: str) -> str:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
