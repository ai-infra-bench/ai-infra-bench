1.4.3 已完成本轮授权的 host 生命周期判定修复。题面、Oracle、镜像和资源要求保持原样；F3（`disable_chunked_mm_input=True`）仍是已注明的暂缓项，本轮没有扩展它的评分范围。

| 对照 | 1.4.2 的问题 | 1.4.3 的结果 |
|---|---|---|
| 64 条有界位置元数据，延迟分配 | 错误 reward 0 | reward 1 |
| 同样的位置元数据，预分配 | reward 1 | reward 1，分配时机不决定得分 |
| 合法位置诊断同时随 hidden width 增长 | 原总量/宽度观察不足以归因 | reward 1，仅记录宽度增长诊断 |
| NumPy 淘汰泄漏加固定 8 MiB 缓冲区 | 错误 reward 1 | reward 0，与未加缓冲区的同类泄漏一致 |

生命周期判定使用匹配的行为实验。宽度 16/256 分别在实际输出 4/8 行下运行，encoder 容量始终为 8 行，prompt 长度、请求数量、身份、顺序、生成预算和分块大小一致；每个宽度对保持相同 mask，行数对照使用合法的不同 embedding 位置。每格完成 32 个真实请求，在第 4、16、32 个完成点记录分配量。所有模型输入仍经过原有的逐步行为核验。

每格先减去自身第一次观测，再计算宽度差分，最后用行数对照排除单纯随宽度增加的背景开销。只随请求数、行数或宽度增长的分配留作诊断。持续的行数/宽度交互增长提供本组 payload 保留反例的归因证据；固定噪声余量不随初始进程占用增加。四个请求是参考点，不要求所有缓存届时分配完。已有 tracemalloc 状态保留；区间允许为负，避免回收先前分配时截断信息。采样点之间继续执行完整生命周期，只减少观测器自身的 GC/采样开销。

这些检查不读取候选缓存容器、字段名、转换 API 或指定指针，不要求采用 Oracle 的存储或释放方式。新增正例覆盖延迟/预分配和与宽度相关的诊断元数据；保留 compact Python/NumPy、稀疏/转置表示、重命名字段及可复用缓冲区对照。交互量是有限实验的因果证据，不是任意 Python/native 对象的所有权证明；背景行为同时与两个 payload 维度相关时仍存在观察歧义。现有空间增长检查和 Torch 数据来源观察继续提供互补覆盖。

验证：56/56 个完整 Docker 评分结果符合预期，24 个正例通过、32 个 Base/负例被拒绝。所有正例额外通过独立窗口/容量挑战。13 个 Harbor trial 均得到预期 reward，0 个 errored trial；包含新的四个对照、原有 NumPy/Python 泄漏、已有 tracing、可复用缓冲区、字段改名与完成性反例。8 个 host 差分、9 个 Tensor observer、4 个 completion channel、4 个 diagnostic-reporting 单测通过，共 25 个。没有进行新的模型调用。

本轮普通正例 verifier 平均 44.3 秒，Oracle 48.1 秒；全部正例范围 38.6–91.8 秒，包含候选自行开启全程 tracing 的额外成本。启动、独立挑战和清理不包含在这些数值内。环境仍为 4 CPU / 16 GiB / 0 GPU，镜像 `sha256:8d200d6c23d542fb41b456cb55bf5c984b1c467c2020e31fb0e053e120c5f852`。Harbor 0.22.0 / Compose 5.5.1 使用已归档的静态离线 Docker adapter，未声称 stock 动态 egress backend 或真实 CUDA allocator 覆盖。

`semantic-boundary.md` 记录行为与测试的双向对应；`local-regressions.json` 保存逐例结果、原因、时间和诊断量；`e2e-evidence.json` 保存可执行文件身份。最终原始记录在 `evidence/local-1.4.3.tar.gz`、`evidence/harbor-1.4.3.tar.gz`。`evidence/paired-host-counterexamples-1.4.2.tar.gz` 保留此前错误 reward 和独立 96 请求验证。旧版本矩阵与原始 agent 分数仍为历史记录。

验收快照位于 `/data/codex-pr84-rereview-58fed25-20260919`，分支 `codex/pr84-paired-host-lifecycle`，基于 `58fed254d542d8ce08b5195c4dd2390577b82066`。证据中的 uncommitted 状态描述验收时刻；后续发布以 PR #84 提交历史为准。运行后只更新证据和文档，评分源码、对照与 task 配置按冻结 hash 核对。
