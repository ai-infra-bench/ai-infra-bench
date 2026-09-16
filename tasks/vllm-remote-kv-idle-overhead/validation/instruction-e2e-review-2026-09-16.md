# PR61 题面与端到端验证复审（2026-09-16）

## 范围与结论

本轮版本为 1.2.0。逐文件对照官方 `create-task` 和 `ai-infra-bench-task-review`，并按 `ai-infra-bench-rollout-review` 的差分方法重评历史候选；官方参考版本为 `b40002e149e5d2e0896ca2cc3573a84f1f0b4091`。参考已合入 Anthropic inline system、async KV token accounting、CPU offload reset、KV admission thrashing 等任务的具体输入与生命周期测试方式，没有新调用付费模型。

原始 [vLLM #35781](https://github.com/vllm-project/vllm/pull/35781) 是 P/D 分离异步 KV 等待的调度开销优化。上游提供真实服务命令及基准，但其 5% 总体性能提升依赖模型、网络和硬件，不适合作为本 CPU 调度任务的固定评分阈值。本题要求无新远端事件时，idle tick 不随 blocked population 线性增大，并保持调度语义。

## 题面公开什么

使用第一人称描述远端 KV 等待期间 CPU 空转的外部现象。给出三个请求的到达顺序 A/B/C，A/B 等远端、C 可本地执行、B 比 A 先完成传输的具体事件输入。要求 C 继续工作，A/B 在就绪后恢复，维持可运行请求之间的 FCFS、计数、取消和正常生成结束行为。

没有告诉 Agent 用哪个队列、集合、dirty flag、回调或函数，也没有提供公开复测脚本。例子是可重现的事件模型，不伪造毫秒级日志。新测试确实执行这个混合事件过程，而非只把例子写到题面里。

## 新增完整功能路径

| 工作负载 | 检查的用户可见行为 |
| --- | --- |
| A/B 远端阻塞，C 本地请求 | C 在传输未完成时产生 token，A/B 不提前生成 |
| B 先就绪、A 后就绪 | 正确请求恢复，chunked prefill 后持续生成，多请求输出不丢失或串线 |
| 三个远端请求同时就绪，running 容量仅 1 | 等待就绪请求不丢失、不饥饿，按 FCFS 逐个完成 |
| 正在运行时加入新请求 | 旧 ready 请求在先，新请求也最终获得完整输出 |
| 普通无 connector 服务 | 完整生成、结束、计数归零及空 tick 不回归 |

旧有性能规模比、完成事件、取消竞态、混合阻塞原因、计数和顺序测试仍保留。正常生成不再用 abort 代替完成：测试检查真实 `update_from_output()` 返回的逐请求 token 流和 terminal output。总共 11 个认证检查点，不把检查点数量等同于独立测试 case 数。

这是“请求进入 Scheduler → 调度 → 接收 ModelRunnerOutput → EngineCoreOutputs → 结束释放”的子系统端到端。模型 token 和 connector 完成事件用确定性替代；真实 Scheduler、Request、KV 分配管理、采样停止条件和输出封装仍参与。没有宣称跑过 HTTP、NIXL/RDMA 或完整 GPU 模型精度测试。

## 漏测反例与历史候选

新增 `dropped-client-output.patch`：在 Oracle 调度修复上保留所有内部状态更新，但丢弃 `update_from_output()` 的客户端返回。它是正常生成回归，不是格式或函数名检查。旧 verifier 只检查调度状态，新的生命周期必须拒绝它。新旧实际 Harbor 成绩见 `e2e-evidence.json` 的 differential control 字段。

上一轮三份保存的 DeepSeek 候选 QGr8Wd6、kGXSyGd、xfkdqfk 在本轮最终镜像 `/tests/test.sh` 重评均为 1，三份代码都未修改。它们采用不同的队列/视图管理方式，说明新测试不要求特定数据结构。这不是三次新 rollout，也不能证明任意实现或任意场景都正确。

## 十维审查与三道门

| 维度 | 判断 | 依据／剩余风险 |
| --- | --- | --- |
| 1 真实、清晰 | 2 | 开发者描述 idle CPU 问题，附事件输入。 |
| 2 独立于原 PR 实现 | 2 | 只规定性能规模关系与调度行为。 |
| 3 Agent 环境可用 | 1 | hidden 运行正常，但上游 pytest 收集缺少 `tblib`。 |
| 4 题面与测试双向对齐 | 2 | 题面事件被实际执行，保留合理兼容性要求。 |
| 5 真实行为决定路径 | 2 | 使用真实 Scheduler 到客户端输出的完整生命周期。 |
| 6 接受不同正确实现 | 2 | 不同正对照及三份历史候选均能通过。 |
| 7 拒绝错误实现 | 2 | Base 性能回归、取消/顺序缺陷和丢客户端输出反例。 |
| 8 Oracle 验证 | 2 | 最终评分代码实际 Harbor Oracle。 |
| 9 评分可信度 | 2 | 11 个有序认证检查点；提前退出及伪造输出经过完整入口。不是任意 native-memory 攻击的形式化证明。 |
| 10 可复现与交接 | 1 | 同一镜像 ID、运行前 frozen hashes、原始评分日志和版本绑定齐全；上游测试环境缺口已明确。 |

题面门：通过。环境门：hidden 所需路径通过，Agent 上游测试依赖门仍有缺口，不标为全部合格。验证门：以本轮 Harbor 矩阵为准。

## 未掩盖的环境问题

在当前最终镜像中以 `agent` 用户执行 `python -m pytest tests/v1/core/test_scheduler.py --collect-only -q`，得到 `ModuleNotFoundError: No module named 'tblib'`，没有进入测试主体。本轮未临时在线安装依赖来冒充镜像已修复，也未改变镜像 ID。这应作为后续环境修订：加入冻结依赖、重建镜像，再完成 Base/Oracle 和上游 smoke，不能把本轮 hidden 通过说成上游全通过。

完整证据根目录：`ai-infra-bench-workspace/runs/instruction-e2e-20260916/`。`pr61-pre-run-hashes.json` 为运行前清单，`jobs/` 保存实际 Harbor，`saved-replays/pr61/` 为原样历史候选重评。旧轨迹和旧 reward 原封不动保留。
