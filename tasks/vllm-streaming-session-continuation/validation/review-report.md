Streaming 可保留；本轮指定 skill 三道审核通过，未发现新的阻断问题。

真实 GPUModelRunner/InputBatch 生命周期在 CPU 上执行，允许重建与原地更新两种实现。新增检查覆盖暂离 batch 的会话恢复、两条同时续接、token/embedding 切换和第三个会话不受影响。

题目描述改成 3 个连续自然段，保留原公开契约和实现自由；task.toml、镜像、评分代码、Oracle 与控制补丁未改。Gate 1 通过；Gate 2 镜像身份、Git 隔离及导入检查通过。Gate 3 通过。

| Case | Declared expected | Actual reward | Harbor errors |
|---|---:|---:|---:|
| base | 0 | 0 | 0 |
| alternate-continuation | 1 | 1 | 0 |
| early-exit-os-exit | 0 | 0 | 0 |
| early-exit-system-exit | 0 | 0 | 0 |
| incomplete-output-absorption | 0 | 0 | 0 |
| forged-report-exit | 0 | 0 | 0 |
| replay-observations | 0 | 0 | 0 |
| oracle | 1 | 1 | 0 |

这些是本轮真实 Harbor 结果。独立新增 challenge 的 Base/Oracle/替代解三种状态均符合预期。真实 runner 和 InputBatch 的状态生命周期在 CPU 执行；调度记录、PP 最后 rank、模型位置生产者属于非决定性输入替代。没有宣称执行完整模型 forward、HTTP 服务或 CUDA 推理。

Astra 的历史 reward、轨迹及最终环境重放记录保持原样。Streaming ZIP 的 CRC、16 项内部清单与原始文件均重新核验；旧 instruction hash 明确保留。本轮没有新跑 Astra/Opus，没有提交、推送或更新 PR。

Skill: /data/yinchen/streaming-modular-task-review-20260912T051251Z/skill-repo/.agents/skills/ai-infra-bench-task-review；HEAD b989bc67e2b945c3be00d548ca25b1f73519f478，clean。完整范围、源码/镜像哈希、原始 job/trial、命令、退出码和证据在 e2e-evidence.json 与 /data/yinchen/streaming-modular-task-review-20260912T051251Z/RESULT.md。
