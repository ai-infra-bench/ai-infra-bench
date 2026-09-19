BMM 输出兼容性：本轮修订及本地验证完成。

前次通过结论在契约/fixture 问题确认后撤回，本报告替代旧结论；历史 raw reward 未修改。

修复：Preserve baseline out copy semantics, including dtype/device conversion and broadcast-compatible destinations. Reject only originally invalid shapes. No new same-dtype/device out restriction.

语义边界：CUDA operands and optional out -> production deterministic batched Triton multiplication and compatible output copy -> numeric and bitwise correctness, original out object and conversion contents, original invalid input behavior, bounded launches and unchanged A100 latency ratios

覆盖：Six dtype/shape numerical and bitwise cases, 24 out-copy cases (two alternate dtypes, CPU destination and leading broadcast dimension per case), seven invalid-input cases, launch batches 1/7/29, three unchanged timing shapes with 5 warmups/20 iterations/5 median rounds.

替代及限制：A100 CUDA/Triton production execution. Model serving is outside this tensor-kernel boundary. Performance measured on the three public shapes, not all possible workloads.

| Case | Expected | Actual | Harbor errors |
|---|---:|---:|---:|
| alternate-copy-compatible-agent | 1 | 1 | 0 |
| alternate-persistent-kernel | 1 | 1 | 0 |
| base | 0 | 0 | 0 |
| diagnosis-only-batch-loop | 0 | 0 | 0 |
| early-exit-os-exit | 0 | 0 | 0 |
| early-exit-system-exit | 0 | 0 | 0 |
| forged-report-exit | 0 | 0 | 0 |
| oracle | 1 | 1 | 0 |
| out-view-return | 0 | 0 | 0 |
| replay-observations | 0 | 0 | 0 |
| strict-out-rejection | 0 | 0 | 0 |
| oracle (frozen final) | 1 | 1 | 0 |

独立 challenge：6 个状态均符合预期。
BMM：同一历史候选源码在旧契约下 0、新契约下 1；旧严格 Oracle 作为不兼容反例得到 0。

原始日志、job/trial、镜像与文件 SHA256：validation/e2e-evidence.json。
本轮证据根目录：/data/yinchen/task-contract-fixture-fix-20260909T033612Z
改动未提交、未推送。
