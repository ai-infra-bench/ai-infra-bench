"""Export a shareable, one-row-per-artifact RQ1 workbook.

This script is intentionally analysis-specific. It joins the canonical
2026-07-31 Release SQLite database, Release-aligned PR labels, and derived
Issue metrics without changing the frozen source data.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from itertools import chain
from pathlib import Path
from typing import Any

import xlsxwriter

REPOSITORY = "vllm-project/vllm"
RELEASE_TAG = "vllm-github-data-2026-07-31"
RELEASE_URL = (
    f"https://github.com/ai-infra-bench/ai-infra-bench/releases/tag/{RELEASE_TAG}"
)
SNAPSHOT_CUTOFF = "2026-07-31T23:59:59Z"
RELEASE_DATABASE_SHA256 = (
    "2ac86507a95f9b8785e6ce0bbf2745e3fbba67c747e37b54020a7e57ce80f8b5"
)
FORMAL_REVIEW_STATES = {"APPROVED", "COMMENTED", "CHANGES_REQUESTED"}
SNAPSHOT_COLLABORATOR_ROLES = {"triage", "write", "maintain", "admin"}


# Column order is the published sharing contract. Empty cells mean either
# not applicable or not observed; the accompanying state/availability fields
# disambiguate those cases.
FIELDS: list[tuple[str, str, str, str]] = [
    ("record_type", "Both", "记录类型：issue 或 pull_request。", "category"),
    ("source_id", "Both", "稳定的项目内记录标识。", "identifier"),
    ("number", "Both", "GitHub Issue/PR 编号。", "integer"),
    ("url", "Both", "公开 GitHub 页面链接。", "URL"),
    ("title", "Both", "截止快照中可见的标题。", "text"),
    ("author_login", "Both", "作者 GitHub login。", "login"),
    (
        "author_type",
        "Both",
        "GitHub actor type；仅 type=Bot 才按 Bot 处理。",
        "User/Bot/Organization/unknown",
    ),
    ("author_association", "Both", "GitHub author association。", "category"),
    (
        "author_group",
        "Both",
        "按严格 actor type 与 5 月 18 日快照协作者名单得到的作者组。",
        "category",
    ),
    (
        "include_in_human_analysis",
        "Both",
        "作者 actor type 为 User 时为 TRUE。",
        "boolean",
    ),
    ("created_at", "Both", "创建时间（UTC）。", "ISO-8601 UTC"),
    ("created_month", "Both", "创建月份。", "YYYY-MM"),
    (
        "reporting_period",
        "Both",
        "launch_through_2024、2025 或 2026_through_cutoff。",
        "category",
    ),
    ("state_at_cutoff", "Both", "2026-07-31 截止状态。", "category"),
    ("arrival_indicator", "Both", "每行恒为 1，用于按月汇总到达量。", "0/1"),
    ("closed_at", "Both", "截止日前最终关闭时间；开放记录为空。", "ISO-8601 UTC"),
    ("merged_at", "PR", "PR 合并时间。", "ISO-8601 UTC"),
    ("first_close_at", "Issue", "Issue 第一次 open→closed 时间。", "ISO-8601 UTC"),
    ("outcome_month", "Both", "关闭或合并结果发生月份。", "YYYY-MM"),
    (
        "closed_by_cutoff_indicator",
        "Both",
        "截止日已关闭（PR 包括 merged/closed-unmerged）。",
        "0/1",
    ),
    (
        "backlog_at_cutoff_indicator",
        "Both",
        "截止日仍 open，因而进入截止日 backlog。",
        "0/1",
    ),
    (
        "time_to_first_close_days",
        "Issue",
        "从创建到第一次关闭的墙钟天数。",
        "days",
    ),
    ("time_to_merge_days", "PR", "从创建到合并的墙钟天数。", "days"),
    (
        "time_to_pr_close_days",
        "PR",
        "从创建到 PR 最终关闭的墙钟天数。",
        "days",
    ),
    (
        "observation_days_to_cutoff",
        "Both",
        "从创建到冻结截止日的观察天数。",
        "days",
    ),
    (
        "close_analysis_state",
        "Both",
        "event 或 right_censored。",
        "category",
    ),
    (
        "merge_analysis_state",
        "PR",
        "event、competing_event 或 right_censored。",
        "category",
    ),
    (
        "close_transition_count",
        "Issue",
        "观察期内 open→closed 转换次数。",
        "count",
    ),
    (
        "reopen_transition_count",
        "Issue",
        "观察期内 closed→open 转换次数。",
        "count",
    ),
    (
        "lifecycle_events_json",
        "Issue",
        "保留关闭/重开序列，支持重建月末 backlog。",
        "JSON",
    ),
    (
        "conversation_comments_at_cutoff",
        "Both",
        "截止日 conversation comments 数。",
        "count",
    ),
    (
        "qualifying_human_comments",
        "Issue",
        "排除作者和 Bot 后的人类评论数。",
        "count",
    ),
    (
        "qualifying_snapshot_collaborator_comments",
        "Issue",
        "快照协作者名单中的合格非作者评论数。",
        "count",
    ),
    (
        "first_human_response_at",
        "Issue",
        "第一条合格人类响应时间。",
        "ISO-8601 UTC",
    ),
    (
        "time_to_first_human_response_hours",
        "Issue",
        "到第一条合格人类响应的墙钟小时数。",
        "hours",
    ),
    (
        "first_human_response_state",
        "Issue",
        "event、closed_without_response 或 open_right_censored。",
        "category",
    ),
    (
        "first_snapshot_collaborator_response_at",
        "Issue",
        "第一条快照协作者响应时间。",
        "ISO-8601 UTC",
    ),
    (
        "time_to_first_snapshot_collaborator_response_hours",
        "Issue",
        "到第一条快照协作者响应的墙钟小时数。",
        "hours",
    ),
    (
        "first_snapshot_collaborator_response_state",
        "Issue",
        "event、closed_without_response 或 open_right_censored。",
        "category",
    ),
    (
        "human_annotated_substantive_response_at",
        "Issue",
        "人工标注的第一条实质响应；当前尚未开展，保持空值。",
        "ISO-8601 UTC",
    ),
    (
        "time_to_human_annotated_substantive_response_hours",
        "Issue",
        "到人工标注实质响应的时间；当前保持空值。",
        "hours",
    ),
    (
        "substantive_annotation_status",
        "Issue",
        "当前统一为 not_annotated。",
        "category",
    ),
    (
        "exploratory_substantive_text_rule_v1_at",
        "Issue",
        "确定性文本规则的探索结果，不是人工标注结论。",
        "ISO-8601 UTC",
    ),
    (
        "time_to_exploratory_substantive_text_rule_v1_hours",
        "Issue",
        "到探索性文本规则命中响应的小时数。",
        "hours",
    ),
    (
        "exploratory_substantive_text_rule_v1_state",
        "Issue",
        "探索性文本规则的事件/删失状态。",
        "category",
    ),
    (
        "first_human_formal_review_at",
        "PR",
        "第一条非作者、非 Bot、GitHub User 的正式 review 时间。",
        "ISO-8601 UTC",
    ),
    (
        "time_to_first_human_formal_review_hours",
        "PR",
        "到第一条合格正式 review 的墙钟小时数。",
        "hours",
    ),
    (
        "first_human_formal_review_state",
        "PR",
        "event、closed_without_review 或 open_right_censored。",
        "category",
    ),
    (
        "first_snapshot_collaborator_formal_review_at",
        "PR",
        "第一条由快照协作者提交的合格正式 review。",
        "ISO-8601 UTC",
    ),
    (
        "time_to_first_snapshot_collaborator_formal_review_hours",
        "PR",
        "到第一条快照协作者正式 review 的小时数。",
        "hours",
    ),
    (
        "first_snapshot_collaborator_formal_review_state",
        "PR",
        "event、closed_without_review 或 open_right_censored。",
        "category",
    ),
    (
        "qualifying_human_formal_review_submissions",
        "PR",
        "APPROVED/COMMENTED/CHANGES_REQUESTED 合格人类 review 数。",
        "count",
    ),
    (
        "snapshot_collaborator_formal_review_submissions",
        "PR",
        "其中由快照协作者提交的 review 数。",
        "count",
    ),
    (
        "unique_human_formal_reviewers",
        "PR",
        "合格正式 reviewers 去重人数。",
        "count",
    ),
    (
        "human_formal_reviewer_logins",
        "PR",
        "按 login 排序、分号分隔的 reviewer 列表。",
        "list",
    ),
    (
        "requested_changes_review_count",
        "PR",
        "合格 CHANGES_REQUESTED reviews 数。",
        "count",
    ),
    (
        "any_requested_changes",
        "PR",
        "是否出现至少一次合格 CHANGES_REQUESTED review。",
        "boolean",
    ),
    (
        "inline_review_comments_total",
        "PR",
        "全部行级 review comments。",
        "count",
    ),
    (
        "inline_review_comments_human",
        "PR",
        "GitHub actor type=User 的行级 review comments。",
        "count",
    ),
    (
        "inline_review_comments_bot",
        "PR",
        "GitHub actor type=Bot 的行级 review comments。",
        "count",
    ),
    (
        "inline_review_comments_unknown",
        "PR",
        "actor type 缺失或非 User/Bot 的行级 review comments。",
        "count",
    ),
    (
        "review_rounds_proxy",
        "PR",
        "被作者 revision 分隔的合格 review activity blocks。",
        "count",
    ),
    (
        "review_rounds_is_timing_proxy",
        "PR",
        "TRUE 表示 commit 时间只是 push timing 的代理。",
        "boolean",
    ),
    (
        "author_revision_timestamps_observed",
        "PR",
        "可归于 PR 作者的 commit 时间戳数。",
        "count",
    ),
    ("commits_observed", "PR", "Release 中观察到的 PR commits 数。", "count"),
    (
        "churn_data_available",
        "PR",
        "是否存在 canonical PR file rows；FALSE 时 churn 留空。",
        "boolean",
    ),
    ("additions", "PR", "文件级 additions 合计。", "lines"),
    ("deletions", "PR", "文件级 deletions 合计。", "lines"),
    ("changed_files", "PR", "观察到的 changed file paths 数。", "count"),
    (
        "files_cutoff_stable",
        "PR",
        "Release 对该 PR 文件表示的 cutoff-stability 标记。",
        "boolean",
    ),
    (
        "workload_category",
        "Both",
        "工作类型标签；当前研究尚未开展，保持空值。",
        "multi-label",
    ),
    (
        "workload_label_status",
        "Both",
        "当前统一为 not_labeled。",
        "category",
    ),
    ("subsystems", "PR", "模型辅助的多标签子系统分类。", "list"),
    ("subsystem_confidence", "PR", "子系统标签置信度。", "low/medium/high"),
    (
        "accelerator_scope",
        "PR",
        "agnostic/specific/cross_backend/unknown。",
        "category",
    ),
    ("accelerators", "PR", "模型辅助的加速器多标签分类。", "list"),
    ("accelerator_confidence", "PR", "加速器标签置信度。", "low/medium/high"),
    ("semantic_label_status", "PR", "Release 对齐的模型标签状态。", "category"),
    ("semantic_taxonomy_version", "PR", "标签 taxonomy 版本。", "version"),
    ("semantic_prompt_version", "PR", "模型标注 prompt 版本。", "version"),
    ("semantic_model", "PR", "解析后的模型版本。", "model"),
    (
        "semantic_label_input_cutoff",
        "PR",
        "标注输入快照截止时间；可能晚于 canonical cutoff。",
        "ISO-8601 UTC",
    ),
    ("semantic_evidence", "PR", "分隔后的模型证据片段。", "text"),
    ("semantic_rationale", "PR", "模型分类理由；不是人工真值。", "text"),
    ("github_labels", "Both", "截止快照中的 GitHub repository labels。", "list"),
    ("source_layer", "Both", "Release canonical source layer。", "base/delta"),
    (
        "representation_may_postdate_cutoff",
        "Both",
        "标题/正文表示可能包含截止日后编辑。",
        "boolean",
    ),
]

FIELD_NAMES = [field[0] for field in FIELDS]


def parse_time(value: str) -> datetime:
    """Parse a GitHub-style ISO timestamp."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def iso_time(value: str | None) -> str | None:
    """Normalize a Release timestamp to explicit UTC ISO-8601."""
    if not value:
        return None
    return parse_time(value).astimezone(UTC).isoformat().replace("+00:00", "Z")


def elapsed(start: str, end: str | None, *, hours: bool = False) -> float | None:
    """Return rounded elapsed wall-clock hours or days."""
    if not end:
        return None
    seconds = (parse_time(end) - parse_time(start)).total_seconds()
    if seconds < 0:
        raise ValueError(f"event precedes creation: {start} -> {end}")
    divisor = 3600 if hours else 86400
    return round(seconds / divisor, 3)


def period(created_at: str) -> str:
    """Map creation time to the frozen reporting windows."""
    year = parse_time(created_at).year
    if year <= 2024:
        return "launch_through_2024"
    if year == 2025:
        return "2025"
    return "2026_through_cutoff"


def actor_type_maps(
    connection: sqlite3.Connection,
) -> tuple[dict[int, str], dict[str, str]]:
    """Recover strict GitHub actor types from base and delta layers."""
    by_id: dict[int, str] = {}
    by_login: dict[str, str] = {}

    def remember(actor: dict[str, Any]) -> None:
        login = actor.get("login")
        actor_type = actor.get("type") or actor.get("__typename")
        actor_id = actor.get("databaseId") or actor.get("id")
        if actor_type not in {"User", "Bot", "Organization"}:
            return
        if isinstance(actor_id, int):
            by_id[actor_id] = actor_type
        if isinstance(login, str) and login:
            by_login[login.casefold()] = actor_type

    for row in connection.execute("SELECT id, login, type FROM user"):
        remember(dict(row))

    raw_tables = [
        row[0]
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name LIKE 'delta_%_raw'
            ORDER BY name
            """
        )
    ]
    for table in raw_tables:
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if "raw_json" not in columns:
            continue
        for row in connection.execute(f"SELECT raw_json FROM {table}"):
            if not row[0]:
                continue
            value = json.loads(row[0])
            stack = [value]
            while stack:
                item = stack.pop()
                if isinstance(item, dict):
                    if "login" in item:
                        remember(item)
                    stack.extend(item.values())
                elif isinstance(item, list):
                    stack.extend(item)
    return by_id, by_login


def actor_type(
    actor_id: int | None,
    login: str | None,
    by_id: dict[int, str],
    by_login: dict[str, str],
) -> str:
    """Resolve an actor type without name-based Bot inference."""
    if actor_id is not None and int(actor_id) in by_id:
        return by_id[int(actor_id)]
    if login and login.casefold() in by_login:
        return by_login[login.casefold()]
    return "unknown"


def snapshot_collaborators(
    connection: sqlite3.Connection,
) -> tuple[set[int], set[str]]:
    """Return the May 18 snapshot collaborator roster."""
    ids: set[int] = set()
    logins: set[str] = set()
    rows = connection.execute(
        """
        SELECT c.user_id, u.login, lower(c.role_name) AS role_name
        FROM repo_collaborator AS c
        JOIN user AS u ON u.id = c.user_id
        WHERE coalesce(c._fivetran_deleted, 0) = 0
        """
    )
    for row in rows:
        if row["role_name"] not in SNAPSHOT_COLLABORATOR_ROLES:
            continue
        ids.add(int(row["user_id"]))
        if row["login"]:
            logins.add(row["login"].casefold())
    return ids, logins


def is_snapshot_collaborator(
    actor_id: int | None,
    login: str | None,
    ids: set[int],
    logins: set[str],
) -> bool:
    """Test membership in the frozen snapshot roster."""
    return bool(
        (actor_id is not None and int(actor_id) in ids)
        or (login and login.casefold() in logins)
    )


def base_artifacts(connection: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    """Load canonical artifact identity and lifecycle fields."""
    result = {}
    rows = connection.execute(
        """
        SELECT database_id, number, artifact_type, repository, author_id,
               author_login, author_association, title, created_at,
               state_at_cutoff, closed_at_cutoff, merged_at_cutoff,
               source_layer, representation_may_postdate_cutoff
        FROM canonical_artifact
        ORDER BY artifact_type, number
        """
    )
    for row in rows:
        value = dict(row)
        for field in ("created_at", "closed_at_cutoff", "merged_at_cutoff"):
            value[field] = iso_time(value[field])
        result[int(row["database_id"])] = value
    return result


def github_labels(connection: sqlite3.Connection) -> dict[int, str]:
    """Return sorted repository labels for every artifact."""
    values: dict[int, list[str]] = defaultdict(list)
    for row in connection.execute(
        """
        SELECT artifact_id, label_name
        FROM canonical_artifact_label
        ORDER BY artifact_id, label_name COLLATE NOCASE
        """
    ):
        values[int(row["artifact_id"])].append(row["label_name"])
    return {key: "; ".join(items) for key, items in values.items()}


def load_jsonl_by_number(path: Path) -> dict[int, dict[str, Any]]:
    """Load a JSONL artifact keyed by GitHub number."""
    result = {}
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            value = json.loads(line)
            number = int(value["number"])
            if number in result:
                raise ValueError(f"duplicate number {number} at line {line_number}")
            result[number] = value
    return result


def author_group(
    actor_kind: str,
    actor_id: int | None,
    login: str | None,
    collaborator_ids: set[int],
    collaborator_logins: set[str],
) -> str:
    """Assign a transparent author group."""
    if actor_kind == "Bot":
        return "bot"
    if actor_kind != "User":
        return "unknown"
    if is_snapshot_collaborator(
        actor_id,
        login,
        collaborator_ids,
        collaborator_logins,
    ):
        return "snapshot_collaborator"
    return "external"


def empty_record() -> dict[str, Any]:
    """Create a record with the complete sharing schema."""
    return dict.fromkeys(FIELD_NAMES)


def issue_records(
    artifacts: dict[int, dict[str, Any]],
    issue_metrics: dict[int, dict[str, Any]],
    labels: dict[int, str],
    actor_types_by_id: dict[int, str],
    actor_types_by_login: dict[str, str],
    collaborator_ids: set[int],
    collaborator_logins: set[str],
) -> Iterator[dict[str, Any]]:
    """Yield one sharing row per canonical Issue."""
    issue_artifacts = sorted(
        (row for row in artifacts.values() if row["artifact_type"] == "Issue"),
        key=lambda row: int(row["number"]),
    )
    for artifact in issue_artifacts:
        number = int(artifact["number"])
        metric = issue_metrics[number]
        created_at = artifact["created_at"]
        closed_at = artifact["closed_at_cutoff"]
        status = metric["status_at_cutoff"]
        author_id = artifact["author_id"]
        login = artifact["author_login"]
        kind = actor_type(
            author_id,
            login,
            actor_types_by_id,
            actor_types_by_login,
        )
        first_human_at = metric.get("first_human_response_at")
        row = empty_record()
        row.update(
            {
                "record_type": "issue",
                "source_id": metric["source_id"],
                "number": number,
                "url": f"https://github.com/{REPOSITORY}/issues/{number}",
                "title": artifact["title"],
                "author_login": login,
                "author_type": kind,
                "author_association": artifact["author_association"] or "NONE",
                "author_group": author_group(
                    kind,
                    author_id,
                    login,
                    collaborator_ids,
                    collaborator_logins,
                ),
                "include_in_human_analysis": kind == "User",
                "created_at": created_at,
                "created_month": created_at[:7],
                "reporting_period": period(created_at),
                "state_at_cutoff": status,
                "arrival_indicator": 1,
                "closed_at": closed_at,
                "first_close_at": metric.get("first_close_at"),
                "outcome_month": (
                    metric["first_close_at"][:7]
                    if metric.get("first_close_at")
                    else None
                ),
                "closed_by_cutoff_indicator": int(status == "closed"),
                "backlog_at_cutoff_indicator": int(status == "open"),
                "time_to_first_close_days": metric.get("time_to_first_close_days"),
                "observation_days_to_cutoff": metric.get("observation_days"),
                "close_analysis_state": metric.get("close_analysis_state"),
                "close_transition_count": metric.get("close_transitions"),
                "reopen_transition_count": metric.get("reopen_transitions"),
                "lifecycle_events_json": json.dumps(
                    metric.get("lifecycle_events", []),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "conversation_comments_at_cutoff": metric.get(
                    "conversation_comments_at_cutoff"
                ),
                "qualifying_human_comments": metric.get("qualifying_human_comments"),
                "qualifying_snapshot_collaborator_comments": metric.get(
                    "qualifying_snapshot_collaborator_comments"
                ),
                "first_human_response_at": first_human_at,
                "time_to_first_human_response_hours": metric.get(
                    "time_to_first_human_response_hours"
                ),
                "first_human_response_state": (
                    "event"
                    if first_human_at
                    else (
                        "closed_without_response"
                        if status == "closed"
                        else "open_right_censored"
                    )
                ),
                "first_snapshot_collaborator_response_at": metric.get(
                    "first_snapshot_collaborator_response_at"
                ),
                "time_to_first_snapshot_collaborator_response_hours": metric.get(
                    "time_to_first_snapshot_collaborator_response_hours"
                ),
                "first_snapshot_collaborator_response_state": metric.get(
                    "first_snapshot_collaborator_response_state"
                ),
                "substantive_annotation_status": "not_annotated",
                "exploratory_substantive_text_rule_v1_at": metric.get(
                    "first_substantive_response_at"
                ),
                "time_to_exploratory_substantive_text_rule_v1_hours": metric.get(
                    "time_to_first_substantive_response_hours"
                ),
                "exploratory_substantive_text_rule_v1_state": metric.get(
                    "first_substantive_response_state"
                ),
                "workload_label_status": "not_labeled",
                "github_labels": labels.get(int(artifact["database_id"]), ""),
                "source_layer": artifact["source_layer"],
                "representation_may_postdate_cutoff": bool(
                    artifact["representation_may_postdate_cutoff"]
                ),
            }
        )
        yield row


def pr_conversation_comment_counts(
    connection: sqlite3.Connection,
) -> dict[int, int]:
    """Count PR conversation comments."""
    return {
        int(row["artifact_id"]): int(row["comment_count"])
        for row in connection.execute(
            """
            SELECT c.artifact_id, count(*) AS comment_count
            FROM canonical_issue_comment AS c
            JOIN canonical_artifact AS a ON a.database_id = c.artifact_id
            WHERE a.artifact_type = 'PullRequest'
            GROUP BY c.artifact_id
            """
        )
    }


def pr_identity_maps(
    connection: sqlite3.Connection,
) -> tuple[dict[int, int], dict[int, int]]:
    """Map canonical PR table IDs to canonical artifact IDs and back."""
    pr_to_artifact = {}
    artifact_to_pr = {}
    for row in connection.execute(
        "SELECT database_id, artifact_id FROM canonical_pull_request"
    ):
        pr_id = int(row["database_id"])
        artifact_id = int(row["artifact_id"])
        pr_to_artifact[pr_id] = artifact_id
        artifact_to_pr[artifact_id] = pr_id
    return pr_to_artifact, artifact_to_pr


def pr_review_data(
    connection: sqlite3.Connection,
    artifacts: dict[int, dict[str, Any]],
    pr_to_artifact: dict[int, int],
    actor_types_by_id: dict[int, str],
    actor_types_by_login: dict[str, str],
    collaborator_ids: set[int],
    collaborator_logins: set[str],
) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Derive qualifying per-PR review events and monthly demand inputs."""
    reviews: dict[int, list[dict[str, Any]]] = defaultdict(list)
    monthly_reviewers: dict[str, set[str]] = defaultdict(set)
    monthly_snapshot_reviewers: dict[str, set[str]] = defaultdict(set)
    monthly_reviewed_prs: dict[str, set[int]] = defaultdict(set)
    monthly_submissions: Counter[str] = Counter()
    rows = connection.execute(
        """
        SELECT pull_request_id, author_id, author_login, submitted_at,
               upper(state) AS state
        FROM canonical_pull_request_review
        WHERE submitted_at IS NOT NULL
        ORDER BY pull_request_id, submitted_at, database_id
        """
    )
    for row in rows:
        pr_id = int(row["pull_request_id"])
        artifact_id = pr_to_artifact.get(pr_id)
        artifact = artifacts.get(artifact_id) if artifact_id is not None else None
        if artifact is None or artifact["artifact_type"] != "PullRequest":
            continue
        if row["state"] not in FORMAL_REVIEW_STATES:
            continue
        login = row["author_login"]
        reviewer_id = row["author_id"]
        if (
            actor_type(
                reviewer_id,
                login,
                actor_types_by_id,
                actor_types_by_login,
            )
            != "User"
        ):
            continue
        same_id = (
            reviewer_id is not None
            and artifact["author_id"] is not None
            and int(reviewer_id) == int(artifact["author_id"])
        )
        same_login = bool(
            login
            and artifact["author_login"]
            and login.casefold() == artifact["author_login"].casefold()
        )
        if same_id or same_login:
            continue
        snapshot = is_snapshot_collaborator(
            reviewer_id,
            login,
            collaborator_ids,
            collaborator_logins,
        )
        submitted_at = iso_time(row["submitted_at"])
        if submitted_at is None:
            continue
        event = {
            "submitted_at": submitted_at,
            "state": row["state"],
            "login": login,
            "snapshot_collaborator": snapshot,
        }
        reviews[pr_id].append(event)
        author_kind = actor_type(
            artifact["author_id"],
            artifact["author_login"],
            actor_types_by_id,
            actor_types_by_login,
        )
        if author_kind == "User":
            month = submitted_at[:7]
            if login:
                monthly_reviewers[month].add(login)
                if snapshot:
                    monthly_snapshot_reviewers[month].add(login)
            monthly_reviewed_prs[month].add(pr_id)
            monthly_submissions[month] += 1

    derived: dict[int, dict[str, Any]] = {}
    for pr_id, events in reviews.items():
        reviewer_logins = sorted(
            {event["login"] for event in events if event["login"]},
            key=str.casefold,
        )
        snapshot_events = [event for event in events if event["snapshot_collaborator"]]
        derived[pr_id] = {
            "events": events,
            "first_human_review_at": events[0]["submitted_at"],
            "first_snapshot_review_at": (
                snapshot_events[0]["submitted_at"] if snapshot_events else None
            ),
            "human_submissions": len(events),
            "snapshot_submissions": len(snapshot_events),
            "reviewer_logins": reviewer_logins,
            "requested_changes": sum(
                event["state"] == "CHANGES_REQUESTED" for event in events
            ),
        }
    monthly = {
        "reviewers": monthly_reviewers,
        "snapshot_reviewers": monthly_snapshot_reviewers,
        "reviewed_prs": monthly_reviewed_prs,
        "submissions": monthly_submissions,
    }
    return derived, monthly


def pr_inline_comment_counts(
    connection: sqlite3.Connection,
    actor_types_by_id: dict[int, str],
    actor_types_by_login: dict[str, str],
) -> dict[int, Counter[str]]:
    """Count line-level review comments by strict actor type."""
    result: dict[int, Counter[str]] = defaultdict(Counter)
    rows = connection.execute(
        """
        SELECT pull_request_id, author_id, author_login
        FROM canonical_review_comment
        WHERE pull_request_id IS NOT NULL
        """
    )
    for row in rows:
        pr_id = int(row["pull_request_id"])
        kind = actor_type(
            row["author_id"],
            row["author_login"],
            actor_types_by_id,
            actor_types_by_login,
        )
        result[pr_id]["total"] += 1
        result[pr_id][kind.lower() if kind in {"User", "Bot"} else "unknown"] += 1
    return result


def pr_commit_data(
    connection: sqlite3.Connection,
    artifacts: dict[int, dict[str, Any]],
    pr_to_artifact: dict[int, int],
) -> dict[int, dict[str, Any]]:
    """Return observed commit counts and author revision time proxies."""
    result: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "author_revision_times": []}
    )
    rows = connection.execute(
        """
        SELECT pull_request_id, committed_at, authored_at, author_login
        FROM canonical_pull_request_commit
        ORDER BY pull_request_id, coalesce(committed_at, authored_at), commit_sha
        """
    )
    for row in rows:
        pr_id = int(row["pull_request_id"])
        result[pr_id]["count"] += 1
        artifact_id = pr_to_artifact.get(pr_id)
        artifact = artifacts.get(artifact_id) if artifact_id is not None else None
        if artifact is None:
            continue
        login = row["author_login"]
        author_login = artifact["author_login"]
        timestamp = row["committed_at"] or row["authored_at"]
        if (
            timestamp
            and login
            and author_login
            and login.casefold() == author_login.casefold()
        ):
            result[pr_id]["author_revision_times"].append(timestamp)
    return result


def review_rounds(
    events: list[dict[str, Any]], author_revision_times: list[str]
) -> int:
    """Count review blocks separated by an observed author revision."""
    if not events:
        return 0
    review_times = [parse_time(event["submitted_at"]) for event in events]
    commits = sorted(parse_time(value) for value in author_revision_times)
    rounds = 1
    previous_review = review_times[0]
    for current_review in review_times[1:]:
        if any(previous_review < commit <= current_review for commit in commits):
            rounds += 1
        previous_review = current_review
    return rounds


def pr_churn_data(connection: sqlite3.Connection) -> dict[int, dict[str, int]]:
    """Aggregate file-level churn where canonical file rows exist."""
    result = {}
    rows = connection.execute(
        """
        SELECT pull_request_id, count(*) AS changed_files,
               sum(additions) AS additions, sum(deletions) AS deletions
        FROM canonical_pull_request_file
        GROUP BY pull_request_id
        """
    )
    for row in rows:
        result[int(row["pull_request_id"])] = {
            "changed_files": int(row["changed_files"]),
            "additions": int(row["additions"]),
            "deletions": int(row["deletions"]),
        }
    return result


def pr_file_stability(connection: sqlite3.Connection) -> dict[int, bool]:
    """Load Release file-stability flags."""
    return {
        int(row["database_id"]): bool(row["files_cutoff_stable"])
        for row in connection.execute(
            "SELECT database_id, files_cutoff_stable FROM canonical_pull_request"
        )
    }


def pr_records(
    artifacts: dict[int, dict[str, Any]],
    artifact_to_pr: dict[int, int],
    semantic_labels: dict[int, dict[str, Any]],
    github_label_values: dict[int, str],
    conversation_counts: dict[int, int],
    reviews: dict[int, dict[str, Any]],
    inline_comments: dict[int, Counter[str]],
    commits: dict[int, dict[str, Any]],
    churn: dict[int, dict[str, int]],
    file_stability: dict[int, bool],
    actor_types_by_id: dict[int, str],
    actor_types_by_login: dict[str, str],
    collaborator_ids: set[int],
    collaborator_logins: set[str],
) -> Iterator[dict[str, Any]]:
    """Yield one sharing row per canonical PR."""
    pr_artifacts = sorted(
        (
            (artifact_id, row)
            for artifact_id, row in artifacts.items()
            if row["artifact_type"] == "PullRequest"
        ),
        key=lambda item: int(item[1]["number"]),
    )
    for artifact_id, artifact in pr_artifacts:
        pr_id = artifact_to_pr[artifact_id]
        number = int(artifact["number"])
        label = semantic_labels[number]
        classification = label["classification"]
        provenance = label.get("label_provenance") or {}
        model = provenance.get("model") or {}
        review = reviews.get(
            pr_id,
            {
                "events": [],
                "first_human_review_at": None,
                "first_snapshot_review_at": None,
                "human_submissions": 0,
                "snapshot_submissions": 0,
                "reviewer_logins": [],
                "requested_changes": 0,
            },
        )
        comment_counts = inline_comments[pr_id]
        commit = commits[pr_id]
        churn_value = churn.get(pr_id)
        created_at = artifact["created_at"]
        closed_at = artifact["closed_at_cutoff"]
        merged_at = artifact["merged_at_cutoff"]
        if merged_at:
            status = "merged"
            merge_state = "event"
        elif closed_at:
            status = "closed_unmerged"
            merge_state = "competing_event"
        else:
            status = "open"
            merge_state = "right_censored"
        no_review_state = (
            "open_right_censored" if status == "open" else "closed_without_review"
        )
        first_human_review = review["first_human_review_at"]
        first_snapshot_review = review["first_snapshot_review_at"]
        author_id = artifact["author_id"]
        login = artifact["author_login"]
        kind = actor_type(
            author_id,
            login,
            actor_types_by_id,
            actor_types_by_login,
        )
        outcome = merged_at or closed_at
        row = empty_record()
        row.update(
            {
                "record_type": "pull_request",
                "source_id": label["source_id"],
                "number": number,
                "url": f"https://github.com/{REPOSITORY}/pull/{number}",
                "title": artifact["title"],
                "author_login": login,
                "author_type": kind,
                "author_association": artifact["author_association"] or "NONE",
                "author_group": author_group(
                    kind,
                    author_id,
                    login,
                    collaborator_ids,
                    collaborator_logins,
                ),
                "include_in_human_analysis": kind == "User",
                "created_at": created_at,
                "created_month": created_at[:7],
                "reporting_period": period(created_at),
                "state_at_cutoff": status,
                "arrival_indicator": 1,
                "closed_at": closed_at,
                "merged_at": merged_at,
                "outcome_month": outcome[:7] if outcome else None,
                "closed_by_cutoff_indicator": int(status != "open"),
                "backlog_at_cutoff_indicator": int(status == "open"),
                "time_to_merge_days": elapsed(created_at, merged_at),
                "time_to_pr_close_days": elapsed(created_at, closed_at),
                "observation_days_to_cutoff": elapsed(created_at, SNAPSHOT_CUTOFF),
                "close_analysis_state": ("event" if closed_at else "right_censored"),
                "merge_analysis_state": merge_state,
                "conversation_comments_at_cutoff": conversation_counts.get(
                    artifact_id, 0
                ),
                "first_human_formal_review_at": first_human_review,
                "time_to_first_human_formal_review_hours": elapsed(
                    created_at, first_human_review, hours=True
                ),
                "first_human_formal_review_state": (
                    "event" if first_human_review else no_review_state
                ),
                "first_snapshot_collaborator_formal_review_at": (first_snapshot_review),
                "time_to_first_snapshot_collaborator_formal_review_hours": elapsed(
                    created_at, first_snapshot_review, hours=True
                ),
                "first_snapshot_collaborator_formal_review_state": (
                    "event" if first_snapshot_review else no_review_state
                ),
                "qualifying_human_formal_review_submissions": review[
                    "human_submissions"
                ],
                "snapshot_collaborator_formal_review_submissions": review[
                    "snapshot_submissions"
                ],
                "unique_human_formal_reviewers": len(review["reviewer_logins"]),
                "human_formal_reviewer_logins": "; ".join(review["reviewer_logins"]),
                "requested_changes_review_count": review["requested_changes"],
                "any_requested_changes": bool(review["requested_changes"]),
                "inline_review_comments_total": comment_counts["total"],
                "inline_review_comments_human": comment_counts["user"],
                "inline_review_comments_bot": comment_counts["bot"],
                "inline_review_comments_unknown": comment_counts["unknown"],
                "review_rounds_proxy": review_rounds(
                    review["events"], commit["author_revision_times"]
                ),
                "review_rounds_is_timing_proxy": bool(review["events"]),
                "author_revision_timestamps_observed": len(
                    commit["author_revision_times"]
                ),
                "commits_observed": commit["count"],
                "churn_data_available": churn_value is not None,
                "additions": (
                    churn_value["additions"] if churn_value is not None else None
                ),
                "deletions": (
                    churn_value["deletions"] if churn_value is not None else None
                ),
                "changed_files": (
                    churn_value["changed_files"] if churn_value is not None else None
                ),
                "files_cutoff_stable": file_stability[pr_id],
                "workload_label_status": "not_labeled",
                "subsystems": "; ".join(classification["subsystems"]),
                "subsystem_confidence": classification["subsystem_confidence"],
                "accelerator_scope": classification["accelerator_scope"],
                "accelerators": "; ".join(classification["accelerators"]),
                "accelerator_confidence": classification["accelerator_confidence"],
                "semantic_label_status": label["label_status"],
                "semantic_taxonomy_version": provenance.get("taxonomy_version"),
                "semantic_prompt_version": provenance.get("prompt_version"),
                "semantic_model": model.get("resolved") or model.get("requested"),
                "semantic_label_input_cutoff": provenance.get("input_snapshot_cutoff"),
                "semantic_evidence": " | ".join(classification["evidence"]),
                "semantic_rationale": classification["rationale"],
                "github_labels": github_label_values.get(artifact_id, ""),
                "source_layer": artifact["source_layer"],
                "representation_may_postdate_cutoff": bool(
                    artifact["representation_may_postdate_cutoff"]
                ),
            }
        )
        yield row


def monthly_context(
    issue_summary_path: Path,
    artifacts: dict[int, dict[str, Any]],
    actor_types_by_id: dict[int, str],
    actor_types_by_login: dict[str, str],
    review_monthly: dict[str, dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Build a separate monthly numerator/denominator sharing sheet."""
    issue_summary = json.loads(issue_summary_path.read_text(encoding="utf-8"))
    issue_flow = issue_summary["monthly_issue_flow"]
    pr_arrivals: Counter[str] = Counter()
    pr_merges: Counter[str] = Counter()
    for artifact in artifacts.values():
        if artifact["artifact_type"] != "PullRequest":
            continue
        if (
            actor_type(
                artifact["author_id"],
                artifact["author_login"],
                actor_types_by_id,
                actor_types_by_login,
            )
            != "User"
        ):
            continue
        pr_arrivals[artifact["created_at"][:7]] += 1
        if artifact["merged_at_cutoff"]:
            pr_merges[artifact["merged_at_cutoff"][:7]] += 1

    columns = [
        "record_type",
        "month",
        "new_human_records",
        "close_or_merge_events",
        "end_backlog",
        "active_snapshot_collaborator_responders_or_reviewers",
        "active_human_reviewers",
        "records_receiving_formal_review",
        "formal_review_submissions",
        "new_records_per_active_snapshot_collaborator",
        "new_prs_per_active_human_reviewer",
        "complete_month",
    ]
    rows = []
    for month, values in sorted(issue_flow.items()):
        rows.append(
            {
                "record_type": "issue",
                "month": month,
                "new_human_records": values["new_human_issues"],
                "close_or_merge_events": values["close_transitions"],
                "end_backlog": values["end_backlog"],
                "active_snapshot_collaborator_responders_or_reviewers": values[
                    "active_issue_snapshot_collaborator_responders"
                ],
                "new_records_per_active_snapshot_collaborator": values[
                    "new_issues_per_active_issue_responder"
                ],
                "complete_month": values["complete_month"],
            }
        )
    review_months = (
        set(pr_arrivals)
        | set(pr_merges)
        | set(review_monthly["reviewers"])
        | set(review_monthly["snapshot_reviewers"])
    )
    for month in sorted(review_months):
        human_reviewers = len(review_monthly["reviewers"][month])
        snapshot_reviewers = len(review_monthly["snapshot_reviewers"][month])
        arrivals = pr_arrivals[month]
        rows.append(
            {
                "record_type": "pull_request",
                "month": month,
                "new_human_records": arrivals,
                "close_or_merge_events": pr_merges[month],
                "active_snapshot_collaborator_responders_or_reviewers": (
                    snapshot_reviewers
                ),
                "active_human_reviewers": human_reviewers,
                "records_receiving_formal_review": len(
                    review_monthly["reviewed_prs"][month]
                ),
                "formal_review_submissions": review_monthly["submissions"][month],
                "new_records_per_active_snapshot_collaborator": (
                    round(arrivals / snapshot_reviewers, 2)
                    if snapshot_reviewers
                    else None
                ),
                "new_prs_per_active_human_reviewer": (
                    round(arrivals / human_reviewers, 2) if human_reviewers else None
                ),
                "complete_month": True,
            }
        )
    rows.sort(key=lambda row: (row["month"], row["record_type"]))
    return columns, rows


def write_cell(
    worksheet: Any,
    row: int,
    column: int,
    value: Any,
    text_format: Any | None = None,
) -> None:
    """Write typed cells while preventing formula interpretation."""
    if value is None:
        return
    if isinstance(value, bool):
        worksheet.write_boolean(row, column, value)
    elif isinstance(value, (int, float)):
        worksheet.write_number(row, column, value)
    else:
        text = str(value)
        if len(text) > 32760:
            text = text[:32745] + " [truncated]"
        worksheet.write_string(row, column, text, text_format)


def write_workbook(
    output: Path,
    csv_output: Path,
    records: Iterable[dict[str, Any]],
    monthly_columns: list[str],
    monthly_rows: list[dict[str, Any]],
    *,
    expected_issues: int,
    expected_prs: int,
) -> dict[str, Any]:
    """Write the formatted workbook and matching gzipped CSV."""
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(
        output,
        {"constant_memory": True, "use_zip64": True, "strings_to_urls": False},
    )
    header_format = workbook.add_format(
        {
            "bold": True,
            "font_color": "white",
            "bg_color": "#1F4E78",
            "border": 1,
            "text_wrap": True,
            "valign": "vcenter",
        }
    )
    section_format = workbook.add_format(
        {"bold": True, "font_color": "white", "bg_color": "#5B9BD5"}
    )
    note_format = workbook.add_format({"text_wrap": True, "valign": "top"})
    link_format = workbook.add_format(
        {"font_color": "blue", "underline": True, "text_wrap": True}
    )

    readme = workbook.add_worksheet("README")
    readme.set_column(0, 0, 28)
    readme.set_column(1, 1, 110)
    readme.merge_range(0, 0, 0, 1, "RQ1 vLLM per-artifact metrics", section_format)
    notes = [
        ("Repository", REPOSITORY),
        ("Canonical release", RELEASE_TAG),
        ("Release URL", RELEASE_URL),
        ("Snapshot cutoff", SNAPSHOT_CUTOFF),
        ("Expected records", f"{expected_issues:,} Issues + {expected_prs:,} PRs"),
        (
            "Records sheet",
            "One row per canonical Issue or PR. Filter record_type to obtain "
            "either population.",
        ),
        (
            "Empty cells",
            "Empty means not applicable or not observed. Use the adjacent "
            "state/status and availability columns before analysis.",
        ),
        (
            "Substantive response",
            "Human annotation has not been performed. Human-annotated fields "
            "are blank; rq1-substantive-text-v1 fields are exploratory only.",
        ),
        (
            "Workload category",
            "Not labeled yet. workload_category is blank and "
            "workload_label_status is not_labeled.",
        ),
        (
            "PR semantic labels",
            "Subsystem and accelerator labels are model-assisted, "
            "Release-aligned, and provisional pending stratified human audit.",
        ),
        (
            "Review rounds",
            "A proxy: a new block starts when a qualifying formal review "
            "follows an observed author commit. Commit time is not true push "
            "time.",
        ),
        (
            "Code churn",
            "Only populated where canonical PR file rows exist. Missing churn "
            "is blank, not zero; inspect churn_data_available and "
            "files_cutoff_stable.",
        ),
        (
            "Orphan inline comments",
            "21 canonical inline review comments cannot be assigned to a "
            "canonical PR and are therefore absent from per-PR counts.",
        ),
        (
            "Collaborators",
            "snapshot_collaborator refers to the May 18 roster, not historical "
            "event-time maintainer membership.",
        ),
        (
            "Interpretation",
            "GitHub activity is an observable proxy. Counts and elapsed time "
            "are not engineering hours without maintainer-survey calibration.",
        ),
        ("Release SQLite SHA256", RELEASE_DATABASE_SHA256),
    ]
    for row_index, (name, value) in enumerate(notes, start=2):
        readme.write_string(row_index, 0, name, header_format)
        if name == "Release URL":
            readme.write_url(row_index, 1, value, link_format, value)
        else:
            readme.write_string(row_index, 1, value, note_format)

    sheet = workbook.add_worksheet("records")
    sheet.freeze_panes(1, 4)
    sheet.set_row(0, 42)
    for column, field in enumerate(FIELD_NAMES):
        sheet.write_string(0, column, field, header_format)
    sheet.set_column(0, 1, 18)
    sheet.set_column(2, 2, 10)
    sheet.set_column(3, 3, 44)
    sheet.set_column(4, 4, 55)
    sheet.set_column(5, 9, 22)
    sheet.set_column(10, 18, 24)
    sheet.set_column(19, 29, 22)
    sheet.set_column(30, 44, 25)
    sheet.set_column(45, 66, 24)
    sheet.set_column(67, len(FIELD_NAMES) - 1, 28)

    counts: Counter[str] = Counter()
    with gzip.open(csv_output, "wt", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=FIELD_NAMES)
        writer.writeheader()
        for row_index, record in enumerate(records, start=1):
            writer.writerow(record)
            counts[record["record_type"]] += 1
            for column, field in enumerate(FIELD_NAMES):
                write_cell(sheet, row_index, column, record.get(field))
    total_records = sum(counts.values())
    sheet.autofilter(0, 0, total_records, len(FIELD_NAMES) - 1)

    monthly = workbook.add_worksheet("monthly_context")
    monthly.freeze_panes(1, 2)
    monthly.set_column(0, 1, 18)
    monthly.set_column(2, len(monthly_columns) - 1, 24)
    for column, name in enumerate(monthly_columns):
        monthly.write_string(0, column, name, header_format)
    for row_index, record in enumerate(monthly_rows, start=1):
        for column, name in enumerate(monthly_columns):
            write_cell(monthly, row_index, column, record.get(name))
    monthly.autofilter(0, 0, len(monthly_rows), len(monthly_columns) - 1)

    dictionary = workbook.add_worksheet("data_dictionary")
    dictionary.freeze_panes(1, 1)
    dictionary.set_column(0, 0, 52)
    dictionary.set_column(1, 1, 14)
    dictionary.set_column(2, 2, 100)
    dictionary.set_column(3, 3, 25)
    for column, name in enumerate(("field", "applies_to", "definition_zh", "unit")):
        dictionary.write_string(0, column, name, header_format)
    for row_index, values in enumerate(FIELDS, start=1):
        for column, value in enumerate(values):
            dictionary.write_string(row_index, column, value, note_format)
    dictionary.autofilter(0, 0, len(FIELDS), 3)

    workbook.close()
    observed_issues = counts["issue"]
    observed_prs = counts["pull_request"]
    if observed_issues != expected_issues or observed_prs != expected_prs:
        raise ValueError(
            f"record count mismatch: issues={observed_issues}, prs={observed_prs}"
        )
    return {
        "issues": observed_issues,
        "pull_requests": observed_prs,
        "records": total_records,
        "fields": len(FIELD_NAMES),
        "monthly_rows": len(monthly_rows),
        "xlsx": str(output),
        "csv_gz": str(csv_output),
    }


def export(
    database_path: Path,
    issue_metrics_path: Path,
    issue_summary_path: Path,
    pr_labels_path: Path,
    output: Path,
    csv_output: Path,
) -> dict[str, Any]:
    """Join frozen data and export the sharing artifacts."""
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        metadata = {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM dataset_metadata")
        }
        if metadata.get("analysis_cutoff") != SNAPSHOT_CUTOFF:
            raise ValueError("database analysis_cutoff does not match the export")
        artifacts = base_artifacts(connection)
        github_label_values = github_labels(connection)
        actor_types_by_id, actor_types_by_login = actor_type_maps(connection)
        collaborator_ids, collaborator_logins = snapshot_collaborators(connection)
        pr_to_artifact, artifact_to_pr = pr_identity_maps(connection)
        semantic_labels = load_jsonl_by_number(pr_labels_path)
        issue_metrics = load_jsonl_by_number(issue_metrics_path)
        conversation_counts = pr_conversation_comment_counts(connection)
        reviews, review_monthly = pr_review_data(
            connection,
            artifacts,
            pr_to_artifact,
            actor_types_by_id,
            actor_types_by_login,
            collaborator_ids,
            collaborator_logins,
        )
        inline_comments = pr_inline_comment_counts(
            connection, actor_types_by_id, actor_types_by_login
        )
        commits = pr_commit_data(connection, artifacts, pr_to_artifact)
        churn = pr_churn_data(connection)
        file_stability = pr_file_stability(connection)

    expected_issues = sum(row["artifact_type"] == "Issue" for row in artifacts.values())
    expected_prs = sum(
        row["artifact_type"] == "PullRequest" for row in artifacts.values()
    )
    if len(issue_metrics) != expected_issues:
        raise ValueError("Issue metric population does not match Release")
    if len(semantic_labels) != expected_prs:
        raise ValueError("PR label population does not match Release")

    issues = issue_records(
        artifacts,
        issue_metrics,
        github_label_values,
        actor_types_by_id,
        actor_types_by_login,
        collaborator_ids,
        collaborator_logins,
    )
    prs = pr_records(
        artifacts,
        artifact_to_pr,
        semantic_labels,
        github_label_values,
        conversation_counts,
        reviews,
        inline_comments,
        commits,
        churn,
        file_stability,
        actor_types_by_id,
        actor_types_by_login,
        collaborator_ids,
        collaborator_logins,
    )
    monthly_columns, monthly_rows = monthly_context(
        issue_summary_path,
        artifacts,
        actor_types_by_id,
        actor_types_by_login,
        review_monthly,
    )
    return write_workbook(
        output,
        csv_output,
        chain(issues, prs),
        monthly_columns,
        monthly_rows,
        expected_issues=expected_issues,
        expected_prs=expected_prs,
    )


def main() -> None:
    """Export the shareable table from explicit frozen inputs."""
    parser = argparse.ArgumentParser(
        description="Export the vLLM RQ1 per-artifact workbook and CSV."
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--issue-metrics", type=Path, required=True)
    parser.add_argument("--issue-summary", type=Path, required=True)
    parser.add_argument("--pr-labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()
    result = export(
        args.database,
        args.issue_metrics,
        args.issue_summary,
        args.pr_labels,
        args.output,
        args.csv_output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
