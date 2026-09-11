# Rollout review: vllm-deterministic-bmm-batch-scaling v1.2.4

One original GPT-6-Astra / high attempt: reward 1, no Harbor exception. All 24 ATIF steps were read and the final candidate was checked using its complete pre-verifier filesystem snapshot. No blocking task or candidate defect was found.

9 independent groups passed: eight new numerical geometries plus empty/stride/out boundaries. Formal replay reward: 1; speedups: 6.165x, 10.314x and 1.873x against 2x, 1.05x and 1.05x.

The review used [ai-infra-bench-rollout-review](https://github.com/ai-infra-bench/ai-infra-bench/tree/b989bc67e2b945c3be00d548ca25b1f73519f478/.agents/skills/ai-infra-bench-rollout-review). The [audit](review/final-audit.json), [capture checks](review/capture-audit.json), [replay record](review/replay-record.json) and [complete diagnostic logs](review/replay-evidence.tar.gz) accompany this report. Prior Oracle and alternative/control evidence was reused after exact file comparisons; no new solver run was made during review.

Diagnostics used restored snapshots on A100 GPUs with read-only tests and no external network. They did not impose the original CPU/memory cgroup limits, so their wall times are not equivalent end-to-end benchmarks. Original tool outputs that were already truncated cannot be recovered. The model API reported gpt-6-astra/high; an immutable backend revision was not recorded.

Publication correction: the frozen BMM document said 6/24 cases; the publication copy says 8/32, matching the existing verifier. The original trajectory and all historical hashes are preserved.

## Candidate behavior and attribution

公开边界是 CUDA 三维矩阵及可选 out，经真实 Triton 归约得到数值结果、batch/single 位级一致性和 copy-compatible out，并满足 launch scaling 及三个公开性能门槛。out 可转换 dtype、跨设备 copy 或合法广播；不能沿用旧版本的错误 out_dtype_mismatch 拒绝规则。

agent 定位到逐 batch 启动的 Python 循环，改为一个覆盖 batch/M/N 的 Triton grid。每个 tile 以固定 K 顺序累加，FP32 使用 tf32x3，保留设备检查、64 位 stride、空结果及 out.copy_ 返回原对象。生产修改只有 batch_invariant.py；新增 benchmark 和测试均已读完，未修改评分路径。pytest/ruff 安装因离线环境失败后，agent 以 AST 执行自身测试函数；这是自测启动方式变化，不是正式 verifier 被跳过。原轨迹实际记录 106 项自测完成，不能把它写成 pytest 全套执行。

原评分有四个完整阶段：8 组数值形状、32 次额外 out copy 检查、7 类非法输入、batch=1/7/29 的真实 CUDA launch 观测、3 组配对计时。父进程从本轮自己持有的输入计算 CPU float64 参考；原始三个加速比分别为 6.132、10.320、1.874。独立 challenge 用 K=2048/3072 的新 FP32 输入及非连续/空维度/out 场景，不以旧 TF32 Oracle 作为数值真值。

已确认的一项非阻断问题：冻结版 validation/semantic-boundary.md:7 仍写 Six / 24，实际代码和证据是 8 / 32。它是既有文档计数未同步，不会改变 reward。本轮没有修改 task。
