PR #74 · vllm-fused-moe-config-lifecycle v1.2.9：可保留，本轮修改通过本地 task-review 三个 gate。10/10 维已评分，19/20，无未验证维度或已知阻断；第 9 维为明确的非阻断范围限制。

| # | 维度 | 分数 / 状态 | 关键证据 | 下一步 |
|---|---|---|---|---|
| 1 | 真实性与清晰度 | 2 | 自然开发请求，明确兼容边界；未增加固定段落要求或暴露私有实现。 | 完成 |
| 2 | 正确性独立于来源 PR | 2 | 公开契约决定行为，不按 Oracle 的函数名、属性名或布局评分。 | 完成 |
| 3 | 环境可解性 | 2 | 沿用已核验冻结镜像；逐次非 root agent GPU canary 和正式 Harbor 验证。 | 完成 |
| 4 | 题目与测试双向对齐 | 2 | 保留六次冷构造、36 次生命周期数值、四次大 forward 和交错检查；新增真实构造的普通层，在两种整体配置下连续 profile/forward/profile。 | 完成 |
| 5 | 执行真实行为路径 | 2 | 真实 CUDA/Triton 运算；新增场景运行真实构造函数、factory、apply 和显式局部 forward context。 | 完成 |
| 6 | 接受不同正确解 | 2 | quant-owner、不同内部存储、额外 workspace 查询、复用、packed arena 和按调用释放六类替代解均通过。 | 完成 |
| 7 | 正确拒绝错误解 | 2 | Base、新增行为负例和已有不完整实现均被完整评分拒绝，原因见逐次原始报告。 | 完成 |
| 8 | Oracle 独立验证 | 2 | 独立 challenge 使用不同输入与尺寸；显式尺寸 challenge 使用 DP=3 的整体配置及真实路由，正式测试使用 DP=2。 | 完成 |
| 9 | 评分可信性 | 1 | 父进程独立计算数值参考并决定 reward；成功早退及既有报告控制被拒绝。设备测量仍与候选同进程，不声称任意篡改防护。 | 非阻断范围限制 |
| 10 | 可复现与交付 | 2 | 最终快照 24 次 Harbor、12 项 challenge 符合预期；最终 Oracle 后置运行。 | 完成 |

明确层构造参数覆盖整体配置。新增用例由真实 FusedMoE 构造函数产生配置关系；修正 Oracle 与派生替代解。旧 engine-config reference 保留为负例；旧 config-wrapper 的错误归类已纠正，历史得分不改。

Gate 1：题目契约沿用已审版本。Gate 2：从提交 `ea479f076c71af9ce725700cc86ab307fc38a81d` 的 Dockerfile 重建镜像，核验 exact Base、隔离 Git 历史、非 root import 路径和 GPU canary。Gate 3：在新镜像上运行 Base、Oracle、全部声明控制及独立 challenge；最后再运行一次 Oracle，所有入选 Harbor 运行均无异常。

最小语义边界及允许替代见 [semantic-boundary.md](semantic-boundary.md)；冻结文件哈希、镜像、job/trial ID、GPU、命令与原始日志见 [e2e-evidence.json](e2e-evidence.json)。完整本轮证据目录：/data/yinchen/pr73-pr74-image-refresh-20260917。

三份历史 Sol 曾在前一冻结环境中原样重放（round → 新评分）：3 → 1, 4 → 0, 7 → 1。该诊断不是本轮新镜像运行，也不是新模型解题，不覆盖历史 reward。中间一份因跟随整体配置、扩大普通层预留而失败；另外两份通过全部七个阶段。

本轮重新构建并核验镜像，没有运行新模型、提交或推送。旧 publication-oracle.tar.gz、history 和 candidate replay 是此前版本的记录，不作为本轮镜像接受证据；当前矩阵、challenge 和最终 Oracle 原始产物位于本轮证据目录。CPU 数值参考与 GPU 的允许误差按既有规则执行；比较浮点数使用联合相对/绝对容差，不把绝对误差单独与 atol 比较。
