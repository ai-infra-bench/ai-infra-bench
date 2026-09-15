# Pi Plan Mode 独立审查（作者验收完成）

**最终结论：该题通过当前开发环境下的作者验收，可留在本地分支交付用户 review 和测试。** `matrix-final-verified-20260915` 的 11 项正式 Harbor trial 全部完成、零环境错误，Oracle 与独立 event-journal alternative 都为 1，Base 和八个负控制都因缺失或错误的目标行为得到 0。审查者独立读取了正式结果、目标 JUnit、P2P summary 和关键原始失败，R1–R5 均已在下述声明边界内关闭。未修改 Base 的 AuthStorage 间歇失败仍作为已证实的环境限制保留；首轮失败矩阵没有被改判。本轮是任务质量审查，不是 Pi 能力评价或任何 coding agent 轨迹审查。

最终 10/10 维已评分，合计 20/20，表示本次作者验收要求已满足，不表示题目没有局限或已获得真实 coding-agent 难度/成功率数据。完整首轮 matrix 保持 9 项符合预期、2 项正确实现因 R5 得到错误 reward 的历史记录；后续冻结规则后重新执行的独立完整矩阵为 11/11 符合预期。同一事项不会因影响多个维度而重复计数。

| # | Dimension | Score / status | Key evidence or gap | Next action |
| --- | --- | --- | --- | --- |
| 1 | 任务是否真实且清晰 | 2 — Pass | 对现有 Plan Mode extension 增强版本绑定审批、工具限制和正常恢复，是明确可理解的开发需求；最终题面未扩大为其他生命周期 | 保留任务范围 |
| 2 | 正确性是否独立于来源 PR | 2 — Pass | instruction 定义行为；已有公开实现和已经修复的历史问题被当作背景，没有成为私有实现要求 | 保留 prior-art 和污染风险说明 |
| 3 | Agent 能否在环境中解题 | 2 — Pass | 固定 Base/锁文件；真实 UID 1001 离线开发检查和正式 Harbor Oracle provisioning 均通过；仅镜像拉取路径作相同 digest 的适配 | 保留该准确镜像与 launcher 记录 |
| 4 | 题面和测试是否双向一致 | 2 — Pass | 18 个 contract（含 C00 评价完整性自检）和 4 个生命周期 case；L04 补齐 normal resume；P2P 双边投影已一致；C04 保留正常 schema 转换 | 冻结当前契约，后续只复核受影响改动 |
| 5 | 是否执行真正决定行为的路径 | 2 — Pass | 最终 Oracle/alternative 的 22 cases 完整通过；C15 旧 UI 选择、L04 独立新进程和真实 dispatcher 副作用有正反控制证据 | 保留原始结果 |
| 6 | 不同正确实现能否通过 | 2 — Pass | alternative 用 journal/reducer，Oracle 用完整快照；同一最终 verifier 下均18+4及P2P通过、reward1，且没有触发已知Base失败条件 | 保留两种实现和最终trial |
| 7 | 错误实现是否因正确理由被拒绝 | 2 — Pass | 八个最终负控制均scope/P2P门禁通过，分别在声明行为缺陷或提前退出完整性上失败，正式reward0 | 环境或判题修改后重跑受影响控制 |
| 8 | Oracle 是否经过独立验证 | 2 — Pass | 独立推导 normal resume + --plan 挑战，发现并修复 R2；审查者已读取正式 smoke L04 通过结果；Oracle 没有豁免 | 保留该挑战与最终结果 |
| 9 | 评分结果是否可信 | 2 — Pass | C00通过；root config冻结；提前退出控制在Vitest拦截与独立Node真实零退出无payload两条路径都被拒绝；无万能防篡改宣称 | 保留原始XML和控制patch hash |
| 10 | 验收能否复现且交接明确 | 2 — Pass | image/build/provenance、精确Base失败实证、最终11项的job/reward/raw hashes及开发分支交接范围完整；未提交、未推送 | 保留e2e-evidence，报告/README更新后刷新文档hash |

## 审查快照和范围

- 审查 worktree：`/tmp/ai-infra-bench-pi-plan-mode-20260915`，detached HEAD `9a5d7fee81b151a362b13a67587a12fc8cc00296`。
- dirty 状态：修改 `.agents/skills/ai-infra-bench-task-review/scripts/audit_task_artifacts.py`；新增 `tasks/pi-plan-mode/` 与 `templates/pi-harbor-node/`。审查者未修改任务、Oracle、verifier 或控制，只写本报告。
- Pi Base：`d981de1229ef899957bbe968bc8dcda02a21f477`，cutoff `2026-09-05T11:54:46Z`。
- 指定 skill：`.agents/skills/ai-infra-bench-task-review/SKILL.md`，SHA-256 `0698839b2cf6e54758eb7277c1586c888211bf2e2fdbef9083f83696ba07a749`。
- 完整 rubric：`.agents/skills/ai-infra-bench-task-review/references/review-rubric.md`，SHA-256 `95dc3bd21b3b82b1e1eef28609aaab6384690aa65390ead1f526f549f6183e87`。
- 已阅读 instruction、task.toml、Dockerfile/lock manifest、README、history/behavior map、全部 verifier 源码、Oracle 和 alternative patch、错误控制生成器及 manifest。大型 JSON 锁文件和 Base manifest 按文件类型、hash、结构记录，不把文件大小等同于完成语义审查。
- 初始审查 hash：instruction `fdca0ae169d49221bea179452977ed2640d4d1819d8945b12ca0802dbe3bc8e4`；Oracle patch `b97cf36dc21c1214ab63e1d1b8e8af3e170d65646f05755a7fe6c15eefddcedc`；alternative patch `73647d4d894218f67c59c359e7b84ba401fb60a0fb25e8a303536dc83efa4f95`；test.sh `93e3ec9d04ac509fa0e2543a4bce4ca3e584b6437645ca95260232393c1c7f15`。这些是发现所对应的中间版本，不是最终验收 hash。
- 本次静态复核的 image 为 `sha256:a68c346850d3b3ec045dd52aaf751e229e888ca365de99ab06a99fe88eeb0cda`，metadata、image manifest 与 build provenance 一致。instruction SHA-256 `d5fe707469a99a0aff864dccd81a35094151e53fe23ee6168f4900563322ee8f`；Dockerfile `46c82ca87a43c46770bb6f443650a21a18ce04bed31e78177df44e91ee72fd9c`；test.sh `2029fb5f8f31d41a61f5a95bd613553497fc91cbd4314c5ee8fa9c7300f8cce0`；preload `7c8f28f949a69fec57ae3fe732c0c3c717794ed26eeb5f4eabf6fb0571736b8d`。后续入口加固如果改动这些文件，正式结果必须使用新 hash。
- 最后机械审计发现通用 artifact audit 的旧 `check_image` 把全部控制补丁直接按 Base 检查，忽略主 CI 已支持的 `apply_after=oracle`。审查者只读核对修正与 `.github/scripts/task_ci.py` 的既有合约一致：Oracle 和 base 型 alternative 保持直接检查；八个 oracle 型控制各用独立 `--rm --network=none` 容器先应用 Oracle，再 `git apply --check`。固定 shell 程序用位置参数传递模式和路径，`set -e` 保证前置应用失败不会被后续检查掩盖。通用脚本 SHA-256 为 `2496bf433cdbb0394e09ced0851a82d90956470a649d19cab361f3434dbc3f73`。该工具修正只影响作者机械检查，不修改 task/verifier/solution/main CI，因而无需重跑既有 11 项正式矩阵。Root 报告修正后的 `--strict-evidence --image` 实际检查为 5 checks、0 errors、0 warnings，image identity 和 10 个补丁适用性全部通过；该运行记录单独留存，本审查者没有重跑。

## 三个 gate 与语义边界

**Gate 1：静态通过。** 谁提出需求、修改对象、可用 API 和不支持的生命周期明确。公开已有 Plan Mode 不否定该工程题的真实性；该题没有宣称功能新颖或完全无污染。除非另有真实执行证据，history 文件中的观察仅按源码/来源核对处理。

语义边界为：

```text
interactive/RPC 输入、结构化 tool call、用户 UI 选择或正常 session reopen
  -> 实际 extension loader + AgentSession 输入来源/工具调度/settlement
  -> 扩展版本与审批转换、工具集合、持久化与自动执行调度
  -> 公开 custom entry/message、真实 provider 请求、文件副作用及新进程恢复结果
```

Faux provider 只提供可控模型输出；UI adapter 只提供用户选择。它们不实现目标 plan state、权限判定或执行调度，替代边界合理。真实模型是否理解自然语言计划不在契约内。这里的“RPC”是 SDK 的 `session.prompt(..., {source: 'rpc'})` 输入语义；没有声称覆盖 RPC 网络传输协议。

**Gate 2：通过本次开发环境验证。** Docker 构造从精确 Base SHA 获取完整祖先历史，移除 remote、tag、reflog、FETCH_HEAD，并检查不可达对象；运行源码位于正常 `/workspace/pi` 路径。锁文件与 Base 一致，agent 镜像不 COPY 私有 tests/solution/validation。UID 1001 离线开发检查和正式 Harbor Oracle provisioning 均已通过；构建版本有记录（R4）。首轮 `no-network unsupported` 是 probe 镜像下载失败，按相同 digest 改镜像站后保留了原网络隔离和评分。审查者已完整读取 `harbor_mirror.py`，其唯一 provider 改动是 probe registry，没有覆盖 capability 判定或 scorer。

**Gate 3：通过。** verifier 不 import candidate 私有 helper，不要求其持久化 schema；alternative 的 journal 可以被相同公开测试使用。最终完整矩阵证明两种正确实现通过、Base 与八个负控制均按目标行为被拒绝。原始 P2P 不稳定问题有独立 Base 实证和窄化处理，所有 2,154 项保留，原始 XML 不改写；最终提前退出控制仍得到 0。

## 发现与关闭条件

### R1 — P2：旧套件比较输入必须是同一投影

初始 Dockerfile 的 `/opt/pi-baseline/coding-agent-junit.xml` 包含全量 Base suite，`p2p-files.txt` 则排除允许更新的 `plan-mode-extension.test.ts`。初始 `check_pass_to_pass.py` 直接比较全量 baseline 和排除后的 candidate，必然产生 missing legacy cases，与候选功能正确性无关。

后续静态复核已确认修复：先验证完整 JUnit 的 aggregate，再对 baseline/candidate 做相同且仅针对该文件的投影。**R1 已关闭**：最终 Base、Oracle、alternative 与全部控制都保留同一 2,154 项 inventory；Oracle/alternative 的原始回归全部通过，Base 原始结果和后续已知失败分别记录。

### R2 — P1 已关闭：normal resume 的 flag 优先级存在 Oracle 缺口

独立于 hidden inventory 推导的挑战：扩展加载后保持 `normal`，产生一条 assistant 回复使会话落盘，正常 idle close；新进程带 `--plan` 恢复该文件。题面只允许 fresh session 因 flag 自动进入 planning，并声明 resume 时已持久化状态优先。

初始 Oracle 只在进入 planning/approval 时写状态，normal 会话没有保存记录；`session_start` 在没有恢复记录且 flag 为 true 时直接进入 planning。因此这条真实生命周期可能错误地改变 normal 会话。alternative 已写 `opened` journal 并区分恢复，存在实质行为差异。这里没有要求 crash、fork 或 reload。

Root 已确认这是原契约的直接含义，并补充 L04 独立 Node 进程测试。后续静态复核确认 Oracle 已保存 normal 初始状态，且不会对已有 assistant 消息的恢复会话应用 fresh flag。审查者已直接读取最终 Oracle 和 alternative 的 L04 原始 JUnit，两者都通过。原代码缺口已修复；没有声称曾用该挑战复现正式错误 reward。

### R3 — P2 已关闭：评分权限与完成性

初始 test.sh 的 root 候选进程可读写与父评分进程相同的文件，包括 `/tests` 和 `/logs/verifier`。独立 Python 校验 testcase inventory 优于只信任 exit 0，但不能仅凭“父进程独立”推断这些文件可信。没有生成或执行攻击脚本，也没有宣称已复现 P0 绕过。

后续静态复核已确认专用 agent UID 1001、冻结依赖/Git/配置、root reporter 与降权 fork worker UID 65534。test.sh 在 scope/integrity 通过后才启动 coordinator，清理 candidate Vite cache 并冻结被测试源文件。C00 通过非破坏性的 `open(..., 'r+')` 和 signal 0 自检验证权限，而不是执行利用脚本；正式 C00 和 UID 日志已读取。候选开发检查证明允许的扩展/test 目录可编辑，已装开发工具可用；正式输出采集和 early-exit-zero 结果证明有限权限/完成性边界。此类检查不证明能抵抗同 worker 中任意 monkey patch，也不应作万能防篡改声明。

**后续正式复核：R3 在声明的有限边界内关闭。** 审查者已独立读取 C00 正式通过结果及 UID 日志；`early-exit-zero__TcRxnjY` 的 contract XML 明确记录 Vitest 捕获 `process.exit unexpectedly called with "0"`，lifecycle XML 则在独立 Node `status === 0` 断言通过后，因为观察 payload 不存在而失败。最终 reward 0；scope/P2P exit 0，contract、lifecycle 及其完整性 checker 都 exit 1。它证明提前零退出不能伪装为完成，不证明能够抵御同 worker 内任意断言篡改。

本次还检查了为原 SettingsManager scratch 测试设置的 package root sticky mode 1777。它保护已有 root 文件不被低 UID 删除，但允许新增文件。审查建议三次 Vitest 调用都显式 `--config /workspace/pi/packages/coding-agent/vitest.config.ts` 指向冻结配置；Root 已确认路径并完成修改。配置自动发现的静态风险已关闭。没有生成或运行利用脚本，也没有宣称曾复现 wrong reward。

### R4 — P2：构建可复现性和发布状态应准确

Node/Alpine image digest、fd checksum、Pi SHA 和 package-lock 固定。`apt-get install`、`apk add` 与 Dockerfile frontend 仍有浮动解析，不能把 Dockerfile 描述为未来可逐字节复现。后续已生成 `environment/image-manifest.json` 和 `validation/build-provenance.json`，当前记录 image `sha256:a68c346850d3b3ec045dd52aaf751e229e888ca365de99ab06a99fe88eeb0cda`、实际 Debian 包、BuildKit v0.32.2 及工具镜像 digest、镜像构建网络参数/日志，并准确披露未来重建非 byte-identical、镜像尚未发布。该追踪缺口在开发交接范围内已关闭；发布可拉取固定镜像或进一步锁定仓库 snapshot 是明确的后续限制，不需要为本次未推送开发分支增加发布动作。

## Fixture 可达性与覆盖限制

- C01–C12：由公开输入、真实结构化 tool call、已注册命令/快捷键和 dispatcher 产生状态；错误类型样例各自控制单一失败原因，没有要求未规定的多错误优先级。
- C13/C14：用真实 waiting tool 或 read tool_call hook 持有执行边界，再通过正常输入请求 enter/approve；最终 Oracle/alternative 均通过，超时仅界定挂起，不是吞吐阈值。
- C15：hold 已显示 v1 的 select promise，通过后续 RPC prompt 提交 v2，再返回旧 Execute。最终两种正确实现通过，stale 控制在相同路径错误批准 v2，实际可达性已证实。
- L01/L02：先有 assistant 回复，再 idle close/reopen，独立 Node PID 验证恢复；既没有靠在同一进程重置变量伪装恢复，也没有检查 crash 语义。
- L03：通过公开 `appendCustomEntry` 将候选自己生成的 foreign-session entries 放入新 session；明确对应“不能使用别的 session 状态”的契约。它是显式注入的 foreign-state 验证，不是正常打开会自然泄漏的证据。
- 原有纯 utils 测试保留；legacy toggling/custom-tool 断言按题面允许改变。候选自行新增测试不应改变 hidden inventory。

## 降权旧套件的 AuthStorage 稳定性审查

Root 报告受保护 reporter / UID 65534 下，Oracle 的 18 个 contract 与 4 个 lifecycle case 已通过。早期复用 Oracle debug 容器曾在未修改的 `auth-storage.test.ts` 中观察到 `keeps a coalesced reload alive while another credential reader is waiting` 间歇失败。独立同长度写入探针出现时间戳相同的现象，但不单独证明该断言失败的原因。

第一批 fresh Base 重复运行已记录在 `baseline-environment.md`：相同精确 Base 和冻结文件，UID 65534、4 CPU/8 GiB、无网络；五次完整 auth-storage 文件执行各 26/26 通过，随后完整 P2P 2,154 cases、零 failures/errors、50 原 skips。这一批使用 `--retry=2`，没有复现上述 assertion，因此当时没有足够证据批准例外，也没有新增例外或 skip。这是历史结果，不代表后续固定采样仍未复现。

当时的独立判断是维持严格规则：原 baseline outcomes/hash 保留，所有原本 passed 的 case 继续强制 pass，不得因该病例添加任意失败预算。旧 debug XML 曾被后续运行覆盖，`baseline-environment.md` 已披露这点；早期时间戳探针只支持时序解释的可能性。首轮正式 Harbor matrix 确实使用无新增例外的比较器；后续新实证见下文，不能倒改首轮历史结果。

### 固定采样的原始 Base 复现：已独立核对

审查者只读检查了 `/tmp/pi-authstorage-fs-diagnostic-20260915-infra` 的 `REPORT.md`、`summary.json`、既有执行脚本、provenance、原始 JUnit、worker 日志、container inspect 和已有采样记录。`SHA256SUMS` 全部校验通过，任务内 `validation/auth-storage-diagnostic/` 与原目录逐文件一致。没有生成或运行新探针、修改任务或执行诊断程序。

容器创建时间为 2026-09-15 04:43:58 UTC，image 为本报告固定的 `sha256:a68c346850d3b3ec045dd52aaf751e229e888ca365de99ab06a99fe88eeb0cda`，network none、4 CPU、8 GiB。既有脚本在一个新容器中交替运行 overlay/tmpfs，各预定五次原始 auth-storage 文件，使用 `--pool=forks --maxWorkers=4 --retry=0`；没有应用 Oracle/alternative 或改原始测试。十份 worker 日志均记录 UID 65534。它是一个独立容器内十次独立测试进程，不是十个新容器，也不是十次完整 Harbor/P2P 运行。

停止容器后采集的原测试、AuthStorage 源码和 paths 源码 hash 分别为 `513f35d1adec13ba026a7e73b9d8fd2b98f416d102c6c061f976a3d5e468b2fe`、`32d36165760959766807b8797042e69b65a65c7aad7d1b79a2621c41fe29b48d`、`a687cdb54b82216673fea5be1210c48e64ffa8398d64cfabf2bd7dba5c9d4210`，与先前冻结 Base provenance 相同。诊断 provenance 中的 `base_commit` 是脚本声明值，并非新执行的 Git 查询；此处确认“未经任务修改”依据固定 image、无补丁执行流程及实际文件 hash，不把该声明单独当作来源证明。

| 原始运行 | 26 项中的失败数 | 其余结果 |
| --- | ---: | --- |
| overlay 1、5 | 各 1 | 其余 25 项通过，无 error/skip |
| overlay 2、3、4 | 0 | 26 项通过，无 error/skip |
| tmpfs 5 | 1 | 其余 25 项通过，无 error/skip |
| tmpfs 1、2、3、4 | 0 | 26 项通过，无 error/skip |

审查者完整读取了三份失败 XML：唯一失败均为 `AuthStorage > keeps a coalesced reload alive while another credential reader is waiting`，type 为 `AssertionError`，message 为 `expected { type: 'api_key', key: 'old' } to deeply equal { type: 'api_key', key: 'new' }`，stack 为 `test/auth-storage.test.ts:137:22`。它们与首轮正确实现遭遇的原始失败一致。三份 XML 的 SHA-256 保存在归档 `SHA256SUMS`；例如 overlay 1 为 `d946d8c0339132c9b155ff22ebe67563d64acc87d18f6d5f671bac31b7bcdd03`。

这已经证明：该冻结 Base 的原有单元测试在当前宿主环境可以间歇失败，失败并不以 Plan Mode 修改为前提。五次/文件系统的小样本不能估计可靠失败率，不能证明 tmpfs 优于 overlay，也不能把此前有 retry 的全通过解释成消除问题。现有采样中两种文件系统都复现了相同断言，所以不采用 tmpfs 作为已经验证的稳定方案是准确的。

既有 revision 采样报告为每个文件系统 1,000 次同长度写入，overlay 735 次、tmpfs 990 次前后 revision 相同；原始记录显示时间戳正增量约 1 ms。这支持 revision 缓存发生同值的机制解释，但它与原单元测试分别运行，没有记录每一次失败断言当时的全部缓存调用，因此这里不把时间戳统计表述为逐例因果证明。`baseline-environment.md` 关于固定运行次数、2+1 次原始失败、相同断言、其他 25 项通过、未采用 tmpfs 以及保留旧矩阵的描述均与所读证据相符。该文档另述的独立 API trace 和后续评分器策略不在本次只读复核范围内。

### R5 — P1 已关闭：acceptance matrix 正确实现被同一非目标 P2P 失败阻挡

上述 fresh Base 孤立检查之后，正式 `matrix-acceptance-20260915` 出现了新的原始证据。审查者通过 SSH 读取：Base `base__SkHjQsJ` 的 P2P 2,154/2,154、零回归，正式 reward 0；Oracle `oracle__7i2bLiH` 和 alternative `alternative-event-journal__VdiNy45` 的 P2P inventory 同样完整，但都唯一失败于 `test/auth-storage.test.ts::AuthStorage > keeps a coalesced reload alive while another credential reader is waiting`，正式 reward 0、check exit 2。两者原始 JUnit 均为 line 137 的 `old`/`new` deepEqual assertion failure，不是 timeout、import failure 或缺项。两者目标的 18 contract/4 lifecycle 通过由作者报告，正式 Oracle smoke 的相同边界已独立核对。

这些失败目录和 XML 已保留。后续固定采样满足“原始 Base 同类断言真实失败”的实证要求，改变了先前未复现的事实状态；之后修订规则下重新执行的完整 11 项 Harbor 矩阵全部符合预期，完成 R5 关闭证据。没有要求 solver 修改范围外 AuthStorage，没有靠任意失败预算或反复重试到通过，也没有改写 fs/时间/API 语义。首轮两个正确实现 reward 0 不改判。环境中的原有间歇失败没有被修好，而是被明确识别、保留和隔离于本题评分。

### 后续精确失败识别的普通 CI 静态复核

经 Root 明确追加只读范围，审查者完整阅读冻结的 `check_pass_to_pass.py`、`baseline-pins.json`、`test_integrity.py`，并核对现有 test.sh 仍固定 `--retry 2`。三文件 SHA-256 分别为 `4c588c1ee30c52bc54c1e55830a182437ae1422e0548e448c7184562673ed9be`、`f9687b28641afd351b6ffd342bfb19d7bc3a635e5f4854d65056d36879ddaace`、`b1893d7a7f0d09941f480e6bca323307a95891f5572b09459253d0fb18dcbf32`，与作者冻结值一致。

比较器仍验证原 baseline 的 2,154 项 inventory 和 outcome hash `fa3518ccc5ebb3c7c4c132869c26d13036d00bca4758762b257410559f7ccf94`，没有删除这个 AuthStorage case，也未改变原 3 个 Base failures 与 50 skips 的规则。新识别仅针对该固定 testcase：允许固定 retry2 对应的 1–3 个 failure 元素，且每个的类型、完整 old/new message 和 `137:22` stack 位置都匹配已复现断言；同 case 的其他断言、error、skip 或超过三个 failure 不获得条件处理。比较层要求此 case 原本 passed、当前 failed，并继续拒绝其余原 passed 项的失败、skip、缺项以及任何新增 case。它不是任意失败数量预算。

三个原始 Base 失败 XML 的实测 hash 与 pins 对应条目相同。比较器仅读取输入 XML，在另一个 JSON summary 中记录 `observed_known_base_failures`，不改原始失败 XML。test.sh 保留 raw P2P exit code，并由 inventory/outcome 比较结果决定 P2P 门禁；目标 contract/lifecycle 仍须各自完整通过。六个 integrity selftest 的源码覆盖匹配断言、三个同类 retry failure、混入其他断言、error、skip、错误身份/位置、其他 testcase 回归和完整性边界；本次审查没有执行这些测试，作者报告六项通过。

静态检查没有发现本次窄化识别扩大为其他 testcase 失败豁免。该处理的适用前提是已核对的冻结源文件、原始 JUnit 和当前同一环境；它不是对任意候选运行时篡改的安全保证。先前文档中的“sole failure element”已同步成固定 retry2 的 1–3 个且全部同类 fingerprint；审查者重新读取本地 `baseline-environment.md`（SHA-256 `251b08cafab3468ed8b471099e90ed6f08374653a407eb2f360b1846e6352156`）确认描述相符。最终完整 Harbor 矩阵也实际执行了该路径，见下文。

## 正式运行证据与最终矩阵

已独立核对的正式 Oracle smoke：`matrix-smoke-ready-20260915/jobs/pi-plan-mode--oracle/oracle__EjdGt7U`，trial ID `37419ba1-ab45-4cb2-9a3e-6997c1d26581`，输入 checksum `b55b5162b04e746770f2c735db1916a745257f6d7433d7a775d83ff4853b8d3d`，Harbor 0.23.0。UTC 04:36:43 至 04:39:01，验证层约 121 秒。scope 通过；P2P 2,154/2,154、无 missing/extra/regression；contract 18/18 和 lifecycle 4/4 无 failure/error/skip；C00、C15、L04 在完整 JUnit 中且通过，worker 日志 UID 65534。prepared instruction、test.sh、preload、Oracle patch hash 与当前 staging 一致。日志从容器收集至上述 host 目录，证明该次 verifier artifact transfer/collection 已完成。该 run 只代表 Oracle，不代替全矩阵。

首轮完整 matrix 的记录为 `validation/initial-matrix-evidence.json`，全部 11 个 trial 已完成且无 Harbor errors；不是最终通过证据。审查者 SSH 读取了下列控制的原始 JUnit，失败 case、assertion 和该文件记录的原始 artifact hash 相符。全部 8 个控制的 P2P 都通过，排除了 R5 或环境失败偶然造成 reward 0 的解释。

| 负控制 | 原始观测与失败层 | 结论 |
| --- | --- | --- |
| `accept-stale-revision` | C06 接受旧 revision，ok true/mode approved/revision 2；C15 用旧 UI 选择批准了 unreviewed v2 | 因版本绑定缺陷拒绝 |
| `accept-extension-control` | C07 的 extension-origin enter 被接受，normal 变 planning，未返回 forbidden_source | 因输入来源限制缺陷拒绝 |
| `replay-duplicate-approval` | C10 第二次同版本批准后 provider callCount 5，预期保持 4 | 因重复调度拒绝 |
| `allow-custom-planning-tools` | C02 多出 verifier_effect；C09 实际产生不应存在的副作用文件；L01 恢复仍多出 custom tool | 因规划工具限制缺陷拒绝 |
| `replay-approved-resume` | L02 恢复后的 provider callCount 为 1，预期 0；contract 18项全过 | 因恢复重放拒绝 |
| `resume-original-toolset` | L01 规划恢复工具集合多出 write 和 verifier_effect；contract 18项全过 | 因恢复工具集合缺陷拒绝 |
| `drop-approved-request-context` | C10 实际请求可见文本只有 inspect/Draft ready，不含批准身份；持久化和其他生命周期检查通过 | 因批准快照未送到模型拒绝 |
| `early-exit-zero` | C01–C17 在 extension factory 触发 process.exit(0) 被 Vitest拦截；L01–L04独立Node真实status0但无payload；C00通过 | 因未完成目标行为拒绝 |

提前退出 patch SHA-256 为 `78d313aacd2f5638f45567ae6251259e2e10ae514debf93953bd913af0238145`；正式 trial `early-exit-zero__TcRxnjY`。其 contract XML SHA-256 为 `ca2ba93a0c27e3d22140ddfab9a8a871f3e84726a39dbce340b57b308323a15e`，lifecycle XML 为 `ec77fda9a8e21ae325fb128dc20d908d7bdc4869a33920cccf7c68f7b1da1022`。原始路径及其余控制 hash 保留在 initial matrix evidence 中。

最终矩阵为开发机 `/data00/home/xingjunqian/harbor-workspace/pi-plan-mode/matrix-final-verified-20260915`。11 个 trial 在 2026-09-15 04:50–04:55 UTC 完成，全部 `completed=1`、`errored=0`，每项实际 reward 与其冻结预期相同。`e2e-evidence.json` 保存完整 case 集合、image、命令、prepared snapshot、job/result 与原始 XML/JSON/log hashes；审查者读取了该 evidence、collector 源码和开发机原始结果，没有重跑或生成程序。

| 最终 case / trial | Reward | 独立核对的决定性结果 |
| --- | ---: | --- |
| Base / `base__mwq2KXY` | 0 | scope/P2P通过；C00通过，17项业务和4项生命周期因目标能力缺失失败 |
| Oracle / `oracle__GkjdFwQ` | 1 | scope、P2P 2,154项、contract18、lifecycle4全通过；没有已知Base失败 |
| Alternative / `alternative-event-journal__Xsnwrfs` | 1 | 与Oracle同一最终verifier，所有层通过；没有已知Base失败 |
| Stale revision / `accept-stale-revision__DYHCCFZ` | 0 | C06接受旧版本，C15旧UI选择批准未审v2 |
| Extension source / `accept-extension-control__4qnJEmF` | 0 | C07接受extension-origin enter，错误从normal进入planning |
| Duplicate approval / `replay-duplicate-approval__n9qfkhN` | 0 | C10重复审批令provider请求数5而非4；原有AuthStorage失败被单独记录，未掩盖业务失败 |
| Planning tools / `allow-custom-planning-tools__qkvKnUJ` | 0 | C02/L01多出verifier_effect；C09真实生成禁止的副作用文件 |
| Resume replay / `replay-approved-resume__HGxPmtV` | 0 | L02恢复时provider请求数1而非0，contract18通过 |
| Resume tools / `resume-original-toolset__x2CS6LZ` | 0 | L01规划恢复工具中多出write和verifier_effect，contract18通过 |
| Request context / `drop-approved-request-context__zFTPKno` | 0 | C10实际请求缺批准身份，其他目标检查通过 |
| Early exit / `early-exit-zero__uzVzbwn` | 0 | C00通过；C01–C17被Vitest捕获零退出；L01–L04独立Node实际零退出但无观察payload，均被拒绝 |

所有最终 trial 的 scope 和 P2P 比较门禁通过，2,154 项完整，没有 missing/extra 或其他 regression。Oracle/alternative 的原始 P2P exit code 都为 0，`observed_known_base_failures=[]`，因而不是凭已知失败条件才得到 1。Duplicate 和 early-exit 的原始 P2P exit code 为 1；审查者直接读取两份原始 XML，均仅包含该 AuthStorage case 的三个同一 old/new AssertionError（137:22），summary 如实列入 `observed_known_base_failures`。两项控制仍因各自目标缺陷得到 0，证明新条件没有吞掉目标失败。

最终 early-exit 原始 contract XML SHA-256 为 `d6e1e76dfcde1ec32ec81eeb81bf50066b59988bc43848d29678a0b31d737ff4`，lifecycle XML 为 `cf910e219237236b0dd6d1829d9e52555d997e2fc742dc65cc72d956edd051b0`，P2P XML 为 `85784dabbe3b2b8d4f3c34d42a044d7851688a63aedc7d40fcfb92d63fb0c666`；开发机直接计算值与 evidence 相同。其“零退出但未完成”的失败机制与首轮一致，没有借无关P2P失败凑成负例。

最终 Oracle trial ID 为 `6b8e8093-54b5-45b9-b3c0-aca8a44234ab`，alternative 为 `5a0ba7e3-5eb1-4ffc-b10a-439a3fcad57f`；前者 task checksum `f8cc8d818e9830dca23f1fea9620bd593956f1a647e989f3288f73c6a216a5ea`，后者因替换解答 patch 为 `e2715ccd4fe83a9571749cd2de0afcf06ade6bda2ce5cc62e3ac4c53e21396c4`。collector 对 11 个 prepared task 都验证最终 instruction/tests 字节一致，并核对期望case集合、image、scope/P2P、目标行为结果和reward；它是作者证据汇总，不改变 Harbor 判分。

本报告将任务保留为已完成作者验证的开发草稿。公开已有 Plan Mode 的污染可能、尚无真实 coding-agent 轨迹或经验难度数据、镜像未发布及未来浮动OS仓库重建差异、同worker任意断言篡改未获万能防御，均继续披露。正常idle关闭/恢复以外的crash、fork/tree/reload、in-flight shutdown和任意shell只读隔离不在任务契约内。

验收必须以最终 executable hash、实际 image identity 和正式 Harbor job/result 为准。若之后只更新本报告等 evidence 文档，可以单独说明目录 checksum 的自引用变化；改变 instruction、environment、solution、tests 或 controls 则必须重跑受影响验证。本报告不授权 commit、push 或 PR。
