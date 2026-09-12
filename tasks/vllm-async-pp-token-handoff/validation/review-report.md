# Async PP task review

题目可以保留，1.4.0 的 Worker/executor 边界修复已通过运行验证。10/10 项已评分，总分 20/20；无未验证项或已知阻塞项。评分只表示下面记录的任务范围和验证证据，不表示穷尽所有实现。两次未修改的 Astra 原产物均为 1 分，19 组启用对照全部符合预期，Harbor Oracle 为 1 分且零异常。题面、参考解和镜像未变。

| # | 检查维度 | 得分 / 状态 | 关键依据或缺口 | 下一步 |
|---|---|---|---|---|
| 1 | 题目真实吗、清楚吗？ | 2 | 用户确认的单机 mp、PP=2、普通解码和 chunked prefill 需求 | 保留题面 |
| 2 | 是否独立于原 PR？ | 2 | 按输入、输出、推进和生命周期定义正确性，没有指定 Oracle 的函数、容器或协议 | 保留范围 |
| 3 | 环境能解题吗？ | 2 | Base、镜像和依赖锁未变；两张 GPU 上实际完成 Worker 初始化和模型执行 | 已验证 |
| 4 | 题面与测试双向对齐吗？ | 2 | semantic-boundary.md 映射全部行为；空轮次遵循真实 EngineCore 调用顺序，允许 activation 元数据通信 | 已验证 |
| 5 | 测到了真正的执行过程吗？ | 2 | GPU 行为经过真实 mp executor、Worker、模型输入；另有四种模式的完整生成闭环 | 已验证 |
| 6 | 不同的正确实现能通过吗？ | 2 | 五种替代实现通过，分别改变存储、P2P/私有 helper、调度元数据、接收位置和 activation 元数据接口 | 已验证 |
| 7 | 错误实现能被准确拒绝吗？ | 2 | 13 个错误或作弊对照均为 0，实际拒绝原因逐一记录 | 已验证 |
| 8 | Oracle 本身可靠吗？ | 2 | 同一冻结源码的直接入口和 Harbor 均为 1；独立 GPU 输入与 Transformers 输出对照通过 | 已验证 |
| 9 | 评分结果可信吗？ | 2 | 完整伪造报告仍被独立 GPU 核验拒绝；提前退出和复制参考结果反例被拒绝 | 已验证，保留下面的安全范围说明 |
| 10 | 验收能复现、交付说清楚了吗？ | 2 | 最终源码、归档哈希、严格静态审计和暂存范围审计全部通过；同一分支发布范围明确 | 已验证 |

## Task and environment

The contract is request admission -> real scheduler -> mp executor and Worker -> runner, activation transport, sampling and NCCL token handoff -> next model input -> collected output and completion. The frozen Base is 8ebf372e9d612a325f54aadf5c0c3c6588b6afa3; the image and dependency cutoff remain unchanged. The task supplies no candidate-visible verifier, Oracle or curated reproducer. Evaluation uses two GPUs and no network. The separately requested model trials used host networking and are not evidence of cutoff-isolated solving.

## Reproduced boundary defects and repairs

Astra rruzoCB originally failed because hand-built scheduler output omitted sampled_token_positions. Version 1.3.1 fixed that producer boundary and accepted the unchanged submission. UyTdvKx then exposed another defect: it receives tokens in Worker.execute_model after forwarding activations. Direct runner calls bypassed this behavior and left a legitimate GPU send unmatched. Its separate real mp diagnostic passed all four modes, but that alone did not establish a complete passing score. Both original submissions now pass the complete repaired entrypoint, with every changed production and test file checked against the saved artifact before evaluation.

The new GPU driver creates the real LLM engine, scheduler, mp executor and Worker processes. It submits complete schedule outputs through execute/sample and returns actual collected outputs to the scheduler. No runner is manually constructed or invoked by the fixture. Task probes control valid logits and observe model forward inputs while retaining model execution, Worker dispatch and activation transport. Requests, warmup, collection, completion and cleanup use real lifecycle transitions. Reordering stimuli use the frozen InputBatch swap operation, while assertions compare subsequent model inputs by request identity rather than an Oracle map or sentinel.

The new metadata alternative reproduced a separate false rejection: replacing activation metadata serialization with equivalent send_object_list/recv_object_list preserved the actual input but triggered the broad CPU-object observer. CUDA checks still cover Worker execute/sample; object restrictions apply at sampling, and ordinary CPU activation metadata remains allowed. This alternative now passes the full entrypoint. Empty steps follow EngineCore and do not dispatch sample_tokens; the last-rank negative is injected into the reachable empty Worker execute path instead of requiring an extra sampling call. The prefill gate holds logits production until the earlier stage consumes its next GPU input, and permits implementations that skip discarded logits entirely.

## Behavioral coverage and trust

Both PP endpoints load candidate code. A root-owned observer supplies fresh sampled values and compares subsequent GPU inputs on separate observation groups, without prescribing the candidate's PP wire protocol. Explicit and implicit CUDA waits are observed throughout Worker execution. Events recorded before model forward, or in a completed empty round, may guard prior input-buffer reuse; recording the event again invalidates that temporal exemption. Task-owned input inspection is excluded while candidate calls remain observed.

The ordinary LLM E2E retains real weights, attention, KV cache, sampling and the engine loop in async/sync × PP=1/2. Independent Transformers execution supplies expected sequences. Its async PP=2 executor gate requires another step for the same request to be submitted before earlier worker work is released. All positive runs finish each workload and serve a fresh request. The contract-to-case map, substitutions and control meanings are recorded in semantic-boundary.md.

The root scorer does not import candidate code. Driver identity, exit status and framing are independently recorded; a GPU suite report alone cannot replace external GPU comparison. The report-only control emits complete, correctly framed reports and is rejected for missing independent GPU behavior. The copied-reference control passes GPU behavior, then fails the actual executor boundary in async PP=2 and protected reference reads with PermissionError in the other three modes. Worker-side Python instrumentation is not a general security boundary against arbitrary malicious rewriting, and the tests retain frozen vLLM subsystem interfaces. These are representative behavioral checks, not a proof covering every possible refactor or workload.

## Final results and interpretation

The frozen worker-boundary-final snapshot passes all 21 runs: two unchanged Astra submissions plus 19 active Base/Oracle/control cases. Oracle and five correct alternatives receive 1; all 13 incorrect controls receive 0. The two production patches extracted from Astra also pass independently. Original raw rewards are preserved; the separate rescore records are evidence/rruzoCB-rescore.json and evidence/UyTdvKx-rescore.json.

The historical Oracle and prompt-loss mutation fail because the next long-prompt input after compaction is 27..34 instead of 57..64. Implicit nonzero and Worker stream-wait mutations produce correct token inputs but violate the no-host-wait requirement. Base omits an eligible request on CPU scheduler reentry; its secondary GPU missing-request exception is not the rejection evidence. The final-rank mutation reaches the production role assertion during empty Worker execution.

The serial executor passes basic, reordered, integrated and compaction checks, then cannot submit the next prefill step while prior logits are held. After that deadline expires, its late step enters failure cleanup and an RPC timeout. It receives 0 before E2E, with a causal progress failure rather than incomplete framing. Some remote Worker exceptions are printed under the generic INFRA_ERROR label; that label alone does not distinguish infrastructure failure from candidate defects. The recorded interpretations use the underlying tracebacks and controlled transitions.

The direct Oracle run takes 558.8 seconds, the two Astra replays 552.1 and 555.9 seconds, and correct alternatives 511.1–562.3 seconds. Harbor 0.22.0 trial task__mAoVBAA receives 1 with zero exceptions and a 553.117-second verifier phase. These measurements share GPU devices 0 and 2; they are not isolated throughput benchmarks. The serial negative takes 450.6 seconds because its invalid progression ends in the existing RPC timeout. All 41 standalone CUDA observer checks pass. No required E2E mode is skipped.

The Harbor task checksum is 4152b12a5e59f1f2933d2788e69beeee233e414c75ccb58ddf07b43a0045c1c5, with image sha256:cf04408e8aed807333ff1522f952182aa7948f2a32e3caeee79dac9b95911e69. The local adapter only allocates the two GPUs and shared memory; task scoring is unchanged. An initial launcher omitted the locally installed Compose plugin configuration and never started evaluation; that setup failure is preserved separately and is not a candidate result.

Runtime files remain byte-identical to the tested snapshot. Documentation and evidence are finalized afterward. Prior 1.3.1 results and superseded development probes are preserved as historical evidence, not certification of this revision. Only this task directory in /tmp/ai-infra-pr75-review is included for publication to codex/async-pp-behavior-hardening.
