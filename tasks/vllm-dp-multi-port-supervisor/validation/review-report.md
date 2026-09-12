# DP supervisor：task 1.2.0 后代清理回归

Task 1.1.0 的改进已提交为 `19226cf`，与原 Codex rollout 的冻结快照一致。随后轨迹复审确认：原 reward=1 的 Codex 答案只清理 rank 进程组，在 rank 死亡后会遗漏独立 session 的后代和监听端口。题面已经要求清理任何后代，本轮只补测试覆盖，不扩大需求或规定实现方式。

## 本轮变化

`detached_descendants` 通过原公共 CLI 启动一个 local rank，作为 global DP=2 中 start rank=1 的合法节点切片。原 engine fixture 可创建独立 session 的真实后代 TCP listener；测试先确认父子关系与活跃监听，再分别触发 ready 后 rank 死亡、startup 中 rank 死亡、startup 中正常 SIGINT。断言在测试自己的 teardown 前检查进程及端口释放。原有继承 rank session 的场景保持不变。

评分不读取候选的 helper、字段、类或 bookkeeping，不要求 subreaper、psutil 或进程组算法。OS session 断言只确认测试输入拓扑成立，不规定候选如何清理。模型计算仍使用已有的受控替代边界，真实 CLI、serving 入口、rank、信号、HTTP 和后代生命周期参与执行；没有新增 GPU 推理或 Kubernetes 集成要求。

`codex-session-only-cleanup.patch` 保存原答案的六个源码、测试、文档和工具改动文件，作为真实缺陷负例。本轮 Docker 回放还叠加了原完整 regular workspace 捕获。原收集缺失部分链接、权限和 repo 外状态，不能声称重建了完整 agent 环境；已核实用于原评分的 vllm regular 文件与捕获一致，native 二进制与 Base 一致。该局限不改变两种 rank 死亡后真实进程和 socket 泄漏的复现。

## 版本与证据

当前 task 版本为 1.2.0，instruction、Oracle、评分 shell 和 image 均未改动。新增用例使评分范围发生变化，因此不能沿用旧版满分作为新版验收。原初审报告、ci cases、e2e 结果和覆盖说明已原样保存在 `history/task-1.1.0/`；原矩阵与 Harbor 日志仍在 `evidence/` 下。本轮记录单独存放在 `evidence/descendants-1.2.0/`，索引见 `e2e-evidence.json`。

本轮先冻结测试、fixture、task、控制 patch、保存答案和运行脚本，再用固定 image ID 在独立 Docker 容器运行完整 `/tests/test.sh`，结束后核验输入哈希。每个容器 4 CPUs、16 GiB、无外网；没有新模型调用。此处复用了已有评分集成，仅增加行为用例，未修改 Harbor 收集或启动路径；本轮是完整 Docker 评分，不冒称新的 Harbor rollout。

完整评分结果如下。Oracle 和替代实现均完成全部六个顶层组及三个新增子场景；Base 因缺少新参数失败，Codex 在通过原 readiness 后由新增后代清理检查拒绝。所有容器在 verifier 收尾后无残留进程或 TCP listener；候选失败前的泄漏已单独记录，不能把 verifier 收尾解释为候选清理成功。原 Codex reward 1 永久保留在历史记录中，新版结果另列。

| 实现 | 原 1.1.0 reward | 新 1.2.0 reward | 新版完整评分耗时 |
|---|---|---|---|
| base | 0 | 0 | 45.84 秒 |
| oracle | 1 | 1 | 379.11 秒 |
| alternative | 1 | 1 | 384.49 秒 |
| codex | 1 | 0 | 95.07 秒 |

## 仍然存在的边界

上一版七个其他错误控制的执行记录属于 1.1.0，不冒充全部重新验证过 1.2.0。新版本的完整评分验收重点为 Base、Oracle、合法替代实现和本次暴露的 Codex 负例。顺序 probe / callable alias 对照与 Oracle 的清理逻辑同源，不能描述为完全独立的第二套清理算法。

当前测试不是任意恶意代码隔离沙箱，也不覆盖所有跨 rank 非对称失败序列、运行期启动故障或普通 serve 配置。离线开发依赖与完整最终状态收集的改进另列后续工作，没有借本轮后代清理扩大修改范围。这里的新增测试来自已审阅答案，属于开发回归，不是新的 held-out 模型能力测试。
