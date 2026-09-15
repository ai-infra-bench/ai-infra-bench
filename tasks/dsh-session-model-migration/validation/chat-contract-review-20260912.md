# Chat 明文 reasoning 迁移：实测与接口文档对照

2026-09-12，先使用已经可用的 AIDP Chat Completions 接口完成真实行为测试，
再读取官方接口文档。没有继续探测尚未确认的 Responses URL。

## 已实测成立的契约

在 `https://aidp.bytedance.net/api/modelhub/online/v2/crawl`，
`ali-deepseek-v4-pro` 和 `Minimax-M3` 可以互相接续携带明文
`reasoning_content` 的工具会话。两个方向均在 `reasoning_effort: high` 下
完成真实推理、文件工具执行、落盘、换进程和目标工具续接。

| 修正观察点后的尝试 | 真实请求 | 源/目标进程 PID | 结果 |
| --- | --- | --- | --- |
| DeepSeek → Minimax | 2 + 3，全部 HTTP 200 | 4089280 → 4089730 | 通过，603 + 505 = 1108 |
| Minimax → DeepSeek | 2 + 3，全部 HTTP 200 | 4089288 → 4089728 | 通过，121 + 789 = 910 |

工具文件包含每次独立生成的金额，提示没有提供答案。源模型实际调用两次
`read_invoice`；目标模型只能利用恢复的历史，不能重读发票，随后实际调用
`write_report` 和 `read_report`。源进程退出后才启动目标进程。

独立证据检查确认：

- 源 assistant 消息含有与工具调用同条记录的非空 `reasoning_content`。
- 每个目标请求的历史前缀与源磁盘 transcript 完全相同，字段、内容、关联和顺序均保留。
- 两组工具 ID 唯一、调用与结果配对；目标未重读源文件。
- 目标写出的报告三行数据正确，实际读文件结果再次提交给模型。
- 源 transcript 文件在目标执行前后的 SHA-256 相同。

这里的“保留”是对请求字段和历史完整性的可观察保证。HTTP 200 和任务完成
不能单独证明内部模型如何使用每个 reasoning 字符，也不证明删除 reasoning
一定使这道算术任务失败。

## 保留的初始失败与观察点修正

第一版同样跑了两个方向。DeepSeek → Minimax 通过；Minimax → DeepSeek
完成全部真实请求和工具执行，正确写出 536、356、892，但末尾没有换行。
父测试按逐字节比较判失败。这个失败来自额外的格式要求，不能归因为迁移失败。

第二版只要求报告恰有三行且数据正确，接受有或无末尾换行，并相应删除提示中的
末尾换行要求。它仍会拒绝金额错误、多余行、未写文件、未真实核验、历史被改写、
源 reasoning 缺失或目标绕过历史重读源文件。然后两个方向各运行一次新尝试。
两版脚本、四次结果和所有请求都已保留；无自动重试，不计算 pass@k。

## 与 DSH 验收的区别

本轮新增 `process-e2e/chat-contract.py` 是直接调用真实 API 的协议实验，
使用独立的 Python 文件工具，不经过 DSH、pi-ai 或 forwarding proxy。
它确认候选接口契约可实际使用，不能替代对 DSH 实现的验收。

之前的真实 DSH CLI / Remote / 磁盘恢复测试已证明两方向能继续工具工作，
同时发现 SDK 将外来 reasoning 转成普通 assistant 文本。
所以现在证据是：**接口有可用路径，DSH 的 Chat 明文 reasoning 字段迁移仍需适配。**
没有把本轮结果算作现有 Responses 扩展通过，也没有改动正式题面、Oracle、
32 项 verifier 或已有八条轨迹的分数。

## 测试完成后核对的官方文档

全部页面于本轮实际读取并归档，不将当前文档当作 benchmark cutoff 之前的证据。

| 接口 | 官方说明 | 对题目契约的影响 |
| --- | --- | --- |
| [DeepSeek Chat thinking mode](https://api-docs.deepseek.com/guides/thinking_mode/) | 请求带 `tools` 时，所有之前轮次的 `reasoning_content` 均须完整回传，包括没有调用工具的 assistant 轮次；不带 tools 时该字段会被忽略。 | 测试必须包含工具循环，覆盖每个已有 reasoning 记录，不能只测 hello 或最终文本。 |
| [MiniMax OpenAI compatible API](https://platform.minimax.io/docs/api-reference/text-openai-api) | 多轮工具调用要求回传完整 assistant；原生格式可将思考放在 `content` 的 `<think>` 中，`reasoning_split` 可分离到 `reasoning_content` / `reasoning_details`。 | “OpenAI compatible” 不保证 reasoning 表示一致；AIDP 的实测字段不能被推定为每个 MiniMax 接口的默认格式。 |
| [DeepSeek Responses](https://api-docs.deepseek.com/guides/responses_api/) | 接受 reasoning item 的明文 content 并合入相邻 assistant；不支持 summary 和 encrypted_content。 | 原题明文 Responses 方向有官方文档依据，但该官方路由尚未实际调用，不应标注已通过。 |
| [OpenAI reasoning](https://developers.openai.com/api/docs/guides/reasoning) | reasoning item 是不透明状态，stateless replay 使用 encrypted_content；可见 summary 不等于原始 reasoning。 | 不可把外来明文或 summary 伪装成目标原生不透明状态，也不能把任意 Responses 路由都视为支持 reasoning_text。 |

MiniMax 的原生文档还说明 `reasoning_split` 只控制输出表示；M3 的 thinking
默认开启。本轮只确认 AIDP 接受并发送了 `reasoning_effort: high`，没有通过
内部服务观测单独核实其强度参数映射。

## 对后续题面和测试的设计结论

共同行为应是保留当前工作的上下文、可读 reasoning、assistant / tool 关联及
持久化来源。可读 reasoning 的输出字段由目标路由明确支持的格式决定。
容量准入、idle / revision 检查、caller allowance 和 session-only 选择约束不因
采用 Chat 而改变。

Chat 的 `reasoning_content` 与特定 Responses 的 `reasoning_text` 应分别有
显式配置、真实 SDK 请求断言和续接验收。选项关闭时维持既有行为；同源 native
回放维持原样；跨源 opaque 数据不伪造、不移植；原始持久历史不改写。
不能仅修改 URL 并沿用另一协议的消息结构。

下一轮 DSH 适配应以已实测的 Chat 字段契约为起点，随后用同一真实 DSH
进程验收观察目标请求，要求 reasoning 留在指定字段且后续工具正常运行。
Responses 保留为单独验证的协议，不用当前网关暂不可用的能力充当唯一验收前提。

## 证据

工作目录：`/tmp/aib-chat-contract-live-20260912`。
归档：`chat-contract-evidence-20260912.tar.gz`，旁附 SHA-256 文件。
内含四次尝试、两版脚本、实际请求/响应、真实工具结果、进程退出记录、原始
和目标 transcript、文件产物、独立核验及五份官方文档快照。
