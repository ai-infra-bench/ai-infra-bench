# Modular MoE task hardening review

Task 可保留；本轮修复后通过指定 ai-infra-bench-task-review 的三道审核。#71 Streaming 未在本轮修改。本地 task 版本为 1.2.7，未提交、推送或更新 PR。

## 问题与修复

原评分用固定 NoEP/Triton 组件替换 FlashInfer prepare builder 和专家选择器，遗漏真实配置传播。旧 Oracle 和三个替代解会跳过必要的数据汇集，或在非 DP 层错误启用汇集。现在保留原真实 Triton 数值与 workspace 检查，并增加真实 factory → prepare → expert apply → finalize 的完整生命周期检查。新 Oracle 在准备与专家选择前统一使用当前层的完整配置。

新检查覆盖不同 DP/TP/EP 组合、非零 rank、不等长 payload、路由数据、外部专家 ABI 和最终局部结果。它不要求私有字段名或恰好一次专家调用。旧 Oracle 和三个不完整替代解逐字节保留为负例；四个正确替代实现都通过，包括额外 workspace 查询与保存的 Astra 最终生产补丁。另两项负例分别遗漏专家配置、错误取首 rank 且省略归约，均被拒绝。

## 三道审核

Gate 1：说明保持 3 个自然段，未增加解法提示，任务契约未改变。Gate 2：仍使用原冻结镜像，源码、依赖、资源和网络配置未变。FlashInfer 标准缓存目录设置修正了 root 父进程降权后工作进程无法写入默认缓存的问题，未修改解释器启动策略。Gate 3：真实配置决策组件全部执行，独立 challenge 也验证了不同配置和数据下的行为。数值容差、16,384-row profiling 要求和硬件规格均未降低。

| Case | Expected | Actual | Harbor errors |
|---|---:|---:|---:|
| base | 0 | 0 | 0 |
| oracle | 1 | 1 | 0 |
| alternate-consumer-boundary-ownership | 0 | 0 | 0 |
| early-exit-os-exit | 0 | 0 | 0 |
| early-exit-system-exit | 0 | 0 | 0 |
| wrong-legacy-owner | 0 | 0 | 0 |
| forged-report-exit | 0 | 0 | 0 |
| constant-numerical-output | 0 | 0 | 0 |
| replay-observations | 0 | 0 | 0 |
| compatibility-global-warning | 0 | 0 | 0 |
| alternate-workspace-diagnostic | 0 | 0 | 0 |
| undersized-profile-workspace | 0 | 0 | 0 |
| alternate-layer-config-view | 1 | 1 | 0 |
| missing-flashinfer-owner | 0 | 0 | 0 |
| alternate-full-config-owner | 0 | 0 | 0 |
| incomplete-flashinfer-pipeline | 0 | 0 | 0 |
| alternate-consumer-full-pipeline | 1 | 1 | 0 |
| missing-expert-parallel-config | 0 | 0 | 0 |
| incorrect-finalize-rank-slice | 0 | 0 | 0 |
| alternate-layer-owned-method | 1 | 1 | 0 |
| alternate-workspace-full-pipeline | 1 | 1 | 0 |
| final-oracle | 1 | 1 | 0 |

共 22 次完整 Harbor，全部符合预期且无 Harbor 异常。两次 Oracle 均为 1，7 组检查全部执行。15 项独立 challenge 状态符合预期，其中 12 项执行新增完整路径，3 项执行不同几何的 workspace 检查。挑战首次构造错误、缓存权限诊断错误和 GPU 锁冲突均单独保留，不计入有效行为验证。完整矩阵与最终 Oracle 的评分文件哈希相同；curator-only challenge 构造修正已在最终 Oracle 前归档冻结。

## 验证边界与证据

这是单卡 CUDA 上的组合验证：真实配置决策、准备、专家调用和结束阶段执行；跨 rank 传输及外部 FlashInfer 算术由保留 payload/顺序/归约语义的确定性边界替代。没有声称执行多进程 NCCL 或完整 FlashInfer FP8 数值。既有真实 Triton 数值回归继续执行。

本轮没有新跑 Astra/Opus。Astra 最终补丁通过新评分器的完整 Harbor 重放；原始轨迹和得分不改写。历史 P1 与错误正例证据见 validation/history/before-prepare-hardening-20260912.json。镜像、最终文件 SHA256、实际命令、job/trial ID、退出状态及 raw artifact hashes 见 e2e-evidence.json。完整工作目录：/data/yinchen/modular-prepare-hardening-20260912T053849Z。

Skill 路径：/data/yinchen/streaming-modular-task-review-20260912T051251Z/skill-repo/.agents/skills/ai-infra-bench-task-review；HEAD b989bc67e2b945c3be00d548ca25b1f73519f478。最终严格机械审计结果另存 /data/yinchen/modular-prepare-hardening-20260912T053849Z/strict-audit.log；机械审计不替代上述语义验证。
