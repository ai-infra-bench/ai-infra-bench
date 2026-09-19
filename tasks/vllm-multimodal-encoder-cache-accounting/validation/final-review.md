1.4.2 已完成本轮授权的 F1、F2、F4 修复，题目可以保留。题面、Oracle 和镜像没有变化。F3（`disable_chunked_mm_input=True`）及其是否属于兼容性要求的解释，按用户指示暂不处理；没有为它增加评分条件，也没有声称已修复。

本轮 10/10 维度已评估，19/20；第 8 项保留 F3 的待处理说明。这是任务质量评估，不是候选 reward。题面和环境通过，verifier 在本轮明确的修复范围内通过；这份记录不替代 F3 的单独范围决定。

| # | 维度 | 分数/状态 | 关键证据或缺口 | 下一步 |
|---|---|---|---|---|
| 1 | 题面真实且清楚 | 2 | 行数计费、窗口、复用、存储增长要求明确；题面字节不变 | 保留 |
| 2 | 正确性独立于源 PR | 2 | 按行为验证，Oracle 没有特殊豁免 | 保持统一要求 |
| 3 | 环境可解 | 2 | 固定 CPU 镜像、离线 imports 和真实请求路径通过 | 保留固定环境 |
| 4 | 双向对齐 | 2 | F1/F2 的扣分依据回到可观察行为，未加入 F3 条件 | 维护行为对应表 |
| 5 | 真实目标路径 | 2 | 构造、admission、schedule、execute、merge、完成和淘汰真实执行 | 保留完整生命周期 |
| 6 | 接受不同正确实现 | 2 | 21 个正例通过，包括字段改名、Python/NumPy payload、合法元数据及已有 tracing | 保留这些对照 |
| 7 | 正确拒绝错误实现 | 2 | 31 个 Base/负例被拒；空间增长与淘汰泄漏分别验证 | 保留失败原因 |
| 8 | Oracle 独立验证 | 1，部分 | 当前完整评分与独立挑战通过；F3 按指示保留待处理 | 另行确定 F3 范围 |
| 9 | 评分完整性 | 2 | 提前退出、完整伪造报告仍被拒；通道单测通过 | 安全结论限于实测边界 |
| 10 | 可复现与交付 | 2 | 冻结 hash、52 组矩阵、16 个 Harbor trial、修正后的诊断结果均归档 | 发布记录见 PR #84 |

| 修复项 | 原始复现 | 1.4.2 的结果 |
|---|---|---|
| F1：Scheduler 预算字段改名 | 正确实现 reward 0 | reward 1；容量由 admission、live occupancy 和 profiling 行为核验 |
| F1：cache 容量/空槽字段改名 | 原测试会直接读取内部字段 | reward 1；exact-fit、one-short、分配后不足、释放后恢复均通过正常 API 验证 |
| F2：Python payload 随 span 扩张 | 错误实现 reward 1 | reward 0 |
| F2：淘汰后保存 Python 值副本 | 错误实现 reward 1 | reward 0，原因是完成请求后的 host allocation 持续增长 |
| F2：NumPy 值副本泄漏 | 新增表示对照 | reward 0 |
| F2：扩张 payload 但正确淘汰 | 新增分离对照 | reward 0，单独因 span/width 空间增长失败 |
| F2：紧凑 Python/NumPy、mask 元数据、复用缓冲区 | 正确表示自由度 | 均 reward 1 |
| F2：候选提前开启 tracemalloc | 新增测量兼容性对照 | 正例 reward 1，带泄漏的对应负例 reward 0；保留候选已有 trace |
| F4：`/challenge` 路径错误 | IndexError 被当作 Base 预期失败 | 正常定位 `/tests`；Base 窗口挑战通过、容量挑战因真实计费行为失败 |
| F4：缺少支持文件 | 任意退出 1 可能被误认为有效负例 | 结构化 setup/execution error，退出 2，诊断验证拒绝 |

F1 没有加入字段名兼容列表。请求进度也由测试自己的已完成调度记录推导，不再读取 Scheduler 的 request 容器。正常容量场景同时执行完整 item reservation、持有期间资源不足、后续推进和 profiling 的实际 encoder batch。零输出场景通过真实请求不触发 encoder 的行为验证，不固定内部容量的零/一表示，也未在这次修复中扩展为全零最大输出模型的 profiling 执行测试。

F2 保留 Torch backing-storage 观察，增加 tracemalloc 对 Python/NumPy 存活分配的观察。固定输出行数，在 32/4096 prompt span 和 16/256 embedding width 间做差分，允许与 width 无关的逐位置元数据。另一个场景在一组真实 runner 中完成 32 次请求，只清除测试自己的历史记录，再检查候选资源是否持续积累。使用四轮 warmup 和明确的固定/相对余量，允许合法复用及测量噪声。候选已有 trace 时记录区间起点，保留其 trace 状态；仅停止观察器自己启动的 trace。不会禁止 `tolist()`、NumPy、既有 tracing 或某个容器。覆盖仍限于代表性输入、Torch storage 和可被 tracemalloc 观察的分配，不是任意 native allocator 或 CUDA 峰值内存的完整证明。

F4 的独立脚本支持任务目录和 `/challenge` 挂载两种布局。环境诊断提供 `/tests`，并核对唯一的结构化结果、执行阶段和退出状态；replay 工具使用相同的结果校验。没有把本来能通过的 Base 窗口挑战硬改成负例，也不再将路径/导入错误计作功能缺陷。

验证结果：52/52 个固定镜像完整 Docker `test.sh` 符合预期，21 个正例和 31 个 Base/负例；所有正例另外通过独立窗口/容量挑战。16/16 个 Harbor trial 得到预期 reward，0 个 errored trial，包含 Oracle、两个字段改名、紧凑 Python/NumPy、元数据、复用和已有 tracing 正例，以及五个 host-storage 负例和三个完成性反例。9 个 storage observer、4 个 completion channel、4 个 challenge-reporting 单测通过，共 17 个。没有进行新的模型 rollout。

正确解单次 verifier 耗时 42.5–102.6 秒，平均 49.3 秒。未提前开启全程 allocation tracing 的正例为 42.5–59.6 秒，平均 46.7 秒；Oracle 为 44.3 秒，提前开启 tracing 的正例为 102.6 秒。启动、独立挑战和清理不在这些数字内。每次评测为 4 CPU、16 GiB、0 GPU。Harbor 0.22.0 和 Compose 5.5.1 使用已归档的静态离线 Docker adapter；没有把它说成 stock 动态 egress backend。

仓库 validator、Python/shell 语法、可执行文件 hash 对照和严格 artifact audit 均通过；验收审计为 4 项检查、0 errors、0 warnings，发布前增加 staged 范围检查后为 5 项检查、0 errors、0 warnings。评分源码与运行前冻结的文件一致；控制 patch 的发布格式调整见下一段。最终证据和文档在运行后写入，不作为新一轮模型运行或旧版本结果。

发布前的 staged 检查发现五个新对照 patch 的末尾上下文空行触发 Git 空白规则。仅为这五个 patch 补入下一行未修改的上下文；固定镜像中分别应用验收版和发布版后，完整 candidate diff 的 SHA-256 一致。旧运行记录保留原 patch hash，发布版 patch hash 与代码等价证明记录在 `publication-checks.json`；评分源码和候选实际执行代码均未变化。

`local-regressions.json` 保存逐例分数、阶段、失败原因与时间；`e2e-evidence.json` 绑定最终可执行文件、镜像和 Harbor 记录。原始证据见 `evidence/local-1.4.2.tar.gz`、`evidence/harbor-1.4.2.tar.gz`；此前错误 reward 与诊断失败保存在 `evidence/review-counterexamples-1.4.1.tar.gz`。1.4.0/1.4.1 原始归档及历史 agent 分数保留为历史记录。

验收时的工作区为 `/tmp/ai-infra-pr84-review.kxZVcu`，分支 `codex/pr84-verifier-behavior-fixes`，基于 `3602b95a34fa83df490d60b2ab987c3e84e2d33f`；证据中的 `uncommitted` 描述验收快照，后续发布以 [PR #84 的提交历史](https://github.com/ai-infra-bench/ai-infra-bench/pull/84/commits)为准。题面 SHA-256 为 `01a0b5fe1dc0462ffab4ea817d16265d7917a0139b0d383f126dc7fcf599e881`，Oracle 为 `e4304b6ba84cfceabed78677735b077258fe5bc1e85fc985834f9b787b1d47a5`，与评审前相同。镜像保持 `sha256:8d200d6c23d542fb41b456cb55bf5c984b1c467c2020e31fb0e053e120c5f852`。
