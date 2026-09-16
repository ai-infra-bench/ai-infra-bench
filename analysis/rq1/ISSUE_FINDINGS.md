# RQ1：Issue 到达、关闭、积压与响应

> 权威冻结时间：2026-07-31 23:59:59 UTC。主数据源为 Release
> `vllm-github-data-2026-07-31` 的 canonical SQLite；2026-08-08 API
> 数据仅保留为后续增量和敏感性快照。GitHub 活动是可观察代理，不等于工程工时。

## 对齐结果

不能把 8 月 API 快照简单截断到 7 月 31 日。Release 恢复了 API 快照遗漏的历史
对象，在共同截止日的差异如下：

| 对象 | Release | 旧 API 快照 | Release 多出 |
|---|---:|---:|---:|
| Issue | 16,990 | 16,946 | 44 |
| PR | 32,935 | 32,884 | 51 |
| Issue/PR conversation comments | 205,998 | 205,043 | 955 |
| PR reviews | 131,473 | 131,020 | 453 |

因此，本页 Issue 结论已切换到 Release；现有 PR 生命周期、响应、评审和模型标签
仍基于 8 月 API 快照，迁移前只能视为 provisional。

## 主要结论

1. **Issue 需求仍在上升。** 人类 Issue 从 2024 年的 4,339 个增至 2025
   年的 6,937 个，增长 59.9%；月均从 361.6 增至 578.1。2026 年 1–7 月
   月均 609.7 个，较 2025 年再高 5.5%。
2. **积压持续扩大并且以中期未结项为主。** 年末 backlog 从 2023 年的
   817、2024 年的 1,233 增至 2025 年的 1,791；2026 年 7 月末为 2,054。
   其中 1,520 个已超过 30 天、797 个超过 90 天、205 个超过 180 天。
3. **关闭量不能直接解释为人工维护容量。** 观察到首次关闭的 14,978 个
   人类 Issue 中，5,857 个（39.1%）首次由 GitHub `Bot` 关闭。自动化占
   close transition 的比例从 2024 年的 22.0% 升至 2025 年的 46.9% 和
   2026 年前 7 个月的 47.3%。
4. **快照协作者的早期响应覆盖明显下降。** 2 天内响应率从 2024 年的
   47.8% 降至 2025 年的 36.2%，2026 年截至 7 月为 19.9%；7 天内分别为
   51.7%、40.0% 和 23.0%；30 天内分别为 54.7%、43.1% 和 27.5%。各比率
   仅使用完整观察窗口，并附 Wilson 95% 区间。
5. **Issue responder 的可观察供需压力在 2026 年中上升。** 新 Issue/活跃
   Issue 快照协作者 responder 从 2025-12 的 10.26 升至 2026-07 的
   21.77；同期 backlog/responder 从 38.93 升至 66.26。该分母不包括只做
   PR review 或 merge 的协作者，因此不是完整 active-maintainer workload。

## 数据总体

| 口径 | 数量 |
|---|---:|
| 全部 Issue | 16,990 |
| GitHub `User` authored Issue | 16,985 |
| Organization authored Issue | 4 |
| 作者类型缺失 | 1 |
| Issue conversation comments | 84,242 |
| close/reopen 输入事件 | 15,975 |
| 人类 Issue 截止日关闭 | 14,931 |
| 人类 Issue 截止日开放 | 2,054 |
| 观察到首次关闭 | 14,978 |

Bot 主口径严格使用 GitHub `user.type == Bot`，不按用户名猜测。Organization 和
actor type 缺失的 Issue 单列，不静默并入人类 Issue。

## 到达、关闭与 backlog

| 时段 | 新人类 Issue | 月均 | close transitions | 其中自动关闭 | 期末 backlog |
|---|---:|---:|---:|---:|---:|
| 2023（4–12 月） | 1,441 | 160.1 | 646 | 0 | 817 |
| 2024 | 4,339 | 361.6 | 4,031 | 886 | 1,233 |
| 2025 | 6,937 | 578.1 | 6,561 | 3,076 | 1,791 |
| 2026（1–7 月） | 4,268 | 609.7 | 4,189 | 1,982 | 2,054 |

关闭数按状态 transition 计数；同一 Issue 关闭、重开、再次关闭会产生多个
transition。全时期共有 496 次 reopen transition。2024 年 11 月的 809 次关闭中
595 次来自自动化，当月 backlog 从 1,780 降至 1,331；该下降不能全部归因为人工
处理。

2026 年 7 月末 backlog 的年龄结构为：74.0% 超过 30 天、38.8% 超过 90 天、
10.0% 超过 180 天。所有月末状态流量都与 canonical 截止状态对账，月度
reconciliation adjustment 均为 0。

## 首次快照协作者响应

Release 的 `repo_collaborator` 是 2026-05-18 的单点名单，不是历史成员表。本页
将名单中 triage/write/maintain/admin 的 103 人称为 **snapshot collaborators**
（write+ 70 人、triage-only 33 人），不能称作 event-time maintainers。响应定义
为第一条来自该名单成员的公开评论，同时排除 Issue 作者和 GitHub Bot。

| 创建年份 | Issue | 最终观察覆盖率 | 观察事件中位数 | 2d 内（95% CI） | 7d 内（95% CI） | 30d 内（95% CI） |
|---|---:|---:|---:|---:|---:|---:|
| 2023 | 1,441 | 59.9% | 182.76h | 23.9% [21.8, 26.2] | 29.4% [27.1, 31.8] | 34.6% [32.1, 37.1] |
| 2024 | 4,339 | 60.2% | 4.72h | 47.8% [46.3, 49.3] | 51.7% [50.2, 53.2] | 54.7% [53.2, 56.2] |
| 2025 | 6,937 | 45.8% | 5.48h | 36.2% [35.0, 37.3] | 40.0% [38.9, 41.2] | 43.1% [41.9, 44.3] |
| 2026 截止日 | 4,268 | 27.2% | 10.85h | 19.9% [18.7, 21.1] | 23.0% [21.8, 24.3] | 27.5% [26.1, 29.0] |

2026 cohort 的完整窗口分母分别为 2 天 4,221、7 天 4,108、30 天 3,620；其他
年份都已获得完整 30 天窗口。全时期有 7,807 个 Issue（46.0%）观察到快照协作者
响应，观察事件中位数为 7.35 小时、P75 为 55.37 小时、P90 为 918.21 小时。
这些条件分位数排除了未响应 Issue，跨年判断应以固定窗口覆盖率为主。

`rq1-substantive-text-v1` 的文本启发式仅保留在派生 artifact 中作为 exploratory
sensitivity，不作为正式“实质响应”结论。正式指标需要分层人工标注和误差报告。

## 关闭时间与自动化

| 首次关闭者 | Issue | 观察到首次关闭的中位数 | P75 | P90 |
|---|---:|---:|---:|---:|
| 人类 | 9,067 | 5.16 天 | 47.92 天 | 132.48 天 |
| GitHub Bot | 5,857 | 126.26 天 | 176.59 天 | 250.02 天 |
| actor type 缺失 | 54 | 3.64 天 | 44.30 天 | 140.09 天 |

全部人类 Issue 的 closed-only 首次关闭中位数是 90.73 天；将 2,007 个未观察到
首次关闭的 Issue 作为右删失后，Kaplan–Meier 中位数是 120.28 天。自动化首次
关闭中位数为 126.26 天，说明总体关闭时间强烈混合了人工决策与 stale
automation。

2026 cohort 的 closed-only 中位数只有 11.49 天，但纳入右删失后的
Kaplan–Meier 中位数为 120.58 天。因此不能用已关闭样本宣称 2026 年关闭速度
大幅提高。

## 月度 Issue responder 供需（选取月份）

| 月份 | 新 Issue | 活跃 Issue 快照协作者 responders | 新 Issue/responder | backlog | backlog/responder |
|---|---:|---:|---:|---:|---:|
| 2024-12 | 359 | 30 | 11.97 | 1,233 | 41.10 |
| 2025-06 | 507 | 44 | 11.52 | 1,885 | 42.84 |
| 2025-12 | 472 | 46 | 10.26 | 1,791 | 38.93 |
| 2026-03 | 693 | 41 | 16.90 | 1,773 | 43.24 |
| 2026-06 | 517 | 41 | 12.61 | 1,969 | 48.02 |
| 2026-07 | 675 | 31 | 21.77 | 2,054 | 66.26 |

## 数据质量与限制

- Release 解压 SQLite 的官方 SHA256 为
  `2ac86507a95f9b8785e6ce0bbf2745e3fbba67c747e37b54020a7e57ce80f8b5`。
- 13,574 个 base-layer Issue 的生命周期使用 `issue_closed_history`；3,416 个
  delta-layer Issue 使用 `canonical_maintenance_event`，不把两套事件盲目 union。
- 输入包含 14,354 个 base 和 1,621 个 delta close/reopen 事件；90 个冗余状态
  事件被忽略，42 个 Issue 使用 canonical `closed_at_cutoff` 回退。
- 14 个生命周期事件缺少可验证的 GitHub actor type，单列为 unknown；没有按登录名
  将其猜成 bot。
- 4 条 delta comment 的文本表示可能包含截止日后编辑；时间戳仍在 cutoff 内。
  这会影响探索性文本规则，不影响评论到达时间和快照协作者身份。
- Comment、关闭次数、backlog 和响应时间都只是公开活动代理，不能换算为工程
  小时、个人效率或 Issue 难度。

## 复现

```bash
uv run aib-rq1 derive-release-issue-metrics \
  --database /path/to/vllm_github_2026-07-31.sqlite \
  --records-output artifacts/rq1/2026-07-31/issue_metrics.jsonl \
  --summary-output artifacts/rq1/2026-07-31/issue_summary.json
```
