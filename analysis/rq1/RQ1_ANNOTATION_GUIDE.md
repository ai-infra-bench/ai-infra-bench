# RQ1 annotation and field guide

## Purpose

This document explains the per-artifact RQ1 sharing table and defines the
annotation contract for vLLM Issues and pull requests. The table is an
observational community dataset, separate from the agent benchmark score.
GitHub activity is treated as a public proxy for maintenance demand, not as a
measurement of engineering hours.

The canonical population is frozen by the
[`vllm-github-data-2026-07-31`](https://github.com/ai-infra-bench/ai-infra-bench/releases/tag/vllm-github-data-2026-07-31)
release at `2026-07-31T23:59:59Z`:

- 16,990 Issues;
- 32,935 pull requests;
- one row per Issue or pull request;
- monthly time series as the primary aggregate view;
- reporting windows of launch through 2024, calendar year 2025, and 2026
  through the cutoff.

## Current annotation status

| Annotation layer | Unit | Current status |
| --- | --- | --- |
| Lifecycle, response, and review metrics | Issue or PR | Derived from the canonical Release |
| Subsystem labels | PR | 32,935/32,935 labeled; model-assisted and pending human audit |
| Accelerator labels | PR | 32,935/32,935 labeled; model-assisted and pending human audit |
| Subsystem and accelerator labels | Issue | Not currently labeled; cells remain empty |
| Workload category | Issue or PR | Not labeled; `workload_label_status=not_labeled` |
| Human-annotated substantive response | Issue | Not annotated; human-annotation fields remain empty |
| Exploratory substantive-text rule | Issue | Available only as a sensitivity field; not human ground truth |

`unknown` is a valid evidence-insufficiency label. It is not a missing label
and must not be replaced merely to force coverage.

## Shared sample fields

| 字段 | 含义 |
| --- | --- |
| `case_note` | 这条样本的人工备注，说明它为什么值得关注；仅存在于案例样表，不属于全量原始指标 |
| `record_type` | 记录类型：`issue` 或 `pull_request` |
| `number` | GitHub Issue / PR 编号 |
| `url` | 对应 GitHub 链接 |
| `title` | Issue / PR 标题 |
| `state_at_cutoff` | 在研究截止时间点的状态，如 `open`、`closed`、`merged`、`closed_unmerged` |
| `created_at` | 创建时间，统一为 UTC |
| `author_group` | 作者所属群体，如外部贡献者或 snapshot collaborator |
| `first_close_at` | Issue 第一次被关闭的时间，即使之后又 reopen 也记录第一次 close |
| `time_to_first_close_days` | 从 Issue 创建到第一次关闭经历的墙钟天数 |
| `first_human_response_at` | 第一条由非作者、非 Bot 的 GitHub `User` 发布的响应时间 |
| `time_to_first_human_response_hours` | 从创建到第一次合格人类响应的墙钟小时数 |
| `first_snapshot_collaborator_response_at` | 第一条由 5 月 18 日快照协作者名单成员发布的合格响应时间 |
| `time_to_first_snapshot_collaborator_response_hours` | 从创建到 snapshot collaborator 首次响应的墙钟小时数 |
| `substantive_annotation_status` | 人工“首次实质性响应”标注状态；当前为 `not_annotated` |
| `first_human_formal_review_at` | PR 第一次收到合格正式 GitHub Review 的时间 |
| `time_to_first_human_formal_review_hours` | PR 创建到首次合格正式 Review 的墙钟小时数 |
| `qualifying_human_formal_review_submissions` | 符合统计条件的人类正式 Review 提交总次数 |
| `unique_human_formal_reviewers` | 参与合格正式 Review 的不同 reviewer 数量 |
| `review_rounds_proxy` | 估算的 Review 轮数；由作者 revision 分隔 Review activity blocks |
| `requested_changes_review_count` | 合格 `CHANGES_REQUESTED` Review 的次数 |
| `inline_review_comments_total` | 针对具体代码行留下的 Review comment 总数 |
| `merged_at` | PR 最终 merge 的时间 |
| `time_to_merge_days` | PR 从创建到 merge 经历的墙钟天数 |
| `commits_observed` | Release 中对该 PR 观测到的 commit 数量 |
| `churn_data_available` | 是否存在 canonical PR file rows；为 `False` 时 churn 字段留空而不是填 0 |
| `additions` | 文件级新增代码行数合计 |
| `deletions` | 文件级删除代码行数合计 |
| `changed_files` | 观测到的修改文件数量 |
| `subsystems` | 当前仅对 PR 提供的 vLLM 子系统多标签分类；Issue 保持空值 |
| `subsystem_confidence` | 模型对 subsystem 分类结果的置信度 |
| `accelerator_scope` | 硬件覆盖范围：`agnostic`、`specific`、`cross_backend` 或 `unknown` |
| `accelerators` | 具体涉及的硬件后端，可多选 |
| `accelerator_confidence` | 模型对 accelerator 分类结果的置信度 |
| `workload_label_status` | workload 类型标注状态；当前为 `not_labeled` |

全量表包含更多质量、删失状态、标签 provenance 和生命周期字段。完整
定义位于 Excel 的 `data_dictionary` sheet。空单元格表示“不适用”或“未观察
到”，必须结合相邻的 `*_state`、`*_status` 和 `*_available` 字段解释，不能
自动当作 0。

## Actor and response rules

### Human and Bot

- 只有 GitHub `user.type == Bot` 才被归为 Bot。
- login 中包含 `bot` 但 actor type 不是 `Bot`，不能据此推断为 Bot。
- actor type 缺失或为 Organization 的记录单独保留，不静默计入人类总体。

### Snapshot collaborator

`snapshot_collaborator` 指 Release 中冻结于 5 月 18 日的 repository
collaborator roster。它包括 triage 或更高权限的 103 个账号，其中 70 个为
write 或更高权限，33 个为 triage-only。

该 roster 不是历史 event-time maintainer membership。因此：

- 字段和报告使用 `snapshot collaborator`；
- 不把它写成某事件发生时的 maintainer；
- 不从一次快照反推历史任职起止时间。

### Issue response

合格的首次人类响应必须同时满足：

1. 是公开 conversation comment；
2. actor type 为 GitHub `User`；
3. 不是 Issue 作者；
4. 不是 Bot；
5. comment 非空且发生在冻结截止日前。

reaction、行政事件、label/assignment 变更、Bot 消息以及作者自回复不属于响应。
首次 snapshot-collaborator 响应在上述条件上再要求 actor 位于冻结 roster。

### Human substantive response

正式 substantive-response 指标必须由人工标注。当前
`human_annotated_substantive_response_at` 为空，
`substantive_annotation_status=not_annotated`。

全量表中的 `exploratory_substantive_text_rule_v1_*` 字段来自确定性文本规则，
仅供敏感性分析。它不能被重命名、复制或报告为人工标注结果。

## PR review and churn rules

### Formal Review

合格正式 Review 必须：

- state 为 `APPROVED`、`COMMENTED` 或 `CHANGES_REQUESTED`；
- 已 submitted；
- reviewer actor type 为 GitHub `User`；
- reviewer 不是 PR 作者；
- 发生在冻结截止日前。

`PENDING`、`DISMISSED`、Bot review 和作者自己的 review 不进入合格正式
Review 计数。行级 Review comments 与 conversation comments 分开统计。

### Review rounds

`review_rounds_proxy` 不是 GitHub 原生字段。第一条合格正式 Review 开始第一
轮；如果后续合格 Review 之前观察到 PR 作者的新 commit，则开始新一轮。

Release 中的 commit 时间是 push timing 的代理。没有观察到作者 commit 不代表
作者没有修改，因此 Review rounds 必须保留 `proxy` 表述，不能解释为精确轮次。

### Code churn

`additions`、`deletions` 和 `changed_files` 只有在 canonical PR file rows
存在时才填写。`churn_data_available=False` 表示缺失，不能填为 0。目前 9,190
个 PR 有文件级 churn，其他 PR 保持空值。代码 churn 是 patch size 的代理，
不是工作时长或难度。

## Semantic label taxonomy

### Subsystems

`subsystems` 是多标签字段，以分号分隔。允许值为：

| Label | Scope |
| --- | --- |
| `models` | 模型实现、模型接入、权重加载或模型配置 |
| `scheduling` | 请求调度、batching、队列、抢占和执行编排 |
| `memory_kv_cache` | KV cache、内存分配、offload、swap 和缓存管理 |
| `distributed_serving` | 多进程、多节点、并行策略和分布式 serving |
| `kernels_operators` | CUDA/Triton/其他 kernel、算子和底层计算路径 |
| `frontend_api` | OpenAI-compatible API、输入输出协议、CLI 和前端 serving |
| `hardware_backends` | 平台后端、设备抽象和厂商集成 |
| `other` | 有充分证据但不属于上述子系统 |
| `unknown` | 证据不足，无法可靠判定 |

一个 PR 可以同时涉及多个子系统。不要为了选择单一主标签而删除有证据支持的
次要标签。

### Accelerator scope

| Scope | Meaning |
| --- | --- |
| `agnostic` | 没有特定硬件后端依赖 |
| `specific` | 明确涉及一个或多个特定后端 |
| `cross_backend` | 明确协调、比较或统一多个硬件后端 |
| `unknown` | 证据不足，无法确定 scope |

`accelerators` 允许值为：

- `cpu`;
- `nvidia_cuda`;
- `amd_rocm`;
- `intel_xpu`;
- `ascend_npu`;
- `cambricon_mlu`.

当 `accelerator_scope=agnostic` 时，`accelerators` 必须为空。
`cross_backend` 通常应包含至少两个有证据支持的 accelerator labels。

### Confidence

| Value | Annotation interpretation |
| --- | --- |
| `high` | 标题、正文、文件路径或 repository labels 提供直接且一致的证据 |
| `medium` | 有合理证据，但范围或多标签边界存在一定歧义 |
| `low` | 证据有限、冲突或主要依赖弱线索 |

置信度描述当前分类证据，不是统计概率。

## Workload categories

Workload classification 尚未开展。预定 controlled vocabulary 为：

- `bug_fix`;
- `feature`;
- `performance`;
- `refactor`;
- `test_e2e`;
- `ci_build`;
- `docs_api`;
- `chore`;
- `unknown`.

在正式编写 workload annotation guide、完成双人试标和一致性评估前，
`workload_category` 必须保持空值，`workload_label_status` 必须保持
`not_labeled`。

## Human annotation procedure

对 subsystem、accelerator、workload 或 substantive response 开展人工标注时，
应遵守以下顺序：

1. 只检查冻结截止日前可见的标题、正文、repository labels、文件路径、comments
   和 reviews。
2. 先独立标注，再查看模型 label、rationale 或 confidence，避免锚定偏差。
3. 为每个标签记录直接证据，不根据作者身份、评论数量或 PR 大小猜测类别。
4. 证据不足时使用 `unknown`，不要强行分配标签。
5. 多标签按受影响范围标注，不把相互独立的子系统压缩为单一标签。
6. 两名标注者独立完成同一审计样本，分歧由第三人或共同会议 adjudicate。
7. 保留原始标注、adjudicated label、annotator ID、annotation round、时间和备注。

建议新增的人工标注字段为：

| Field | Purpose |
| --- | --- |
| `annotator_id` | 匿名或稳定的标注者编号 |
| `annotation_round` | pilot、audit、adjudication 等轮次 |
| `human_subsystems` | 人工 subsystem 多标签 |
| `human_accelerator_scope` | 人工 accelerator scope |
| `human_accelerators` | 人工 accelerator 多标签 |
| `human_workload_categories` | 人工 workload 多标签 |
| `human_substantive_response_at` | 人工确认的第一条实质响应时间 |
| `annotation_evidence` | 支持判断的截止日前证据 |
| `annotation_notes` | 歧义、排除理由和特殊情况 |
| `adjudication_status` | 未复核、已一致或已裁决 |

## Quality and reporting requirements

- 模型标签不是人工真值；正式结论前需进行分层双人人工审计。
- 审计优先覆盖 `unknown`、low confidence、截止日后表示风险以及 Ascend/MLU
  稀有样本。
- 多标签应分别报告每个 label 的 precision、recall 和样本量。
- 人工一致性至少报告原始 agreement；条件允许时报告适合多标签任务的一致性指标。
- 所有比例必须同时报告分子、分母和 missingness。
- 没有事件的开放记录属于 right-censored，不得把空响应时间或合并时间填为 0。
- comment、Review、churn 和 elapsed time 均不能直接换算为工程工时。
