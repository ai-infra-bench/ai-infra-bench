# DSH session model migration：按仓库 skill 复审

**结论：题目可以保留，但需要加固，当前不能通过发布审查。Gate 1 和 Gate 2 通过；Gate 3 不通过。发现 1 个 P0 评分绕过和 4 个 P1 合同/覆盖问题。**

本次复审推翻旧 `validation/review.md` 的“无阻塞问题”结论。旧模型试跑的 reward = 1、18/18 是真实历史结果，但当前测试没有充分证明完整满足题意。没有发现该模型使用下面的评分绕过；模型原始提交在补充业务用例中有两个实际错误。

## 审查版本与范围

- Skill、task 工作区：`/home/tiger/lidailin/ai-infra-bench`；分支 `main`；HEAD `ee32cad166ca065f02945bda6b2f6dca3a025ddd`。
- 使用该工作区的 `ai-infra-bench-task-review/SKILL.md`、完整 review rubric 和 validation playbook。Skill 文件未修改；仓库存在其他修改，目标 task 仍未跟踪。完整状态、加载文件 SHA-256 和全部 47 个 task 文件的大小/哈希见 `review-context.json`。
- Task：`tasks/dsh-session-model-migration`；上游 `deepseek-ai/deepseek-harness`；Base `4e84901e6471b79ec0338099867ebb4606d12bb5`；依赖 cutoff `2026-09-01T15:37:26Z`。
- 镜像：`ai-infra-bench/dsh-session-model-migration:base-4e84901e6471`；ID `sha256:e87af67674c9b180ee88328bffd4b4279c1324c0567ac86be943f951287a2b0a`。
- 本次只新增复审报告、反例和隔离执行记录。没有修改题面、Oracle、正式 verifier、模型原始提交或已有分数；没有提交、推送、PR，也没有重新调用被测模型。

## Gate 1：场景与题面，通过

使用现有会话继续工作、切换目标模型前检查容量、保留显式输出额度、隔离部署默认值，以及适配声明了 plaintext reasoning 扩展的网关，都是现有产品接口上的合理需求。题面是构造场景，没有声称复现某次历史部署或某个 PR；无需把它改写成讨论区原文。

`selectModel`、provider profiles、token meter 和持久化事件是 Base 中存在的能力。新增 opt-in 参数和网关字段属于功能请求。题面给出了较充分的业务验收条件，但没有给出私有 Oracle 函数、补丁、隐藏测试文件或逐步实现算法。导航充分是难度设计因素，不构成这里的答案泄漏。

## Gate 2：环境与 cutoff，通过

语义边界：

```text
checked selectModel 请求
→ 真实会话状态/版本与目标能力解析、token-meter 容量检查
→ 会话本地选择事件与重开后的请求构建
→ pi-ai 的真实 HTTP 序列化
→ 工具执行、副作用和包含结果的下一次请求
```

真实执行组件包括 Loader、会话/投影、agent loop、控制器业务操作、token meter、pi-ai/HTTP 客户端和工具执行器。外部模型目录和生成事件是可替代的输入边界：此题检查路由、容量估算与协议保真，不检查模型回答质量。HTTP 输入、事件顺序、并行调用数量和结束事件得以保留；工具真实写文件。重开通过 JSON 保存事件后建立新 agent，是事件重放边界；不宣称覆盖所有存储后端故障恢复。

本次重新检查了精确镜像的 inspect、完整 history、Base HEAD、干净 Git 状态、remotes/tags/reflogs/FETCH_HEAD/ORIG_HEAD/alternates、不可达对象，以及 `/tests`、`/solution`、`/validation` 缺席。检查通过，锁文件 SHA-256 与记录一致。镜像层只安装 Base、系统工具和锁定依赖，没有任务专用补丁或测试层。见 `remote-results/image-*`。

pi-ai 0.84.2、OpenAI SDK 6.40.0、Zod 4.4.3 的已有 registry 记录早于 cutoff；目标源代码和 vendored runtime 由 Base 固定。Node/构建测试工具属于固定版本的基础设施。本次未重新请求 registry 时间戳；使用已有依赖证据并校验其文件身份。

4 CPU、8 GiB、20 GiB、离线工作区可以执行真实边界。agent 预算 36000 秒，无短于 10 小时的警告。上次模型运行只为模型 relay 放行一个地址，隐藏验收离线。此次反例都在 `--network=none` 的同一 Base 镜像执行。

## Gate 3：验收与评分，不通过

旧验收共 18 项：迁移工作流 2 项、预算/准入 10 项、Responses 兼容 6 项。其主链路完整，且不要求固定生成 ID 或固定修复位置，但以下组合缺失：

| 题意 | 旧覆盖 | 本次补充发现 |
|---|---|---|
| 显式输出额度与容量检查 | 非空会话显式额度；空会话默认额度 | 空会话 + 显式额度漏算 |
| 显式额度、迁移和重开 | 即时继续有显式额度；重开只有默认额度 | 重开后显式额度丢失 |
| 工具调用与结果逐一配对 | 两个前缀不同的 provider ID | 去掉后缀后发生 ID 碰撞 |
| Responses 配置兼容 | 显式 API；错误协议拒绝 | 合法的目录继承协议被 Oracle 拒绝 |
| 所有必需测试确实执行 | 精确名称/状态/数量；native 提前退出控制 | 工作区内测试 runner 可被替换，完整 JSON 可伪造 |

### P0：候选可替换测试 runner，零测试仍得满分

位置：`tests/grade.py:24` 从候选可写的 `root/node_modules/vitest/vitest.mjs` 启动测试，随后在 `:28` 信任该子进程生成的报告。独立 Python 父进程检查名称和数量，无法识别伪造这些字段的 runner。

反例只替换 `node_modules/vitest/vitest.mjs`，保留 Base 全部目标源码。替代 runner 在验收阶段读取 `/tests/expected-tests.json`，写出所有名称为 passed 的 JSON 并正常退出，完全不导入或执行行为测试。Docker 中 `git diff --exit-code` 成功，实际 grading entrypoint 仍写 reward = 1。日志只有 `REVIEW_FORGED_REPORT_WITHOUT_EXECUTING_TESTS`。

完整 Harbor 复现同样 reward = 1、零异常：job `e204154c-db4f-437e-8c46-43300615c69e`，trial `73f23eb5-54ba-409f-85ae-baa05217d6d4`，名称 `forged-harbor-case__qaTPYu5`。它使用同一镜像和未改动的正式测试；Oracle agent 仅承担“执行错误候选准备命令”的角色，并未应用参考功能补丁。

修复方向：建立候选无法改写的测试运行时和结果采集边界，校验/重建可信依赖与启动链；不能只增加 JSON 字段检查，也不能只把成功标记改名。必须同时保留 native 提前退出和 forged-runner 两类控制，在完整 Harbor 路径验证它们均为 0。影响 `tests/grade.py`、测试运行时/隔离配置和控制记录。

### P1：迁移后重开丢失显式输出额度

位置：旧 `tests/budget.spec.ts:73` 只测试立即继续；`tests/migration.spec.ts:24` 的重开没有显式额度。Oracle 和模型提交均沿用 Base 首次重开请求从 agent options 构建额度的路径，没有恢复事件中显式保存的值。

反例：会话以 `maxTokens: 177` 完成一轮，checked 迁移成功，保存事件并重开，再向目标发起请求。实际 HTTP `max_output_tokens` 为 **128**，合同要求保留 **177**。Oracle、替代实现、模型提交均失败。应补齐“显式额度 × 重开”覆盖，并修复持久化请求控制的恢复路径。

### P1：空会话迁移漏算已经显式指定的输出额度

位置：`solution/feature.patch:203` 只从 previous request header 取得显式额度。空会话还没有 header，agent options 中的显式值被忽略；旧空会话测试均未传显式额度。

反例：空会话 `maxTokens: 177`，目标窗口 32、默认输出 32。Oracle/替代实现允许迁移，本应因 177 > 32 拒绝；模型提交正确拒绝。应补充空会话显式控制，并修复 Oracle 和替代实现；不得通过收窄题意消除反例。

### P1：两个工具 ID 归一化后碰撞，模型错误提交仍得满分

位置：`validation/model-run/submission.patch:1476` 将 ID 截断到第一个 `|` 之前。旧 `tests/migration.spec.ts:11` 的两个 ID 分别以 `old/a` 和 `old?b` 开头，无法暴露这个错误。

反例：源 Completions 网关产生两个不同调用 `shared|opaque_a`、`shared|opaque_b`，真实工具分别记录 alpha 和 beta。迁移后实际目标 HTTP 含两个 `call_id: shared` 的调用及两个同 ID 的结果，失去一一配对。Oracle 和替代实现保持两个不同 ID；模型提交失败。应把该模型提交保留为一个自然产生的错误控制，并覆盖会发生碰撞的 ID 组合。

### P1：Oracle 拒绝合法的目录继承 Responses 协议配置

位置：`solution/feature.patch:583` 要求配置必须显式写 `api: openai-responses`，而题面只禁止启用在非 Responses 路由。

反例：`openai` profile 选择已安装的 `gpt-4.1`，通过 catalog 继承协议。独立断言确认解析后 API 为 `openai-responses`，没有开关时 profile 合法；加 `responsesReasoningText: true` 后 Oracle/替代实现错误拒绝。模型提交按解析后模型协议检查，因此通过。应修复 Oracle 判断并增加合法继承配置与不合法混合协议配置的覆盖。

## 实际执行结果

本次所有候选先运行原封不动的正式 `/tests/test.sh`，再在同一个一次性容器运行单独的 reviewer probes。下表的“旧验收”不是修改后的分数；补充探针尚未加入正式 verifier。

| 候选 | 旧验收 | 空会话显式额度 | 继承 Responses 协议 | 显式额度 + 重开 | ID 碰撞 |
|---|---|---|---|---|---|
| Oracle | 18/18，reward 1 | 失败 | 失败 | 失败 | 通过 |
| 原替代实现 | 18/18，reward 1 | 失败 | 失败 | 失败 | 通过 |
| 原模型提交 | 18/18，reward 1 | 通过 | 通过 | 失败 | 失败 |

当前“正确替代实现”标签需要撤回其完整正确性保证：它在投影算法上确实不同于 Oracle，但共享了准入和重开缺陷。修复后需要重新独立挑战，不能仅凭相同 reward 证明公平性。

已有可校验历史记录：Base 两次 6/18、reward 0；Oracle 两次 18/18；no-budget 15/18、no-revision 17/18、global-default 17/18、no-reasoning-transfer 15/18，均 reward 0；native 提前退出 reward 0；原替代实现 reward 1。已有 8 类 Harbor 记录均为预期旧分数、零异常。本次没有重跑那些未受修改的旧控制。原 `process.exit` 被 Vitest 截获的记录已被 `process.reallyExit` 控制替代；native 控制有效，但不防报告伪造。

当前 repository validator 通过，已有 evidence 中 36 个文件哈希全部匹配。可选审计脚本的固定 Python/JUnit 文件约定不适用于本 task，本次使用仓库 validator、文件/镜像哈希核验和实际 Docker/Harbor 控制，没有把静态通过当作语义通过。

## 后续需要变更的材料

1. 加固 verifier 的运行时和结果信任边界，并添加完整 Harbor 错误控制。
2. 将四个业务探针并入正式验收；修复 Oracle 与语义不同的替代实现，保留当前模型提交用于验证错误会被拒绝。
3. 对变更后的正式任务重跑 Base、Oracle、全部控制和替代实现，再冻结可执行哈希，更新 image/evidence/review。旧模型分数应保留为旧 verifier 版本的历史结果，追加修订后的重评分，不能悄悄覆写。

难度调整属于非阻塞设计建议。现在应先解决错误答案可得满分的问题，再用修订后的验收判断模型能力；无需为增加难度而堆文档或扩大为无关功能。

## 复现材料

- `probes/review.spec.ts`：四个合同内反例；`probes/support.ts` 复用真实工作流装配，未替换业务实现。
- `remote-results/results-v2.json`：每个候选的完整命令、原分数、探针状态和断言栈。
- `remote-results/runs-v2/*/entrypoint.log`：实际 HTTP 调用配对和重开输出额度。
- `forged-runner.mjs`、`run_forged_remote.py`、`run_forged_harbor.py`：评分绕过控制及 Docker/Harbor 复现脚本。
- `remote-results/forged-harbor-result.json`、`remote-results/jobs/`：完整 Harbor 错误奖励证据。
- `evidence.tar.gz`：上述远端原始输出归档；`manifest.json` 记录本次证据的 SHA-256。

这些发现均未修复，最终状态为 **needs hardening**，不是完成加固或可发布。
