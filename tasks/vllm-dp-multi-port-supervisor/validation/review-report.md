# PR 54 task 修复与本地验收

题目可以保留。最终验收结果以 `e2e-evidence.json` 和对应日志为准；本报告不把原 PR 或开发中间版本的通过记录算作最终证据。

语义边界是：公开 CLI 和配置 → 实际 API rank 进程、嵌套子进程、HTTP 探测与信号 → 聚合就绪状态、整个所属进程树及端口释放。模型计算不决定这些行为，因此替换模型客户端和模型相关 HTTP handler；实际 `run_server`、`setup_server`、`run_server_worker` 仍执行。没有宣称完成 GPU 推理、跨节点 LB 或 Kubernetes 集成验收。

## 十维检查

本地验收通过，可继续提交评审。已评分 10/10，18/20；没有未验证维度或本次范围内的阻断项。第 9、10 项各保留一分限制，不代表任意攻击防御或干净主机联网重建已完成。

| # | 检查维度 | 得分 / 状态 | 关键依据或缺口 | 下一步 |
|---|---|---|---|---|
| 1 | 题目真实吗、清楚吗？ | 2 / 通过 | 真实 DP 进程监督请求；去掉目录提示及硬换行 | 无 |
| 2 | 是否独立于原 PR？ | 2 / 通过 | 以生命周期和配置行为定义正确性，Oracle 含额外修复 | 无 |
| 3 | 环境能解题吗？ | 2 / 通过 | agent 离线烟测；完整 Base 历史、源码/native 导入、无答案对象 | 无 |
| 4 | 题面与测试双向对齐吗？ | 2 / 通过 | 逐项覆盖表；含 rank 启动期退出、失败重置、连接断开、正常 serve | 见覆盖边界 |
| 5 | 测到了真正的执行过程吗？ | 2 / 通过 | 实际 CLI、服务入口、HTTP、进程、嵌套 listener 和信号 | 不扩张为 GPU 推理结论 |
| 6 | 不同的正确实现能通过吗？ | 2 / 通过 | 串行 probe 加提前 callable 别名正确实现通过 | 无 |
| 7 | 错误实现能被准确拒绝吗？ | 2 / 通过 | Base 和 7 个错误控制均为 0；对应失败路径见日志 | 无 |
| 8 | Oracle 本身可靠吗？ | 2 / 通过 | 独立嵌套孤儿场景促成修复；最终 Docker 与 Harbor 均为 1 | 无 |
| 9 | 评分结果可信吗？ | 1 / 部分 | 独立父进程完成断言，早退两控制拒绝；worker instrumentation 不是任意代码隔离 | 如需更强对抗模型，另做隔离审计 |
| 10 | 验收能复现、交付说清楚了吗？ | 1 / 部分 | 最终 SHA、镜像、10 组结果及 Harbor 已记录；公网重建未完成、镜像未发布 | 有网络的环境验证默认构建并发布镜像 |

[最终运行记录](e2e-evidence.json) 包含每组得分、耗时及独立资源检查，所有组测试结束后均无残留进程或 TCP listener。Oracle 的两个独立运行分别经过 direct Docker 和完整 Harbor；这不是大样本稳定性证明。

## 修复内容

题面按开发者请求重写，去掉工作目录提示和手工硬换行，直接使用 DP、TP、PP、LB。明确三端点的就绪条件、初次就绪前后的失败计数、配置冲突和完整进程清理；不规定 supervisor 类名、辅助函数、计数容器或进程组设计。

Verifier 改为从公开 CLI 驱动实际服务生命周期，用健康响应、探测次数和时间间隔、进程身份与真实 TCP 连接观测结果。测试自己的收尾清理在候选清理断言之后执行，因此不能替候选完成缺失工作。连接超时和 HTTP 无响应不再被解释为端口释放。测试覆盖与题面依据见 [semantic-boundary.md](semantic-boundary.md)。

Oracle 修复了初次就绪和失败计数混用、无效参数校验以及 rank 已退出时的嵌套进程遗漏。Linux subreaper 负责接管孤儿后代；Python resource tracker 由其自身生命周期管理，避免重复回收。历史 upstream commit 仅作为实现来源，修改后的 Oracle 与其他解法接受同一套检查。

## 对照含义

正确替代实现使用串行探测和提前保存的 serving callable 别名。题面没有规定探测必须并发，也没有规定 import 写法；同一 callable 在正常产品执行中的语义不变，所以这两项应当被接受。

错误反例分别覆盖提前就绪、忽略 probe 参数、错误失败阈值、无效启动遗留监听器、rank 退出后遗留嵌套进程，以及两种成功提前退出。Base 没有新 CLI；提前退出反例必须执行到注入点，但不能凭退出码零获得成功。忽略参数的反例会在本应存活的短失败序列期间提前结束服务；最终异常可能表现为后续观测读取不到 JSON，需结合进程日志判断原因，不能只看 traceback 名称。

## 环境与交付边界

新 worktree 为 `/tmp/ai-infra-pr54-hardening`，分支为 `codex/dp-supervisor-cleanup`，基于 PR HEAD `9cc04b5edbedb60006ab0a4974c0748adb2d4c52`。所有修改仅在该 task 下，尚未提交或推送。主工作区已有的 skill 修改未改动；所用 dirty skill 内容用单独 SHA-256 记录。

环境使用 CPU，因为目标是 Python frontend 的进程监督。设备测试执行 pinned platform 的设备映射 API，使用重排后的 CPU 可见设备列表验证 TP/PP 切片，不声称实际分配 GPU。构建默认保留公开 donor 加指定源码的路线，本次成功路径复用了经过验证的缓存镜像，细节见 [docker-build.md](docker-build.md)。镜像未推送，不把本地 image ID 写成不存在的 registry digest。

评分父进程不导入候选，执行必需断言后才写 reward；子进程早退无法替代这些检查。模型边界 instrumentation 位于包含候选代码的 worker 中，它不是抵御任意代码篡改的隔离沙箱。当前可信度结论限于已执行的行为及反例，不能据此宣称对所有攻击免疫。

## 最终运行结果

| 实现 | 预期 | 实测 | 秒 |
|---|---|---|---|
| base | 0 | 0 | 45.88 |
| oracle | 1 | 1 | 320.38 |
| sequential-probes-and-callable-alias | 1 | 1 | 311.85 |
| ready-before-children | 0 | 0 | 32.79 |
| ignored-probe-options | 0 | 0 | 79.5 |
| wrong-failure-threshold | 0 | 0 | 88.62 |
| invalid-start-listener-leak | 0 | 0 | 223.58 |
| orphaned-engine-process | 0 | 0 | 43.36 |
| systemexit-success | 0 | 0 | 45.95 |
| os-exit-success | 0 | 0 | 45.86 |

Harbor：1 个完成 trial，0 个 error，reward=1。开发过程中发现并修正了断连时 HTTP 客户端自动重试导致的请求次数误判；最终断连场景只要求真实失败发生并停止整个组，精确逻辑失败阈值由非 200 响应场景验证，避免锁定客户端重试策略。
