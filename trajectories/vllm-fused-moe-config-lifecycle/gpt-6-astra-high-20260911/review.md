# Rollout review: vllm-fused-moe-config-lifecycle v1.2.6

One original GPT-6-Astra / high attempt: reward 1, no Harbor exception. All 35 ATIF steps were read and the final candidate was checked using its complete pre-verifier filesystem snapshot. No blocking task or candidate defect was found.

3 independent lifecycle, warning and bidirectional configuration-ownership groups passed with new workload geometry. All five formal replay stages passed; reward: 1.

The review used [ai-infra-bench-rollout-review](https://github.com/ai-infra-bench/ai-infra-bench/tree/b989bc67e2b945c3be00d548ca25b1f73519f478/.agents/skills/ai-infra-bench-rollout-review). The [audit](review/final-audit.json), [capture checks](review/capture-audit.json), [replay record](review/replay-record.json) and [complete diagnostic logs](review/replay-evidence.tar.gz) accompany this report. Prior Oracle and alternative/control evidence was reused after exact file comparisons; no new solver run was made during review.

Diagnostics used restored snapshots on A100 GPUs with read-only tests and no external network. They did not impose the original CPU/memory cgroup limits, so their wall times are not equivalent end-to-end benchmarks. Original tool outputs that were already truncated cannot be recovered. The model API reported gpt-6-astra/high; an immutable backend revision was not recorded.

## Candidate behavior and attribution

公开边界是带有效层配置的真实 factory construction 和 apply，在 ambient config 缺失或冲突时仍按层配置完成 profile/forward，保留真正缺少配置时的告警以及正确 CUDA 数值输出。NoEP prepare/finalize 提供本地 expert 输入；跨卡 all-to-all 不决定这个配置生命周期问题，没有把它伪装成完整分布式 serving 测试。

agent 把仅经 apply 调用的 modular wrapper 从 CustomOp 改为普通 Module，避免 wrapper 初始化无故查询全局 compilation config；factory 把真实 old_quant_method.moe.moe_parallel_config 传给 kernel。profile workspace 由绑定的层配置决定，独立构造 kernel 时仍保留原 ambient fallback。两个生产文件与新增自测已完整检查。未删除通用告警、未篡改 Torch 数值或 profiler，也未通过替换 fixture 掩盖 wrapper 行为。

原评分及本轮使用的 fixture 都调用真实 FusedMoEModularMethod.make 和返回对象的 apply，正常构造 UnquantizedFusedMoEMethod，不访问特定内部 wrapper storage 名称。实际 CUDA workspace 观测区分 DP+EP 与普通层；数值由父进程持有的输入独立计算，允许真实 FP16 GEMM/激活舍入区间。独立 challenge 更换为 6 tokens、hidden 96、intermediate 160、8 experts、top-k 3、DP=4，验证生命周期、真正缺配置告警以及双向 owner 冲突。该 challenge 的有限数值检查不能单独证明数值正确，正式父进程的四组数值比较另行核对。
