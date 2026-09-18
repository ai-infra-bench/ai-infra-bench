Historical review of an earlier revision. Current status and evidence are in `review-report.md` and `e2e-evidence.json`.

PR18 构造函数与调度时序：本轮修订及本地验证完成。

前次通过结论在契约/fixture 问题确认后撤回，本报告替代旧结论；历史 raw reward 未修改。

修复：Run production constructor. Substitute only model computation/sampling inputs; keep constructor-owned buffers and state. Specify schedule twice before update_from_output while requests remain runnable and resources are sufficient. Retain no CPU-object collective or device-to-host synchronization constraints.

语义边界：Real initialized production runner with valid model configuration and sampled GPU tensors -> real PP NCCL handoff and retained/discarded bookkeeping -> next GPU input preparation and next async scheduler round

覆盖：Real constructor and CPU/GPU buffers, CONFIG, SCHEDULER_REENTRY at 1/3 requests, NCCL_BASIC/REORDERED/INTEGRATED with two ranks, production output materialization and next GPU input consumption; independent five-request interleaved-discard challenge.

替代及限制：Runner initialization and world/TP/PP groups are real. Model weights/attention execution and sampling computation are replaced by valid sampled-tensor inputs. No attention is executed; empty KV groups are supplied to the downstream state slice. This is not a full model generation deployment.

| Case | Expected | Actual | Harbor errors |
|---|---:|---:|---:|
| alternate-inline-nccl | 1 | 1.0 | 0 |
| base | 0 | 0.0 | 0 |
| constructor-owned-transport | 1 | 1.0 | 0 |
| cpu-sync-object-collective | 0 | 0.0 | 0 |
| early-os-exit | 0 | 0.0 | 0 |
| early-system-exit | 0 | 0.0 | 0 |
| group-coordinator-broadcast | 1 | 1.0 | 0 |
| oracle | 1 | 1.0 | 0 |
| post-broadcast-failure | 0 | 0.0 | 0 |
| oracle (frozen final) | 1 | 1.0 | 0 |

独立 challenge：6 个状态均符合预期。
PR18：同一正确的构造函数实现，在旧 fixture 中因属性缺失得 0；新 fixture 中得 1。原始 agent 的 CPU 通信/同步问题未因此被改成通过。

原始日志、job/trial、镜像与文件 SHA256：validation/e2e-evidence.json。
本轮证据根目录：/data/yinchen/task-contract-fixture-fix-20260909T033612Z
改动未提交、未推送。
