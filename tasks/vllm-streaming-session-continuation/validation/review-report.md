vllm-streaming-session-continuation：可保留；本轮本地三道 review 通过。

原问题属于评测评分问题：候选进程复制上一次的 observations 后直接成功退出，旧评分器仍给 1。当前保留同一个补丁和同一份旧观测，完整 Harbor 得到 0。

本轮修改：评分父进程持有实际测试输入；数值参考与状态期望来自本次输入。保留真实生产调用、原性能门槛和正确性要求。Streaming 快照即时复制，支持正确的原地更新实现。

Gate 1：任务工作流合理；公开输入和目标不变。
Gate 2：固定镜像身份、Base Git 历史隔离和 agent 用户导入检查通过；隐藏测试、答案与验证材料未打包到 agent 镜像。runner 状态切片在 CPU 执行。
Gate 3：Base 因目标行为失败，Oracle 与不同实现的正确替代方案通过；错误修复、提前退出、直接写评分报告和旧观测回放均为 0。

语义边界：Repeated/interleaved complete new-request records for cached IDs -> real GPUModelRunner state update and persistent InputBatch -> consistent prompts/output absorption/block/sample/pool/M-RoPE state and no stale rows.

此任务明确限于 runner 状态切片，CPU 张量足以执行决定状态转移的生产代码；没有模拟决定结果的 CUDA 内核。调度输入、最后 PP rank、M-RoPE 位置生产者和 pooler 参数生产者是确定性替代。未执行 HTTP 服务、scheduler 全栈、模型 forward 或 GPU/native kernel，也不声称重新编译了这些未使用的扩展。

| Case | Expected | Actual | Harbor errors |
|---|---:|---:|---:|
| replay-observations | 0 | 0 | 0 |
| base | 0 | 0 | 0 |
| oracle | 1 | 1 | 0 |
| alternate-continuation | 1 | 1 | 0 |
| early-exit-os-exit | 0 | 0 | 0 |
| early-exit-system-exit | 0 | 0 | 0 |
| incomplete-output-absorption | 0 | 0 | 0 |
| forged-report-exit | 0 | 0 | 0 |
| oracle (final) | 1 | 1 | 0 |

独立 challenge：Base、Oracle、alternate-continuation、incomplete-output-absorption 四个状态均符合预期。
额外评分器回归：保留旧输出并更新输入描述，三组新输入均被拒绝；这些是评分器单元检查，不计为 Harbor trial。

最终 job：`2b08dd69-4920-4fd3-bb09-7740e28a9153`；trial：`db25955c-61c4-4bc9-93ce-025af71abf5c`。
原始证据及命令：/data/yinchen/task-owned4-final-review-20260909T012410Z
未提交、未推送；没有对外部 GitHub review 或 LLM agent 能力作通过声明。
原生扩展来源与范围限制见 environment-review；本轮没有声称完成 exact-Base 全量 C++ 重建。
