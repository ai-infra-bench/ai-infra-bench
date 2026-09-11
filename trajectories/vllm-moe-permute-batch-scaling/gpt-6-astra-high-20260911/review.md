# Rollout review: vllm-moe-permute-batch-scaling v1.3.2

One original GPT-6-Astra / high attempt: reward 1, no Harbor exception. All 46 ATIF steps were read and the final candidate was checked using its complete pre-verifier filesystem snapshot. No blocking task or candidate defect was found.

14 independent correctness cases and one performance case passed, including the originally delivered native library. Formal replay reward: 1; rebuilt-library latency: 122.163 us, scaling ratio: 2.731, against limits of 250 us and 3.5.

The review used [ai-infra-bench-rollout-review](https://github.com/ai-infra-bench/ai-infra-bench/tree/b989bc67e2b945c3be00d548ca25b1f73519f478/.agents/skills/ai-infra-bench-rollout-review). The [audit](review/final-audit.json), [capture checks](review/capture-audit.json), [replay record](review/replay-record.json) and [complete diagnostic logs](review/replay-evidence.tar.gz) accompany this report. Prior Oracle and alternative/control evidence was reused after exact file comparisons; no new solver run was made during review.

Diagnostics used restored snapshots on A100 GPUs with read-only tests and no external network. They did not impose the original CPU/memory cgroup limits, so their wall times are not equivalent end-to-end benchmarks. Original tool outputs that were already truncated cannot be recovered. The model API reported gpt-6-astra/high; an immutable backend revision was not recorded.

## Candidate behavior and attribution

公开边界是原生 moe_permute 的输入 payload、routing、可选 expert map 和合法专家数，经真实 native build/load/CUDA kernel 输出五个 buffer，并满足 A100 4096-token 延迟 <250 μs、4096/512 比 <3.5。FP8 在这里用于字节存储，未要求 A100 执行 FP8 tensor-core 算术。

agent 删除逐 routed row 重复扫描所有 expert offsets 的路径，改为固定 256 线程的分块 CUB scan，然后按 offsets 直接定位复制行和填充 expert ranges。循环支持跨多个 scan tile，256 不是专家数上限；保留 raw offsets、remote route sentinel、稳定排序及原 optional -1 行为。四个生产 native 文件、新增 164-case 自测和 benchmark 报告已全部检查。

轨迹中第一次 build 缺 CUDA math-library headers，随后用已安装 NVIDIA 包的 include 路径修正。中途重叠 build 写同一日志/cache 导致 Ninja 日志问题，最终已重新构建和安装，并在最终计时前重新完成 164 项 byte-exact 检查。失败属于开发过程，不是最终 scorer 超时或未执行。最终安装库 SHA256 为 334b52ce72088bb77aac7712cd43ebda3d6f25810841d865dde2fbefd323a042；原 Harbor verifier 另行重建并 root-stage 的库为 ed1a87fec30845b95e3c6668ccbe88522aa47c3bdd381bfc8553d0a7c87e29c6，不能把两者混为一个 artifact。

本轮先挑战完整快照里的原安装库，再执行原评分器的真实重建和正式评分。正式正确性有 26 组：18 个 token/alignment 场景及 64/1023/1024/1025 experts × 两种 alignment；后八组核对全部 buffer 和未写区域。独立 challenge 有 14 个正确性场景（含 2049 experts）和一个公开边界上的性能场景。原正式评分的 4096 延迟为 122.532 μs、比例 2.690，独立重放数据另列，不能用 agent 的 119.747 μs 自报值替代原 verifier 结果。
