# PR60 题面与端到端验证复审（2026-09-16）

## 范围与结论

本轮版本为 1.4.0。按官方 `create-task`、`ai-infra-bench-task-review` 的要求逐文件复核，使用 `ai-infra-bench-rollout-review` 的差分方法重放历史候选；所读官方 main 为 `b40002e149e5d2e0896ca2cc3573a84f1f0b4091`。没有重新调用付费模型，候选重评不是一次新 rollout。

对照已合入的 `vllm-anthropic-inline-system-template`、`vllm-async-kv-token-accounting`、`vllm-cpu-offload-reset-inflight`、`vllm-kv-admission-thrashing` 和 `vllm-runner-v2-selection`：值得借鉴的是可理解的输入、用户能观察的行为和完整生命周期，而不是照搬别题的 API 脚本或增加实现提示。

原始来源是 [vLLM #34179](https://github.com/vllm-project/vllm/pull/34179)，属于 Model Runner V2 的 DCP 功能支持。没有把后续 PR 的新功能加入评分。题面不应伪装成某个已实测的 HTTP 错误，也不应复制原 PR 的内部实现路线。

## 题面公开什么

第一人称说明从原 runner 迁移到 V2，希望继续使用 DCP；给出 TP=2、DCP=2、interleave=2 的普通配置片段，以及长短请求交错、旧请求结束后新 prompt 加入的工作负载。要求 eager/CUDA graph 均正确、非 DCP 不回归。

不公开：改哪个文件、增加哪个函数、slot 公式、内部张量字段、Oracle patch、hidden 测试数据或可执行复测脚本。配置是契约示例，已经用于实际验证；不是声称某个线上部署真实发生过的精确日志。

## 这次测试改变了什么

旧 graph fixture 通过检查候选函数签名来补传参数，仍然与实现表示耦合。本轮删除该适配层，使用真实 `ModelConfig`、`GPUModelRunner` 构造、缓存初始化、`execute_model()`、`capture_model()` 和 `sample_tokens()`。候选自行完成数据传递，测试不按候选新增名称帮它补线。

| 用户行为 | 实际评分路径 |
| --- | --- |
| 不同 DCP 配置与长位置正确 | 4 种 size/rank/interleave 组合、2 种 cache group block size、靠近上下文上限的位置；不规定内部表宽 |
| replay 不能使用旧输入 | 同一 CUDA graph 改变请求映射、每请求 token 数、位置与 staged block IDs |
| batched generation 持续正确 | 8 个连续 SchedulerOutput：prefill、重排 decode、跨块追加、完成、插入新请求、容量复用、空 tick |
| 同一修复同时覆盖 eager/graph | 完整生命周期分别走 DCP eager、DCP graph、非 DCP graph |
| 下游真的得到正确结果 | 确定性模型消费真实 forward context 和 attention metadata，经真实 sampler 输出；逐请求比对 token IDs |

这里是子系统端到端，不是多机模型精度端到端。替代的是模型数学、attention consumer、实际 KV 大内存分配和分布式进程组；真实执行的是 runner 请求状态、输入准备、Triton slot kernel、CUDA graph、metadata 到消费端和采样。没有宣称已覆盖多卡 NCCL、HTTP、完整权重推理、所有 attention backend 或 A100。

## 旧候选重评：确实修复了一次误拒

使用上一轮 `pr60-deepseek-v4-flash-r3-enhanced` 的原样保存代码，Python 文件逐个哈希，评分前后不修改候选，通过最终镜像的 `/tests/test.sh` 重放：

| 候选 | 旧原始 reward | 本轮重评 | 解释 |
| --- | ---: | ---: | --- |
| ReK9erk | 0 | 1 | 旧 fixture 手工传入的 buffer 表示与候选真实调用链不一致；新真实 runner 链路完成 11/11 检查，旧失败不能归因于 Agent。 |
| jQwFCvS | 0 | 0 | interleave=2 的真实配置未正确传递到 slot mapping；rank-local slots 与独立期望不符。 |
| sL3ZB4M | 0 | 0 | eager 通过；graph 第一次 decode 的两个请求 token 输出错误，说明缺少正确的 graph 数据更新。 |

原始轨迹和分数不覆盖。新的口径是“旧候选在 1.4.0 上重评 1/3”，不是模型重新做题得到 1/3。历史报告里的 0/3 必须保留版本标注，不可继续当作最终失败率。

## 十维审查与三道门

| 维度 | 判断 | 依据／剩余风险 |
| --- | --- | --- |
| 1 真实、清晰 | 2 | 开发者迁移需求与具体配置，没有虚构精确报错。 |
| 2 独立于原 PR 实现 | 2 | 只限定外部行为。 |
| 3 Agent 环境可用 | 1 | hidden GPU 路径可运行；不把这当成所有上游 pytest 都可运行的证明。 |
| 4 题面与测试双向对齐 | 2 | 配置、batch 变化、graph 和非 DCP 均有覆盖。 |
| 5 真实行为决定路径 | 2 | runner 到 sampler，而非只调孤立 helper。 |
| 6 接受不同正确实现 | 2 | 正对照与原样候选重评；已纠正 ReK9erk 误拒。 |
| 7 拒绝错误实现 | 2 | Base/遗漏 interleave/graph 输出错误均有行为性证据。 |
| 8 Oracle 验证 | 2 | 在最终评分代码上完成真实 Harbor Oracle。 |
| 9 评分可信度 | 2 | 父进程要求 11 个有序认证检查点；提前退出和伪造负对照经完整入口复验。不是任意 native-memory 攻击的形式化安全证明。 |
| 10 可复现与交接 | 1 | frozen hashes、镜像 ID、Harbor 日志齐备；实际 H20 与声明 A100 的差异仍待补验。 |

题面门：通过。环境门：H20 子系统验证通过，A100/完整上游测试就绪证据不足，保留条件。验证门：见 `e2e-evidence.json` 的本版本 Harbor 矩阵，不沿用旧 verifier 成绩。

完整本地证据根目录：`ai-infra-bench-workspace/runs/instruction-e2e-20260916/`。`pr60-pre-run-hashes.json` 是运行前冻结清单，`jobs/` 是 Harbor 原始评分产物，`saved-replays/pr60/` 是历史候选重评及逐文件哈希。环境和模型调用均不含密钥。
