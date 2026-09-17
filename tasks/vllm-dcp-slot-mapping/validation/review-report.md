# PR #60：FlashInfer DCP 修复与校准（v1.7.0）

选题保留。本轮修复旧 Oracle 的 FlashInfer 缺陷及真实 CUDA 数值覆盖遗漏，最终 13 个普通功能控制均符合预期，Harbor 无 errored trial。Oracle 与两个合理替代实现均完成 17/17；Base 与另外九个功能反例均因实际行为错误得到 0。功能门禁通过，允许后续授权的新模型实验；不是完整任务合入批准，不把旧版成绩当作本版成绩。

## 修复内容

题面仅补充部署会选 FlashAttention 或 FlashInfer，不公开内部字段、函数、文件或修法，不提供公开复测脚本。原有 V2、DCP、batch 变化、cache-block 边界、eager/graph 与非DCP保留要求不变。此范围澄清从 v1.7.0 起生效，旧版模型结果不追溯改判。

旧 FlashInfer 先按全局序列长度计算页面数量，再转换 CPU 长度，且读取旧 interleave 配置。真实 decode 内核因此消费错误页面长度。v1.6 Oracle 没有修改该后端。新 Oracle 让页面规划使用本地长度及现行配置；prefill 使用 CPU 长度副本，避免修改共享输入。原有 FA graph 与 V2 修复保留。

## 行为与测试对齐

| 公开要求 | 输入与执行边界 | 可观察断言 |
|---|---|---|
| DCP 分片后仍正确 | block16/32，rank0/1，interleave1/2 → 真实 FlashInfer builder/native decode | 每个 head/dimension 的 attention 数值符合独立均值 |
| 跨 cache-block 后正确 | 两请求连续增长，跨逻辑 block 边界 | 原生 CUDA 结果持续匹配各自缓存 |
| 请求移动与替换 | decode 行交换；A 结束后 C 替换；再次换位 | 每请求结果不串用旧页面 |
| CUDA graph 下同样正确 | 首步捕获，后续重新规划并重放同一 graph | 更新的页面和末页长度真实影响输出 |
| 非DCP不回归 | FI DCP1 eager/graph，已有 FA 与 Eagle 用例 | 输出及 draft tokens 正确 |
| V2 及槽映射正确 | 保留生产 runner/cache manager/sampler 的八步生命周期和 slot kernel 检查 | 精确 slot 与按请求关联的 token 结果 |

新增 FI 部分共 12 组 × 5 步 = 60 个数值步骤，每步两个请求；它们形成两个新增检查点。完整评分要求 17/17 检查点完成，不是进程返回 0 就成功。

另有不计分的独立 Oracle 挑战：mixed prefill/decode、两个 block size、两个 rank，共四组 20 个本地 prefill context 数值步骤通过。该诊断访问 Base 现有 context wrapper，只用于补充证据，不把私有表示要求加入评分，也不冒充完整分布式 prefill。首版探针在 config context 外查询 layout，属于探针错误；修正后的 v2 与首版记录分开保存。

## Fixture 与实现自由

所有配置经 Base 生产类构造。模型配置 head128、FP16、两个 decode 请求、query_len=1；长度和块分配足够且合法。当前 token 的 slot 按 rank ownership 构造。预填充 K/V 表示完成 prefill/当前写入后的缓存，未被本步使用的区域可保留任意旧内容。Q=K=0，使输出成为有效本地 V 的算术均值；预期从位置逐个枚举归属计算，不调用候选 helper。

测试不读取候选源码，不断言新增方法/字段、内部容器、紧凑表宽或修复位置。两种既有不同 runner buffer 方案作为正确替代控制；旧 Oracle、只改 interleave 却保留全局页数、只改页数却读取旧 interleave、旧 FA graph 和非DCP Eagle 回归作为不同的功能反例。通过 reward 并不能单独证明替代实现全局正确；这里依据其代码中的长度/缓存更新与实际 CUDA 结果给出限定判断。

## 身份、证据与范围

| 最终 Harbor 控制 | Reward | 已完成检查点 | 第一因果结果 |
|---|---|---|---|
| Oracle、input-buffers 替代、persistent-backend-buffer 替代 | 各 1 | 各 17/17 | 完成所有检查，FI 各 60/60 步 |
| Base、不完整修复 | 各 0 | 各 2/17 | DCP slot 地址/归属错误 |
| 历史 Oracle（无 FI 修复）、仍用全局页数、旧 backend-context-buffer 答案 | 各 0 | 各 14/17 | FI 数值最大差 0.029296875 > 0.001 |
| 页数已本地化但仍读取旧 interleave | 0 | 14/17 | FI 数值最大差 0.00189208984375 > 0.001 |
| 旧 alternative、旧 explicit-capture、历史 FA backend | 各 0 | 各 11/17 | graph 输出 0，而正确 context 为 0.61328125 |
| 非DCP Eagle 回归 | 0 | 13/17 | draft `[[1,0],[1,0]]`，预期 `[[1,6],[1,9]]` |

三个正对照的新 FI 用例最大观测误差均为约 0.00008138，低于容差。失败不是 missing dependency、构造参数不兼容、未完成报告或仅仅进程异常；首个实际语义断言及完整评分日志保留。较早 `harbor-v1` 13 个控制也均符合预期，但不代替上表的最终 fixture 证据。

- Base：`be3af2d29e2507f32b2190fe015cd6609b348caa`；cutoff：`2026-02-17T23:18:18Z`。
- 校准时工作树起点 HEAD：`9515aae923e68eb11c7537a6eff2444687f69fae`，包含当时未提交修订；此后发布整理不改变运行文件，发布哈希不冒充当时的执行身份。
- 官方 review/create/rollout-review skill：`b40002e149e5d2e0896ca2cc3573a84f1f0b4091` 的干净 reference worktree；本轮按发现的问题重新打开合同与验证相关 gate，不宣称重新完整执行所有安全审计。
- 环境及语义依赖未改，镜像复用 `sha256:dee094a5fca85bb9d08b507d3d23b12b51d89c31b268bc9431800efed3c961d3`。
- 完整 raw 记录保留在 workspace `runs/pr60-flashinfer-repair-20260917`。最终摘要 `flashinfer-v170-results.json` 和原始评分日志现统一收纳在 [evidence.zip](evidence.zip)；更早记录在 [history/curation-history.zip](history/curation-history.zip)。原始产物仅在实际校准完成后生成，整理没有重跑或改写分数。
- 初始 `gpu-v1`：Oracle 60 步通过；历史 Oracle 在数值断言失败。`harbor-v1` 为更早 fixture，不替代最终记录。`final-v170` 测试已修正合法 slot 地址。之后 Oracle patch 的空白 context 行格式化不改应用后源代码，仍额外执行 `final-oracle-normalized` 完整 Oracle；最终摘要逐项绑定两个 freeze，不伪称所有运行的全目录 hash 一样。

本轮硬件为共享 H20，未复验声明中的 A100。FI DCP 新检查执行本地 builder 和 native kernel/graph；不执行完整 FlashInferImpl.forward、KV 写入、多 rank gather/reduce、NCCL、模型权重推理或 HTTP。保留的 runner/Eagle 用例是互补的组件组合覆盖，不能宣传成整个生成服务的 E2E。

评分监督器未更改，相关安全探针此前受限，本轮不重试或绕过；完整防篡改审核仍未完成。功能控制组通过允许开展授权的探索性 DeepSeek 实验，不等于这些边界已经认证。

## 十维复核（限定范围）

已评分 8/10，小计 16/16；第 3、9 维 U，整体分数待定。历史 Oracle/覆盖缺陷已修复，最终功能控制通过；硬件和评分信任缺口仍保留，不能把本轮功能验收描述为整个任务已完成最终认证。

| # | 维度 | 状态 | 证据或缺口 | 下一步 |
|---|---|---|---|---|
| 1 | 场景真实清楚 | 2 | 明确 V2 迁移、DCP、FA/FI 和正常请求变化 | 保持开发者题面 |
| 2 | 正确性独立于 PR | 2 | 按可观察结果，修复历史 Oracle 而不豁免 | 不追溯改判旧轮 |
| 3 | 环境可解性 | U | H20 实际 CUDA；声明 A100 未复验 | 保留硬件限制 |
| 4 | 题面/测试对齐 | 2 | 上表及合法配置、slot 地址；公开后端范围 | 继续检查新轨迹 |
| 5 | 行为路径真实 | 2 | 生产 builder/native CUDA/graph，保留 runner/Eagle | 不扩大 E2E 宣称 |
| 6 | 接受不同正确实现 | 2 | 两个不同 buffer 管理方案均完整 Harbor 17/17 | 新轨迹继续检验公平性 |
| 7 | 因真实缺陷拒绝反例 | 2 | Base 与九个反例到达真实路径后因数值/slot/token 错误失败 | 保留第一因果失败 |
| 8 | 独立 Oracle 挑战 | 2 | 独立 ownership/均值公式，60 个 CUDA 步骤及图重放 | 结合完整入口结果 |
| 9 | 评分可信度 | U | 不凭 checkpoint 或独立容器宣称防篡改完整 | 另行完成允许的安全审核 |
| 10 | 可复验交接 | 2 | 最终控制、执行前后哈希、镜像身份及原始评分产物均已保留 | 静态审计后冻结新实验；不混用历史结果 |
