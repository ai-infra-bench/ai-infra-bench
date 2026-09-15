# 模型迁移题：按 #75 session 方法复审（2026-09-13）

**任务值得保留，但 v0.0.5 不能据现有全绿结果批准合入。发现两个 P1 实现／评分问题，以及一个 P1 历史观测缺口。** 本轮只增加独立反例与审查证据，没有改正式题面、参考补丁、verifier、镜像配置或历史模型成绩。

## 方法与范围

采用用户提供的 review session 方法，并应用仓库 `ai-infra-bench-task-review` skill。方法摘要见 `session-review-method-20260913.md`：从题面推导契约，双向检查需求与断言，独立挑战 Oracle，核实合法输入与真实失败原因，分别检查漏判、额外扣分及观察者自身错误。

当前审查对象是 `dsh-session-model-migration` v0.0.5。repo HEAD `ee32cad166ca065f02945bda6b2f6dca3a025ddd`；任务与部分其他目录未跟踪，其他已有修改不属于本轮。冻结并核对了已有清单的全部 38 个执行／环境文件哈希，均未变化。实际 skill 文件、附件来源哈希、工作区状态记录于证据 `context.json`。

## P1-1：Oracle 丢失只有 reasoning 的历史 assistant，正式测试漏检

题面明确要求开启 `chatReasoningText` 时保留无工具调用 assistant 的可用 reasoning，没有要求这类消息必须另有非空正文。现有 SDK 测试的无工具消息固定包含 `Source finished.`，进程测试固定包含 `Invoices inspected.`，两层共享了同一输入盲点。

独立反例只把源提供方最后一次 SSE completion 的正文从 `Invoices inspected.` 改为 `''`，保留 `reasoning_content: "Both values have been verified."` 和正常 `stop`。输入经过真实 DSH、真实 SDK 和真实 Bash 工具；没有手工构造 Session 内部事件。checked 迁移成功，第一进程正常退出，第二个 PID 从磁盘恢复后继续。

完整磁盘解码确认 `assistant/message` seq 34 的 content 正好为一条 reasoning，source 仍为 `origin/old-model`。但是目标请求只剩先前带工具的 assistant，这段 reasoning 及所属 assistant 整体缺失。跨 provider 和同 provider 换 model 均复现 `assistant history missing`。

同一 Oracle 此前在冻结的正式 `/tests/test.sh` 中为 **36/36 + 7/7，reward=1**。这证明已有全绿不能覆盖题面承诺。原因是 Oracle 的 `projectChatReasoning` 只投影 SDK Context；固定 pi-ai Chat serializer 随后执行 `if (!hasContent && !assistantMsg.tool_calls) continue`，即使存在 `reasoning_content` 也丢弃消息。SDK 实际文件路径、相关行及哈希见 `sdk-inspection.jsonl`。

定位：`tests/chat-reasoning.spec.ts:10`、`tests/process/run.py:232`；参考补丁内 `packages/llm/llm-pi-ai/src/chat-reasoning.ts` 及 adapter 投影调用。

修复方向：在最终 Chat 请求层保留这类 assistant 的 reasoning 和位置；不能通过捏造正文规避 SDK。将反例接入正式 SDK 和冷恢复行为测试，并保留当前 Oracle 作为错误对照。

## P1-2：两条配置测试把未约定的错误文案变成得分条件

`tests/chat-reasoning.spec.ts:46` 和 `:51` 使用 `.toThrow(/chatReasoningText/)`。题面要求拒绝错误协议及非 boolean 配置，并不要求异常字符串含这个字面字段名。

构造的完整补丁与 Oracle 仅差两条错误提示：

- `chatReasoningText must be boolean` → `plaintext Chat replay option must be boolean`。
- `chatReasoningText requires every resolved model to use openai-completions` → `plaintext Chat replay requires every resolved model to use openai-completions`。

验证条件、抛错位置、异常类型和全部业务行为均不变，提示仍解释问题。实际在相同干净 verifier 镜像、无网、正式 `/tests/test.sh` 下运行，结果 **34/36 + 7/7，reward=0**；恰好只有上述两个文案匹配断言失败。完整差异见 `wording-only.diff`。

这是可复现的额外扣分条件。这里称它为“行为等价的报错变体”，不因为其余测试通过就宣称整个实现满足全部契约：它仍继承 P1-1 的 Oracle 缺陷。

修复方向：断言合法的配置校验拒绝与有解释的错误，去掉未公开的固定文案要求；保留这个变体为公平性对照。不要反过来在题面增加固定报错字符串。

## P1-3：磁盘历史不可变断言只看到了 Zstd 第一帧

`tests/process/run.py:165` 对整个多帧文件调用一次 `zstdDecompressSync`。该运行时只返回第一帧，会话第一帧恰好只有 `type: session` 元数据。后面的历史前缀断言比较的是这个头部，而非真实事件；虽然记录了文件 SHA，比较逻辑并未使用它。

独立系统 libzstd 解码每一帧后，同一主会话文件是 **39 行**，旧观察器只得到 **1 行**；sibling 是 **20 行**，旧观察器仍只有 **1 行**。因此之前“durable history prefix 未改变”的证据不足，不能继续按完整磁盘历史验收解释。

另外直接调用冻结 `/tests/process/run.py` 的 `disk()` 和原前缀判定：在合法多帧文件中只将既存 `assistant/message` seq 22 的 `time` 加 1，保留头部、事件数量与全部其他内容。旧判定仍接受，而完整解码比较拒绝，文件 SHA 也不同。见 `disk-mutation-result.json`。这是实际观察函数的反例；**没有将它夸大为完整恶意补丁绕过 reward**。

修复方向：独立、完整解码所有帧，确认观察结果包含真实 assistant、tool result 和选择事件，再比较语义事件前缀；保留“只改持久化事件、内存历史不变”的负例。不应通过加载候选自带解码代码来承担可信判定。

## 三个审查门

| 门 | 结论 | 依据与界限 |
|---|---|---|
| 题面真实性与风格 | 可以保留 | 模型迁移、额度归属、历史配对和冷恢复是可实现需求；扩展 reasoning 格式明确限定兼容网关，并未声称所有公开 Responses 端点支持。容量段虽密集，但边界都影响可观察行为，没有必要为缩短而删掉。 |
| 环境可解性 | 当前未发现新阻断 | Base、锁文件及镜像身份未变化；本轮从固定 verifier 应用完整补丁，重建 host 后跑通正式 Oracle。复用此前匹配哈希的 agent 镜像、Base 普通生成／恢复和 Harbor 证据，未重新完整构建 canonical Dockerfile 或重新检查所有镜像层。 |
| verifier 有效性、公平性 | 不批准，需修复 | P1-1 漏检，P1-2 额外扣分，P1-3 观察缺口均有实测；36+7 全绿不足以推翻这些反例。 |

语义边界为：公开会话操作／输入 → Session Controller admission、AgentLoop、SDK 请求序列化、真实工具、持久化恢复 → 目标 HTTP 请求、工具结果、重启后的选择／额度及历史。外部模型计算可以由先检查请求再返回固定 SSE 的提供方替代；这轮测的是 DSH 行为，不是模型推理质量。源与目标调用、工具、进程及磁盘恢复均真实执行。

## 双向契约核对

下表按语义合并参数化案例；原始 36 个 case 名称仍以冻结 `expected-tests.json` 为准。

| 契约／扣分条件 | 当前观察与测试 | 审查结论 |
|---|---|---|
| token-meter 对目标重估历史、system、tools，输入+输出 exact fit | budget exact-fit 与 headerless 对照、差 1 拒绝、同路重查 | 有目标边界观察；非任意 tokenizer 精确度要求 |
| 已知 context/output capacity，显式额度不能超过硬上限 | unknown capacity 两例、capacity-reopen 超限例 | 有正反例 |
| 输出额度持久、首次请求前及再次选路不丢失 | 三个 explicit reopen、empty-same/third 实进程 | 同时覆盖 seed 恢复和实际冷恢复 |
| 默认额度归目标，不捏造 request default | destination-default、连续迁移、catalog capacity 两例、defaults 进程 | 请求字段与内部 header 同时观察；catalog 夹具来自 Base 已有边界 |
| idle、无 pending、检查期间无变化 | queued、running、catalog gate 中 append 后 clear | gate 延迟真实异步依赖，检查先后关系，不依赖总耗时 |
| admission 不生成，不改旧状态／默认／其他会话 | 多案例检查请求数、事件前缀、sibling、catalog/settings；reject 冷恢复 | 存在外部观察；磁盘前缀部分受 P1-3 限制 |
| legacy selection 保持旧行为 | legacy 容量不足仍选路且保存默认 | 明确来自题面“不带 option 保持行为” |
| Responses plaintext、顺序、foreign opaque 不冒充 native | migration、replay provider/model | 请求级别观察；未要求 Oracle 的新 helper |
| parallel/provider IDs 正确配对 | 六组 collision + 实际 tool result | 观察 id 的唯一性与配对，不限定具体新 id 算法 |
| same-route native replay 保持 | Responses native opaque、Chat native reason/tool | 有实际后续请求观察 |
| 不凭空生成 reasoning、关闭 option 保持序列化 | replay 无 reasoning 两例、disabled；Chat enabled=false | 有正反例 |
| Chat 无工具 assistant reasoning | Chat enabled=true、chat-provider/model | 只覆盖正文非空；P1-1 |
| option boolean／协议限制／catalog 继承 API | boundaries、Responses invalid、两项 Chat invalid | 拒绝有题面依据，固定错误文案没有；P1-2 |
| 不重写磁盘历史与 provenance | process `disk` / 前缀比较 | 实际只比较 header；P1-3。内存 snapshot 不能替代这个要求 |
| 测试完成性和 reward 所有权 | root grader、UID 65534 build/worker、固定 case 集合 | 保留此前 early-exit/forged-report 的具体证明；不声称已防住任意代码攻击 |
| 类型、配置、文档和集成覆盖 | Oracle 静态变更及真实运行 | 本轮未给全部候选做完整类型检查，未增加以文件名或文档措辞决定 reward 的规则 |

## 实际运行与证据范围

| 本轮运行 | SDK／操作 | 正式进程 | 结果 |
|---|---:|---:|---|
| 完整冻结 Oracle 正式入口 | 36/36 | 7/7 | reward 1 |
| 仅错误提示变体正式入口 | 34/36 | 7/7 | reward 0，恰好两个文案断言失败 |
| Oracle：reasoning-only 跨 provider | — | 独立完整 DSH 场景 | 丢失已持久化 assistant |
| Oracle：reasoning-only 同 provider 换 model | — | 独立完整 DSH 场景 | 同样丢失 |
| 旧磁盘观察器 + 合法事件时间变更 | — | 独立观察函数 | 接受已变化历史；完整解码能区分 |

最初 reasoning-only 探针和加入完整解码后的探针均复现目标请求缺失。第一次完整解码尝试因诊断代码未处理 Zstd 未声明原始大小的帧而退出；随后修正诊断代码，以有界 buffer 解码并复跑两条路径。该次基础设施失败保留在归档，未算成产品缺陷。最终完整解码读到了源 assistant/message，才确认 P1-1。

本轮运行使用 Docker `--network=none`，正式镜像 `sha256:54ea499b323969650ba28c996a91e075289373c4870aa2137230615cd7cf651f`；独立探针从已评分 Oracle 容器保留的本地快照运行，快照 `sha256:8711dee4864409a268c92780ba10318f0cbb14ae6bfd67082205162a236a6595`。没有新的 Harbor orchestration 运行，不将直接 Docker 正式脚本运行称为新 Harbor 验收。

之前 Base、正确替代、10 个错误对照及 Harbor 控制结果仍是该冻结版本的历史证据，见 `v005-review.md`；它们不证明本次发现的输入分支正确。原始 8 个 GPT-6／GPT-5.6 完整补丁哈希本轮逐一核对一致，已有 patch 重评分结论见 `v005-eight-patch-regrade.md`。新 Chat 契约不能追溯作为旧模型的解题失误；本轮没有重新逐条阅读 8 条完整轨迹，也没有新模型调用或重算 pass@4。

## 建议后续顺序

先修 Oracle 的 reasoning-only replay 和磁盘观察器，再去掉未声明的文案限制；将当前 Oracle、报错变体、持久化事件变更纳入对照。先复验受影响路径，再运行完整正式矩阵和必要 Harbor 入口。题面无需为这三个问题增加 Oracle 专属要求。

本次交付是审查结论与反例证据，三个问题尚未修复。没有 commit、push，也没有修改正式 v0.0.5 执行输入或历史分数。
