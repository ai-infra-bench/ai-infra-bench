PR #73 · v1.2.8 adds implementation-independent FP32 launch-scaling coverage and a targeted serial-FP32 negative control. The instruction, environment, Oracle, numerical checks, performance thresholds, and launch-count comparison rule are unchanged. Current executable hashes and CI reproduction details are in [e2e-evidence.json](e2e-evidence.json); acceptance of this revision is determined by its GitHub `Task validation` check. No new GPU results are claimed in this document. The report below describes v1.2.7 only; its results are preserved in [history/1.2.7-before-fp32-launch-coverage.json](history/1.2.7-before-fp32-launch-coverage.json). The new coverage does not address candidate-process observation forgery.

---

Historical review — PR #73 · vllm-deterministic-bmm-batch-scaling v1.2.7：可保留，本轮修改通过本地 task-review 三个 gate。10/10 维已评分，19/20，无未验证维度或已知阻断；第 9 维为明确的非阻断范围限制。

| # | 维度 | 分数 / 状态 | 关键证据 | 下一步 |
|---|---|---|---|---|
| 1 | 真实性与清晰度 | 2 | 自然开发请求，明确兼容边界；未增加固定段落要求或暴露私有实现。 | 完成 |
| 2 | 正确性独立于来源 PR | 2 | 公开契约决定行为，不按 Oracle 的函数名、属性名或布局评分。 | 完成 |
| 3 | 环境可解性 | 2 | 沿用已核验冻结镜像；逐次非 root agent GPU canary 和正式 Harbor 验证。 | 完成 |
| 4 | 题目与测试双向对齐 | 2 | 19 组正确性、9 类输入错误；额外 RHS 按左侧 batch 截取，空 LHS 拒绝；原有长 K、逐位一致、out 和性能检查保留。 | 完成 |
| 5 | 执行真实行为路径 | 2 | 真实 CUDA/Triton 运算；额外 RHS 用独立数值参考和实际 out copy 验证。 | 完成 |
| 6 | 接受不同正确解 | 2 | persistent、copy-compatible 和 split-reduction 替代解均通过。 | 完成 |
| 7 | 正确拒绝错误解 | 2 | Base、新增行为负例和已有不完整实现均被完整评分拒绝，原因见逐次原始报告。 | 完成 |
| 8 | Oracle 独立验证 | 2 | 独立 challenge 使用不同输入与尺寸；原始三个性能门槛及计时协议不变。 | 完成 |
| 9 | 评分可信性 | 1 | 父进程独立计算数值参考并决定 reward；成功早退及既有报告控制被拒绝。设备测量仍与候选同进程，不声称任意篡改防护。 | 非阻断范围限制 |
| 10 | 可复现与交付 | 2 | 最终快照 21 次 Harbor、8 项 challenge 符合预期；最终 Oracle 后置运行。 | 完成 |

明确保留 batch 数量的基线兼容边界，修正 Oracle 和受影响替代解；保留旧 Oracle，并增加只拒绝额外 RHS、只接受空 batch 的独立负例。

Gate 1：题目契约沿用已审版本。Gate 2：从提交 `c772d6572a15f0f21b10eadc9327947b2225cea2` 的 Dockerfile 重建镜像，核验 exact Base、隔离 Git 历史、非 root import 路径和 GPU canary。Gate 3：在新镜像上运行 Base、Oracle、全部声明控制及独立 challenge；最后再运行一次 Oracle，所有入选 Harbor 运行均无异常。

最小语义边界及允许替代见 [semantic-boundary.md](semantic-boundary.md)；冻结文件哈希、镜像、job/trial ID、GPU、命令与原始日志见 [e2e-evidence.json](e2e-evidence.json)。完整本轮证据目录：/data/yinchen/pr73-pr74-image-refresh-20260917。

三份历史 Sol 曾在前一冻结环境中原样重放（round → 新评分）：1 → 0, 3 → 0, 6 → 0。该诊断不是本轮新镜像运行，也不是新模型解题，不覆盖历史 reward。第一份仍存在 FP32 精度缺陷；另外两份与本轮明确后的兼容边界不同，不能反向把此前的歧义算作新增能力失败。

本轮重新构建并核验镜像，没有运行新模型、提交或推送。旧 publication-oracle.tar.gz、history 和 candidate replay 是此前版本的记录，不作为本轮镜像接受证据；当前矩阵、challenge 和最终 Oracle 原始产物位于本轮证据目录。CPU 数值参考与 GPU 的允许误差按既有规则执行；比较浮点数使用联合相对/绝对容差，不把绝对误差单独与 atol 比较。
