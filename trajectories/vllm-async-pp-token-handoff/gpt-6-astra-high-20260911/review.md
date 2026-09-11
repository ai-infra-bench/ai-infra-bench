# Rollout review: vllm-async-pp-token-handoff v1.2.4

One original GPT-6-Astra / high attempt: reward 1, no Harbor exception. All 58 ATIF steps were read and the final candidate was checked using its complete pre-verifier filesystem snapshot. No blocking task or candidate defect was found.

Independent five-request and seven-request handoff scenarios passed on both ranks. All five formal replay stages passed; reward: 1. Final agent-authored tests were also checked separately as supplementary diagnostics.

The review used [ai-infra-bench-rollout-review](https://github.com/ai-infra-bench/ai-infra-bench/tree/b989bc67e2b945c3be00d548ca25b1f73519f478/.agents/skills/ai-infra-bench-rollout-review). The [audit](review/final-audit.json), [capture checks](review/capture-audit.json), [replay record](review/replay-record.json) and [complete diagnostic logs](review/replay-evidence.tar.gz) accompany this report. Prior Oracle and alternative/control evidence was reused after exact file comparisons; no new solver run was made during review.

Diagnostics used restored snapshots on A100 GPUs with read-only tests and no external network. They did not impose the original CPU/memory cgroup limits, so their wall times are not equivalent end-to-end benchmarks. Original tool outputs that were already truncated cannot be recovered. The model API reported gpt-6-astra/high; an immutable backend revision was not recorded.

## Candidate behavior and attribution

公开边界是两端真实 runner 初始化和 execute_model，随后 sample_tokens 经真实双 rank NCCL 交接 GPU token，更新 retained/discarded 请求、placeholder、下一轮 GPU input，并允许 scheduler 在有在途 placeholder 时继续调度。固定小模型的 hidden/logits/采样输入替代权重与 attention 算术；runner 初始化、执行状态、InputBatch、NCCL、bookkeeping 和下一轮消费均实际执行。

agent 在真实 execute_model 路径设置早期 rank 的待采样状态，sample_tokens 用 GPU int32 broadcast 接收，并共用生产缓存逻辑更新映射和 placeholder；移除 scheduler 对在途 placeholder 的一概跳过，同时令 async PP 不再依赖 scheduler 回传 CPU token。最终还保留 external_launcher 原有 logits 分发和各 rank 本地输出路径。两个生产文件及新增两卡诊断测试均已检查。自测中的 SchedulerConfig 和 block table 初始化错误已在轨迹中修正，不能归因为 task fixture 故障。

v1.2.4 的 task fixture 通过真实构造与 execute_model 获取状态，没有硬塞某个答案专用的 pp_async_broadcaster 或 pending 字段。观察器检查阻塞 D2H、CUDA 标量读取和显式 host wait；允许最后 rank 的正常 non-blocking 输出拷贝。原始三个 NCCL 场景的 receiver 均无 transfer/violation，sender 只有合法 non_blocking=true 的输出拷贝；三个场景、配置和 scheduler 共五阶段均完整。

独立 challenge 使用 5/7 个请求、交错丢弃、重排、不同 prior outputs，并实际消费下一轮 GPU input，两个 rank 都必须返回完整记录。另有一个证据细节：agent 最后的缓存 tensor data_ptr 断言在原自测进程已加载文件后加入。该断言属于 agent 自测，不是新增评分要求；本轮单独运行归档中的最终四阶段自测以核实，结果与独立 challenge 分开记录。

The supplementary configuration test initially timed out before workers started because the restored review container lacked a hostname loopback mapping. After correcting that mapping, configuration passed with the same final candidate; all four supplementary phases passed across the recorded runs. Both the initial result and retry are preserved in the diagnostic archive.
