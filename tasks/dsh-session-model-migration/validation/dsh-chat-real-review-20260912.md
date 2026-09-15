# 完整 DSH 链路的真实 Chat 迁移验收

2026-09-12。本轮使用实际 DSH CLI、Session Remote、SDK、模型推理、工具执行
和磁盘恢复。先证明现有实现被严格测试判失败，再修复 DSH 适配层并重跑两方向。
不使用直接 Python API 探针代替 DSH。

## 结果

| 完整进程尝试 | 实际推理请求 | reasoning 字段 | 结果 |
| --- | --- | --- | --- |
| 现有 Oracle，DeepSeek → Minimax | 2 + 3，均 HTTP 200 | 249 字符被转为 assistant 文本 | 严格测试失败 |
| Oracle + Chat 补丁，DeepSeek → Minimax | 2 + 3，均 HTTP 200 | 319 字符保留在 reasoning_content | 通过 |
| Oracle + Chat 补丁，Minimax → DeepSeek | 3 + 3，均 HTTP 200 | 321 字符保留在 reasoning_content | 通过 |

使用模型原名 `ali-deepseek-v4-pro` / `Minimax-M3`，所有请求均发送
`reasoning_effort: high`。地址为 AIDP `online/v2/crawl`。
本轮没有自动重试。失败基线及成功运行全部保留。

## 真正运行的链路

1. Node 启动 `apps/cli/src/bin.ts web`，使用真实最小 preset 和 JSONL/Zstandard 持久化。
2. 父测试通过 HTTP Session Remote 创建 session，并提交读取两份发票的用户请求。
3. 模型通过 DSH 的实际文件/命令工具获得金额 137、251。
4. 父测试调用 `selectModel(..., migration: "checked")`；校验阶段不发推理请求。
5. 第一 DSH 进程退出，父测试等待完成；启动不同 PID，恢复同一磁盘 session。
6. 目标模型收到保留的历史，并通过 DSH 工具写入和核验 `report.txt`。
7. 父测试读取实际文件，核对三行 A=137、B=251、Total=388，并检查持久化历史前缀没有改变。

成功运行的容器内 DSH PID 分别为 265 → 509、278 → 490；四次退出均为
exit 0 且 `forced: false`。恢复阶段没有手工复制内存消息，也没有注入迁移选择。

联网容器通过转发代理访问实际模型。代理只保管凭证、设置 affinity 并记录原始
请求/响应，不改写 reasoning、历史或工具结果。DSH 本身仍经过完整 pi-ai SDK。
这是联网实测环境（Docker `--network=host`），不是正式无网 grader 的运行记录。

## 测试补强

`run-live.py --require-reasoning-field` 要求：

- 源推理确实产生非空 reasoning，没有源 reasoning 不能算覆盖通过。
- 目标指定 reasoning 字段包含源明文，只有普通 assistant 文本不通过。
- 在目标每一次请求上，逐个比对源 assistant 的 reasoning 文本、顺序及工具名称/参数，确认关联未移动。
- 原有工具配对、实际报告写入/读取、干净退出、冷恢复、磁盘前缀保持仍须通过。

报告验收按恰好三行正确数据比较，接受有无末尾换行，避免用无关排版决定迁移成败。
基线真实跑完工具和重启仍被 reasoning 断言判失败，证明最终报告正确不会掩盖字段丢失。

## DSH 适配层修复

`process-e2e/chat-reasoning.patch` 是叠加在历史 v0.0.4 Oracle 上的独立验证补丁：

- 增加显式 `chatReasoningText` provider 配置，默认 false，仅允许 Chat 路由。
- 在 DSH 适配器中构造独立的请求 projection，把可用外来明文映射到 Chat `reasoning_content`。
- 丢弃外来的不透明 replay 元数据；给外来工具调用生成不冲突的合法 ID，并同步配对结果。
- 同路由原生回放保持原对象；持久化事件不修改。

当前 pi-ai 的 Chat serializer 用 `thinkingSignature` 作为 reasoning 字段名称选择器。
补丁设置的是新的固定字符串 `reasoning_content`，不是复制或伪造其他模型的加密签名。
投影之后仍调用真实 SDK 进行序列化和推理。

完整候选源码补丁（含 Oracle）已随证据保存，SHA-256：
`4170b0e6048b2cf8ffca78bb913a0bd880315f2a035c131a28ce2ae130c103ad`。
父镜像：`sha256:15028d491ca4830758c76af7cf51c1412fc404965d54ed3de8acea524cb8ade0`。
Base commit：`4e84901e6471b79ec0338099867ebb4606d12bb5`。

## 回归与范围

- 原有 32 项测试全部通过，独立检查用例名称 multiset 与冻结清单一致。
- 新增 4 项实际 SDK / HTTP 测试通过，覆盖开关关闭/开启、源与目标原生工具续接、配对及配置拒绝。
- host 运行资产重新构建成功；新 Chat projection 文件的严格 TypeScript 检查通过。
- 未宣称整仓 typecheck 通过：此前 Oracle 的测试类型错误不在本轮修复范围。

这是对“Oracle + Chat 适配补丁”的真实行为验收。正式 v0.0.4 题面仍只声明
Responses 扩展，新的 Chat 契约、补丁及测试尚未并入正式题面和无网计分 verifier；
不能据此更新原八条轨迹的分数或宣称原始 Oracle 已具备该能力。

父测试仍与候选共享容器 UID，本轮为可信实现验收；正式计分需沿用独立 verifier
的可信父进程隔离。所有本轮临时容器和转发代理已停止。

## 证据

`dsh-chat-real-evidence-20260912.tar.gz` 及其 SHA-256 文件保存：三次实际运行、
请求/响应、CLI 启动/退出、Session Remote 记录、磁盘快照、报告文件、冻结 runner、
完整候选补丁、构建/类型检查日志和 32 + 4 项回归结果。
本地工作目录：`/tmp/aib-dsh-chat-real-20260912`。
