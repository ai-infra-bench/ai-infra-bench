fused：修订后的 task 可保留；本轮本地 review 与验证通过。

原始 0 是量化对象 fixture 的误拒绝；生产量化构造保证的状态被替身遗漏。

执行真实 UnquantizedFusedMoEMethod 构造和真实 GEMM selector，提供一致的真实 MoE 配置对象；保留缺配置警告、冲突归属和 Triton 数值检查。 另修复形状查询次数造成的误判：公开保留 DP+EP worst-case/ordinary workspace 语义，观察生产分配接口返回张量的峰值逻辑字节数，允许额外诊断查询。 数值参考使用 FP32 累加误差界处理低精度舍入和 expert 贡献抵消；原比较系数保留。

语义边界和替代：真实量化对象构造、factory、kernel profile、Triton 前向。轻量 layer view 提供一致配置；工厂末端 wrapper 只返回 kernel，不执行不相关 CustomOp dispatch/权重加载；NoEP 激活输入替代分布式 transport。

覆盖：配置正常/生命周期空隙无假警告、真缺配置仍警告、ambient 冲突时 layer owner 优先、四组独立数值；真实历史解答作为另一正确实现。 新增额外 workspace_shapes 查询的正确实现；同一控制旧 fixture 为 0、新 fixture 为 1。独立推导 16,384-row workspace 容量下限，拒绝只预留 64 rows 的数值正确反例。

| Case | Expected | Actual | Harbor errors |
|---|---:|---:|---:|
| alternate-config-wrapper | 1 | 1 | 0 |
| alternate-production-quant-owner | 1 | 1 | 0 |
| alternate-workspace-diagnostic | 1 | 1 | 0 |
| base | 0 | 0 | 0 |
| constant-numerical-output | 0 | 0 | 0 |
| constructor-global-cache | 0 | 0 | 0 |
| early-exit-os-exit | 0 | 0 | 0 |
| early-exit-system-exit | 0 | 0 | 0 |
| forged-report-exit | 0 | 0 | 0 |
| oracle | 1 | 1 | 0 |
| replay-observations | 0 | 0 | 0 |
| undersized-profile-workspace | 0 | 0 | 0 |
| oracle (final frozen) | 1 | 1 | 0 |

独立 challenge：7 个状态符合预期；每项有输入文件 SHA256 和原始日志。
新结果不覆盖原始 solver reward。旧 review 证据保存在 /data/yinchen/task-remaining6-repair-20260909/before/fused。
完整证据：validation/e2e-evidence.json。
改动未提交、未推送。此为本地审查结果，未取得外部 reviewer 批准。
