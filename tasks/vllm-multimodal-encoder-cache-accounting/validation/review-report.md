# PR84 verifier 修复复核 — 1.3.0

结论：A100 固定镜像内的行为验收通过；Harbor 编排验收尚未运行。已评分 9/10，小计 18/18；第 10 维 U，总分待定。最终冻结快照运行 25 个评分场景，reward 全部符合预期；6 个正确实现各通过 2 套独立 challenge。Base 的两套 challenge 均失败，且确实进入目标行为路径。

PR HEAD 为 `08ee4f85fabe632dd56446c12be6b5ff2d247ae6`，构建提交为 `86e7dae`，本次验证源提交为 `08e68b6`；均经本地 push、A100 pull。review skill 来自干净 main `b40002e149e5d2e0896ca2cc3573a84f1f0b4091` 的 `.agents/skills/ai-infra-bench-task-review`。

| # | 维度 | 分数/状态 | 证据或缺口 | 下一步 |
|---|---|---|---|---|
| 1 | 任务真实且清晰 | 2 | 行数与占位跨度差异是实际需求；说明未改 | 无 |
| 2 | 正确性独立于源 PR | 2 | 按公开行为约定判分 | 无 |
| 3 | 环境可解 | 2 | 镜像 ID 精确匹配；agent 导入真实 vLLM/torch；9 个公开测试可收集；cc/headers 可离线编译 | 无 |
| 4 | 说明与测试双向一致 | 2 | 补齐 shifted gather 和直接视频估算；几何与行数相符；Oracle 完整运行 | 无 |
| 5 | 执行真实语义路径 | 2 | 调度、写入、两种窗口读取与两个容量消费者在镜像内运行 | 无 |
| 6 | 接受不同正确实现 | 2 | 5 个正对照得 1，包括 dense cache、字段改名、不同 profiling 接口 | 无 |
| 7 | 正确拒绝错误实现 | 2 | Base + 18 个负对照得 0；按行为差异或明确完成通道拒绝判定 | 无 |
| 8 | Oracle 独立验证 | 2 | Oracle 与 5 个正对照各通过缓存/容量 challenge；Base 两套均失败 | 无 |
| 9 | 评分可信 | 2 | 动态伪造、直接回调、提前退出等被最终 test.sh 拒绝；仅声明已测试攻击范围 | 无 |
| 10 | 验收可复现且交接清楚 | U | 固定镜像、文件哈希、原始输出、驱动已归档；尚无本版 Harbor job | 补 Harbor 采集链 smoke |

Gate 1 通过；Gate 2 的固定镜像与 agent 开发材料检查通过；Gate 3 的声明行为边界通过。发布验收仍保留 Harbor 编排检查。相较前次修复后报告，第 3–9 维从 U 更新为 2，依据是本次实际镜像执行；不把直接 Docker 运行写成 Harbor run。

F1：缓存字段改名实现得 1。F2：动态报告伪造和直接调用完成回调均得 0，日志证明到达攻击入口。F3：忽略 shifted gather 的对照得 0。F4：恢复 12.5 倍视频估算的对照得 0。

新检查发现历史 `alternate-distinct-profile-accessors` 仍有视频估算遗漏，实际产生 200/600 容量而非 16/48；保留原始 patch，将其明确列为负对照。新增 `alternate-distinct-profile-accessors-video-fixed`，保留不同 profiling 接口，只修复遗漏视频估算，得 1 且两套独立 challenge 通过。未降低测试要求以迁就历史样本。

最初驱动的 root Git 所有权检查失败，以及部分旧 patch 错套 Oracle 的失败均原样归档，不计入最终 25 场景。最终驱动以 agent 应用补丁、root 运行 test.sh，容器断网，CPU 4 / 内存 16GiB。底层生产依赖未修改；本版使用新的 workspace 镜像。

完成通道防御范围是已执行的 stdout 伪造、提前退出、其他 code object 直接调用完成回调。没有声称抵御任意 native 内存读取或进程内插桩。未执行新模型 rollout，修改已 commit/push 到 PR84 原分支，A100 已 pull；未发布 PR 评论。

工作目录已统一为 `/workspace/vllm`，覆盖 Dockerfile、task.toml、instruction、solution、导入 `.pth`、worker 默认路径和 curator 工具。完整重建配方和固定旧镜像离线迁移配方均随任务保存。本次 A100 使用 Dockerfile.workspace 离线构建；新镜像 ID 见 image-manifest.json。`/app` 已从运行时目录移除，没有兼容软链接。旧日志中的旧路径保留为历史事实。

本次验证的 25 个评分场景均在新镜像、新路径执行；所有正向独立 challenge 和 Base 负向 challenge 均重新运行。原 1.2.9 结果未用于替代本次验收。环境与计分器修改都在本地完成，再 push、A100 pull；验证生成的原始输出取回本地归档后再提交。
