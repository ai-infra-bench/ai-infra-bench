任务 1.4.0 已完成本地验收，可以保留。两个已复现的 P1 已修复；新增的实际存储要求已与题面、Oracle 和正反例同步。最终冻结快照的 36/36 组完整评分结果符合预期；12 组正确实现通过，24 组 Base/错误实现被拒绝。另有两组随机输入复跑通过。Harbor Oracle 与八组关键对照均完成，零 errored trials。没有新的模型调用。

**评审评分：10/10 个维度已评，20/20；没有未验证维度或已知阻断项。评分仅代表下述范围内的证据，不是穷尽正确性或任意代码防篡改证明。**

| # | 维度 | 分数 / 状态 | 关键证据 | 下一步 |
|---|---|---|---|---|
| 1 | 题目真实、清楚 | 2 — 通过 | 明确两种计量单位、窗口边界和固定输出下的存储要求 | 无 |
| 2 | 正确性独立于来源 PR | 2 — 通过 | 题面定义行为，允许不同接口与紧凑表示；密集存储的历史结果按版本保留 | 无 |
| 3 | 环境可解、无已知泄漏 | 2 — 通过 | 固定 Base/镜像；CPU、离线；真实构造与运行路径可达，测试仅在 verifier 阶段提供 | 无 |
| 4 | 题面与测试双向对齐 | 2 — 通过 | semantic-boundary.md 的逐项映射、token-derived masks、真实视频几何 | 无 |
| 5 | 执行实际行为链 | 2 — 通过 | add/schedule/load/execute/propose/update/profile；在模型收到输入时比较 | 无 |
| 6 | 正确替代实现可通过 | 2 — 通过 | helper、model/buffer 重命名，构造状态，转置和稀疏存储等正例 | 无 |
| 7 | 错误实现因目标行为被拒 | 2 — 通过 | 错误窗口、密集/预分配缓存、旧 Astra、预算/空窗口/lookahead 反例 | 无 |
| 8 | Oracle 独立验证 | 2 — 通过 | 独立 25-token、多窗口/四帧容量/六行存储挑战与随机复跑 | 无 |
| 9 | 评分结果可信 | 2 — 通过 | 预编译可信 worker、native 完成通道、真实 Harbor 提前退出/伪造报告对照 | 无 |
| 10 | 可复现与交接清楚 | 2 — 通过 | 执行文件 hash、固定镜像、36 组矩阵、9 组 Harbor、非 root 收集检查 | 无 |

**修复及契约变化。**

原 verifier 直接调用 gather/admission helper，既会拒绝合法重命名，也会漏掉生产调用方的错误窗口。现在使用真实 Scheduler、GPUModelRunner 和输入批次构造函数，经公开执行入口到实际模型输入；主模型与 draft 的窗口来自生产调用链。神经算术使用确定性输入，正常的 embedding 合并、缓存和请求状态变化仍运行生产代码。模型也经正常 load/get 接口注入，不依赖固定 model 或输入缓冲区字段。

题面新增：固定 encoder output 时，增加非 embedding prompt 位置不能让缓存的 embedding payload 随 placeholder span 膨胀。存储观测跟踪实际 encoder-derived backing storage，覆盖别名、稀疏 values/indices、原始 storage 所有权、原地复制和构造阶段的预分配。profiling 与运行时比较包含各自的初始常驻存储，避免普通 decoder buffer 或预分配池形成误判或漏洞。历史 dense-with-consistent-profile 正例在新契约下转为负例，patch 字节保持不变。

附带 Astra/high 的原始 1.2.8 分数仍为 1；它遗漏 Qwen3-VL 的 12.5 倍视频估算，当前作为负例得到 0。没有覆盖旧得分或重写原轨迹。详见 attached-trajectory-review.md；PR 正文更新草稿在 pr-description.md，轨迹链接固定到历史提交。

**验证和范围。**

完整矩阵通过的正确实现包括 Oracle、直接 mask 计数、构造时计数、重命名 cache internals、独立 profiling 接口、不同 batching 返回形式、零输出容量、重命名私有 helper、转置缓存、构造状态、重命名 model/input buffers 和稀疏缓存。重点错误对照均因实际行为失败：主窗口错移导致真实输入错位；展开或预分配的 dense payload 随 span 增长；旧 Astra 的 analytical video capacity 仍为错误单位。提前成功退出与报告伪造则因完成认证失败而被拒绝。

Harbor 0.22.0 使用固定镜像和静态 network=none 的本地 Docker 适配器；agent、测试传递、权限降级、评分和结果收集沿用 Harbor。主机不支持 stock 动态 egress 后端，因此没有将这些结果描述为 stock Docker provider 运行。镜像为 `sha256:8d200d6c23d542fb41b456cb55bf5c984b1c467c2020e31fb0e053e120c5f852`，资源为 4 CPU / 16 GiB / 0 GPU。非 root CI 用户 UID 995 已成功读取 36 个收集产物。

本轮正确解的单次 verifier 实测 18.2–19.4 秒，平均 18.7 秒；额外独立挑战和整个多实现矩阵的耗时不混入该数值。模型加载和设备原语是 CPU 替身，测试没有声明真实预训练模型生成、GPU 算力性能或 CUDA allocator peak 覆盖。物理 tensor storage 观测不等于任意非 tensor/native 编码的全面内存审计；完成认证也不声称防住任意进程内或原生代码篡改。

**证据与工作区。**

`local-regressions.json` 记录每组 reward、时间和实际失败原因；`e2e-evidence.json` 记录最终文件身份、环境和 Harbor 信息；原始记录位于 `evidence/local-1.4.0.tar.gz` 与 `evidence/harbor-1.4.0.tar.gz`。冻结快照在写最终报告和 evidence 前产生，之后只有证据与文档更新，执行文件保持一致。

验收时修改位于 `/data/codex-pr84-review-20260919`，分支 `codex/pr84-behavior-hardening`，起点 `61d77f0eee5f2fa64074a98dfa2f43c1c59a4e09`。`e2e-evidence.json` 中的工作区状态记录的是提交前的验收快照，执行文件以其中的 SHA-256 标识；后续提交和推送状态以 PR #84 的提交记录为准。
