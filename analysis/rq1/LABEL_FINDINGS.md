# RQ1：Release 对齐的 PR 子系统与加速器标签

> Release 截止时间：2026-07-31 23:59:59 UTC。32,884 条模型标签来自原
> 2026-08-08 API/Git 输入，另有 51 条使用 Release 证据补标。全部标签已按 PR
> number 对齐 Release，尚待分层人工审计。本页只讨论 subsystem 与 accelerator；
> 工作类型标签尚未开展。

## 标签对齐

| 口径 | PR |
|---|---:|
| Release 全部 PR | 32,935 |
| 成功映射原有标签 | 32,884 |
| 使用 Release 证据补标 | 51 |
| 标签总覆盖 | 32,935（100%） |
| 旧标签集中不属于 Release 的截止日后 PR | 703 |
| Release 人类 PR | 32,822 |
| 有标签的人类 PR | 32,822（100%） |

51 个 Release 独有 PR 均已补标；其中 5 个从 base merge commit 恢复了文件路径，
46 个使用截止日稳定的 title/body/repository labels，并保留
`file_paths_unavailable` 风险标记。703 个 8 月新增 PR 不进入 7 月 31 日分析。
以下比例以 32,822 个 Release 人类 PR 为总体分母；时期分母分别为
launch–2024 5,382、2025 年 12,796、2026 年截至 7 月 14,644。

## 主要结论

1. **工作重心向执行内核和内存路径移动。** kernels/operators 从
   launch–2024 的 17.3% 增至 2026 年的 27.7%，memory/KV cache 从 6.7%
   增至 13.8%。models 保持约 22%–23%。
2. **后端特定工作扩大。** `specific` accelerator scope 从 20.6% 增至
   30.6%；agnostic 从 70.1% 降至 61.5%。这描述 PR 构成变化，不等于平台
   工时。
3. **AMD ROCm 和 Intel XPU 的可见覆盖上升。** AMD ROCm 从 4.2% 增至
   11.2%，Intel XPU 从 1.7% 增至 3.5%；2026 年 NVIDIA CUDA 为 14.1%。
4. **跨组件协调不可忽略。** 7,672 个 PR（23.4%）同时涉及多个子系统，平均
   每个 PR 有 1.267 个子系统标签。最常见组合是 hardware backends +
   kernels/operators（1,551 个）。

## 子系统分布

多标签百分比之和可以超过 100%。

| 子系统 | 全时期 | launch–2024 | 2025 | 2026 截止日 |
|---|---:|---:|---:|---:|
| kernels/operators | 23.5% | 17.3% | 21.2% | 27.7% |
| models | 22.7% | 22.4% | 22.4% | 23.0% |
| other | 15.6% | 20.8% | 18.7% | 11.1% |
| frontend/API | 15.1% | 15.0% | 13.5% | 16.6% |
| hardware backends | 14.5% | 12.7% | 15.0% | 14.6% |
| distributed serving | 11.6% | 10.1% | 11.2% | 12.5% |
| memory/KV cache | 10.6% | 6.7% | 8.6% | 13.8% |
| scheduling | 9.6% | 11.6% | 9.3% | 9.2% |
| unknown | 3.4% | 4.2% | 4.0% | 2.7% |

最常见的多子系统组合为：

| 组合 | PR |
|---|---:|
| hardware backends + kernels/operators | 1,551 |
| kernels/operators + models | 1,013 |
| distributed serving + memory/KV cache | 871 |
| kernels/operators + memory/KV cache | 584 |
| frontend/API + models | 554 |

## 加速器覆盖

### Scope

| Scope | 全时期 | launch–2024 | 2025 | 2026 截止日 |
|---|---:|---:|---:|---:|
| agnostic | 64.3% | 70.1% | 65.1% | 61.5% |
| specific | 26.7% | 20.5% | 24.8% | 30.6% |
| cross-backend | 2.1% | 2.5% | 2.5% | 1.5% |
| unknown | 6.9% | 6.9% | 7.6% | 6.4% |

### 厂商/平台

| 厂商/平台 | 全时期 PR | 全时期 | launch–2024 | 2025 | 2026 截止日 |
|---|---:|---:|---:|---:|---:|
| NVIDIA CUDA | 4,216 | 12.8% | 10.9% | 12.3% | 14.1% |
| AMD ROCm | 2,760 | 8.4% | 4.2% | 6.9% | 11.2% |
| CPU | 1,417 | 4.3% | 4.6% | 4.2% | 4.3% |
| Intel XPU | 806 | 2.5% | 1.7% | 1.5% | 3.5% |
| Ascend NPU | 21 | 0.1% | <0.1% | 0.1% | 0.1% |
| Cambricon MLU | 2 | <0.1% | <0.1% | <0.1% | 0.0% |

Ascend 和 MLU 样本过少，不能作平台间比较。低计数也可能意味着开发主要发生在
外部仓库，不能解释为没有维护工作。

## 标签质量与限制

- subsystem `unknown` 为 1,127 个（3.4%），subsystem low confidence 为
  1,383 个（4.2%）。
- accelerator scope `unknown` 为 2,270 个（6.9%），accelerator low
  confidence 为 1,373 个（4.2%）。
- 31,600 个人类 PR（96.3%）的 Release 文件表示标记为 cutoff-stable；
  1,254 个（3.8%）的 Release 文本表示可能包含截止日后编辑。
- 原标签输入来自 8 月 8 日 API/Git manifest，不能保证每条 evidence 都是 7 月
  31 日当时可见的表示；51 条补标使用 Release 截止日证据。正式发布前应优先
  审计这 1,254 个 PR、低置信度、
  `unknown` 和稀有厂商样本。
- 当前模型解析版本为 `gpt-5.6-sol-2026-07-09`，taxonomy 版本为
  `rq1-subsystem-accelerator-2026-08-13`；原标签 prompt 为 v1，Release 补标
  prompt 为 v2。模型标签是测量结果，不是人工真值。

## 复现

```bash
uv run aib-rq1 align-release-labels \
  --database /path/to/vllm_github_2026-07-31.sqlite \
  --labels artifacts/rq1/2026-08-08/full_pr_labels.jsonl \
  --labels artifacts/rq1/2026-07-31/supplemental_pr_labels.jsonl \
  --label-source-cutoff 2026-08-08T23:59:59Z \
  --label-source-cutoff 2026-07-31T23:59:59Z \
  --records-output artifacts/rq1/2026-07-31/pr_label_sidecar.jsonl \
  --summary-output artifacts/rq1/2026-07-31/pr_label_summary.json
```
