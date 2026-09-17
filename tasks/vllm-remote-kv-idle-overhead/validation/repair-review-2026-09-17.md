# PR61 修订审查：v1.3.0

选题保留；本提交修复已证实的 fixture、Oracle、覆盖和环境问题，**不宣布最终合格**。已评分 7/10，小计 14/14；第 3、9、10 维未完整验证，整体分数待定。未完成的审查不由已有通过率替代。

| # | 维度 | 状态 | 证据或缺口 | 下一步 |
|---|---|---|---|---|
| 1 | 场景真实清楚 | 2 | 保持开发者题面和 A/B/C 可观察例子 | 不增加答案提示 |
| 2 | 正确性独立于原 PR | 2 | 队列表示、helper 和修复位置不指定 | 按行为评判 |
| 3 | 环境可解性 | U | 最终 CPU 镜像可完成 Harbor；普通 LLaVA metadata 已补，非全库依赖覆盖 | 复查后续 fresh Agent 环境错误 |
| 4 | 题面与测试双向对应 | 2 | 真实 streaming 输入替代私改状态；混合 idle/续传均来自公开等待、顺序和生成合同 | 保持映射 |
| 5 | 行为决定路径真实 | 2 | Request→真实 scheduler→worker/connector 输出→client tokens | 不扩称 HTTP/RDMA 全链路 |
| 6 | 接受不同正确实现 | 2 | 独立 remote 队列 Oracle 与 linked-list/ready-heap 替代均 13/13 | 增量审查其他解法 |
| 7 | 错误实现因目标行为失败 | 2 | Base 线性 idle、旧替代 mixed idle、旧 Oracle 续传饥饿、丢输出控制均失败 | 见机器记录 |
| 8 | Oracle 独立挑战 | 2 | 无远端完成事件仍应恢复 streaming 的新挑战揭示旧 Oracle 错误，已修 | 保留旧 Oracle 负例 |
| 9 | 评分可信度 | U | 既有提前退出控制实际 Harbor 拒绝；同进程可变依赖线索未验证，相关新探针未执行 | 另行完成可信边界审核 |
| 10 | 验收可复现与交接 | U | 12 个最终镜像 Harbor 控制及哈希可复核；fresh DeepSeek/GPT 和总体审核未完成 | 不标 merge-ready |

## 身份和审查范围

- task v1.3.0，Base `d88f28da05b12bc7d63ebe3dcedf445ecb274343`，cutoff `2026-03-10T15:03:18Z`。
- 镜像 `sha256:fd59b9b0cbbc1c4d5400d97e1eaeb1cdd4640f71983c9a5581b84449743ac88c`；CPU，无 CUDA 声明。
- 使用 task-review skill 的冻结修订 `b40002e149e5d2e0896ca2cc3573a84f1f0b4091`；本次是已诊断问题的功能修订，不是完成了全新全量安全审核。
- 原始 h1 Agent 使用 v1.2.1，其 reward `[1,1,0]` 不改写、不作为 v1.3.0 的新模型实验。r03 是 fixture 假阴性；r02、r03 最终代码在 v1.3.0 的直接评分重放均通过，但重放不是新 Harbor Agent trial。

## 修复及行为映射

| 合同 | 真实触发及观察 | 检查 |
|---|---|---|
| 无远端事件的 idle 不随 blocked 人口线性增长 | 24/384 remote pending；真实 schedule 时间中位数比例 | idle-scaling |
| 其他等待原因共存不破坏优化 | 真实 segment 结束进入 stream wait，再保持远端 pending | mixed-idle-scaling |
| 可运行请求保持 FCFS | 真实 FSM Future、远端完成输出、stream add_request 事件；按 request ID 看调度顺序 | mixed-fcfs |
| streaming 不依赖无关远端完成 | 3/37 remote pending；连续两段输入输出 43/44，再取消 | streaming-resumption |
| 完成、取消及竞态仍正确 | completion、abort、late completion、ready race、staggered events | 对应既有五组检查 |
| 普通生成、背压、后续接入和无 connector 回归 | schedule→update_from_output→client tokens/terminal output→新请求 | generation-lifecycle、ready-backpressure、no-connector-regression |

旧 mixed-FCFS 测试直接把 streaming status 改为 WAITING，绕过事件驱动实现所依赖的真实输入，因此拒绝了合理解法。现在用正常输入和输出生命周期，未在题面暴露内部原因。

旧“正确替代”只优化全部为 remote wait 的情况，混合场景仍线性扫描，改列 `all-remote-only-shortcut` 负例。旧 Oracle 的混合队列选择可能永远无法恢复 streaming，保留为 `historical-oracle-starves-stream`。新 Oracle 将 remote event-only 等待与需轮询的等待分开，FCFS 使用稳定入队次序，正常释放时清理次序记录。它不是复制 Agent r03 的 ready-heap 解法。

`event-ready-heap-alternative.patch` 来自本次探索性 r03 的完整 tracked 最终补丁，公开标明来源；它不是独立 held-out 样本。不能用其通过估计新模型通过率。

## 实际验证与限制

最终 v1.3.0 镜像的普通开发路径复验：以镜像默认 agent 用户、`--network none --runtime=runc` 执行 `python -m pytest tests/v1/core/test_scheduler.py -q`，91 passed、1 skipped，耗时 37.14 秒。没有挂载 curator 的测试或缓存。见 `repair-upstream-smoke.log`；这一结果不等同于全部 upstream 测试可用。

`repair-calibration-2026-09-17.json` 保存 12 个真实 Harbor 控制的预期/实际 reward、完成项、trial ID、输入和结果哈希。Base=0；新 Oracle=1、ready-heap 替代=1（均 13/13）；其余负例=0。Base idle 比例 13.19；旧替代 mixed 比例 12.55；旧 Oracle 明确因 streaming continuation stalled 失败。不是只看退出码就认定控制合格。

题面门保持；环境为有界验证；普通行为 verifier 修订已验证，但评分可信度尚未完整审核，最终门禁未批准。相关受阻探针没有重试，也没有据源码怀疑宣称复现 P0。r02 候选可能长期保留已完成 Request 的引用，目前仅静态疑点，不翻分，也不新增绑定其私有 heap 表示的断言。该资源生命周期问题需要独立行为证据后再决定评分合同。

更早的 `instruction-e2e-*`、`isolated-image-calibration-*` 与旧 rollout 文档保留历史意义，不能替代本次结果。Harbor 输入 checksum 对应写入最终证据文档之前的快照；证据和说明更新不改变被执行的题面、环境、Oracle 和 tests。完整原始产物在 curator campaign `deepseek-ten-per-task-20260916/next-iteration/controls/`，本仓提交精简可核验记录，不提交凭据或候选完整仓库。
