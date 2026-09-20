vllm-fused-moe-config-lifecycle v1.2.10：任务可保留；本轮修复真实层公共接口的 fixture 缺口，GPU 验收待运行。没有把 v1.2.9 的通过记录沿用为新版结果。此前独立 review 发现的观测伪造问题仍未修复，本版不宣称可以合并。

8/10 维已评分，小计 9/16；环境独立运行时复核和新版 Oracle GPU challenge 为 U，总分未定。

| # | 维度 | 分数 / 状态 | 关键证据或缺口 | 下一步 |
|---|---|---|---|---|
| 1 | 真实性与清晰度 | 2 | 题目及原行为边界未改 | 无 |
| 2 | 正确性独立于来源 PR | 2 | 不规定配置存储或 workspace 布局 | 无 |
| 3 | 环境可解性 | U | 环境输入未改；本轮没有指定镜像/A100 | 沿用锁定镜像补正式运行 |
| 4 | 题目与测试双向对齐 | 1 | 用真实层取代缺少公共属性的替身 | GPU 回归 |
| 5 | 执行真实行为路径 | 1 | CPU 已运行真实构造/factory；device 和 apply 为诊断替代 | 验证真实 Triton/容量 |
| 6 | 接受不同正确解 | 1 | 公共属性对照、Oracle、三份已保存模型解均通过 CPU 接口诊断 | 正式 reward 必须均为 1 |
| 7 | 正确拒绝错误解 | 1 | 旧版对照记录保留；新版正式矩阵待跑 | 重跑所有声明负例 |
| 8 | Oracle 独立验证 | U | 已更新 challenge 输入，但没有新版 GPU 结果 | Oracle 与正确替代解 challenge |
| 9 | 评分可信性 | 0 | 候选自报观测的既有绕过问题未修复 | 单独修复评分可信边界 |
| 10 | 可复现与交付 | 1 | 静态检查与局部诊断通过，证据明确标注 pending | 最终 Harbor 验收 |

正式 verifier 与独立 challenge 的 rank-local 输入都改用真实 FusedMoE 构造。只在单设备 transport 边界提供 get_dp_group 的 rank/world_size；有效并行配置、dp_size/use_ep 等公共属性、专家映射、registered Parameters 和量化方法均由生产构造函数产生。rank discovery 替代在 factory 调用前结束，gap/conflict context 检查仍保留。

工厂结果按正常生命周期赋回 layer.quant_method，权重通过 copy_ 加载进已注册 Parameter，避免将普通 Tensor 赋给 Parameter 属性。每次构造使用唯一 prefix，允许同一 owner config 的连续冷构造。没有改数值参考、workspace 容量阈值、七阶段计分要求或题目。

新增 alternate-public-layer-properties 正确对照（期望 reward=1）：工厂把真实 layer 传给 kernel，后者用公共 dp_size/use_ep 属性判断 DP+EP。其他计算与 Oracle 相同。它直接覆盖原先只暴露 moe_parallel_config 的替身所误拒的合法实现。

本轮已执行：

- Oracle、新公共属性对照和三份保存的 Astra 答案，各 10 个 CPU 接口诊断组合，共 50 项通过。调用实际 Base 构造函数和对应答案的 factory，检查 public properties、普通层与 DP=2/4 的多 rank 专家映射、gap/conflict、连续构造和 registered Parameter 原位加载。仅设备分配与 apply 被替代，不能据此声称 GPU 运算、workspace 或完整 reward 通过。
- 任务 validator、主线已有 8 个 CI 兼容单测、Oracle/22 个声明控制共 23 个补丁的精确 Base 适用性检查通过。
- 文件语法、哈希和 task-only 范围检查见 e2e-evidence.json；机械检查不代表正式验收。

目标语义边界、允许替代与输入关系见 semantic-boundary.md 和 fixture-reachability.md。Gate 1 沿用；Gate 2 的构建输入未改；Gate 3 的接口修复已有局部证据，GPU 验证仍待运行，观测伪造 blocker 仍开放。

必须补跑：完整 Base/Oracle/所有声明控制的 Harbor 矩阵、新公共属性正例与三份模型解的 GPU 回归、独立 challenge，以及冻结后的最终 Oracle。此后才能关闭接口问题的正式验收项。不得将 CPU 诊断记为这些运行的完成证据。

v1.2.9 的原始运行记录原样保存在 history/1.2.9-before-real-layer-fixtures.json，原 review 保存在 history/review-1.2.9-before-real-layer-fixtures.md。镜像仍是 sha256:a42e2dad9636b1a70d8b572f3fc57ac8b2141df090dd9f00e19b6e0b61cb0af0，本轮没有重建镜像或重新调用模型。

交付已同步主线 63bfee1：原 PR 的 .gitattributes、CI 兼容改动和网站筛选测试已在主线，当前分支仅新增本任务目录，不再携带任务目录外改动。当前只记录代码与验证快照；提交和 CI 状态以 PR 为准。
