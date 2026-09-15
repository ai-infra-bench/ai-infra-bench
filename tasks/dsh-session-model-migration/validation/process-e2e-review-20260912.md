# 模型迁移：真实进程、磁盘与模型接口验收

结论：已经增加并运行实际 DSH 进程测试，确认原来“序列化事件后重建”的测试遗漏了真实磁盘恢复；同时，真实推理暴露了当前验收后端与题面 `reasoning_text` 扩展假设不一致。不能把所有核心承诺宣布为真实验收通过。

本轮没有修改 v0.0.4 的 instruction、正式 32 项 verifier、参考补丁或原有 pass@4。新增入口位于 `process-e2e/`，目前是独立补充验收。正式计分器仍需另一次版本冻结、信任边界隔离及 Harbor 完整验证后才能纳入它。

## 后续：DeepSeek 官方接口检查

用户随后要求检查 DeepSeek。其当前[官方 Responses 文档](https://api-docs.deepseek.com/guides/responses_api)明确列出：`reasoning` 的明文 `content` 受支持，会合并进相邻 assistant 消息；`summary`、`encrypted_content` 不支持。官方工具文档也支持向 Responses 历史中插入非本模型生成的工具调用及结果。

因此，下文 GPT-5.6/GPT-6 的拒绝应限定于实测 AIDP 路由，**不能据此要求放弃题面中的 opt-in 扩展**。DeepSeek Responses 是与原契约匹配的、文档明确声明能力的真实候选目标；尚未进行带认证的 DeepSeek 实测，仍需核验具体输入形态和工具续接。

当前检查未找到 DeepSeek 专用凭证配置，已询问配置路径/环境变量名。文档及摘要保存在 `/tmp/aib-deepseek-api-review-20260912/`。这些是当前接口文档，不冒充 2026-09-01 cutoff 的历史快照；这项后续检查不在下文原始运行证据归档中。

## 真实行为边界

同一个 session ID → 真实 Session Remote checked selection → 生产持久化协调器及 JSONL/Zstandard 后端 → 第一个 CLI 主进程正常退出 → 新 CLI 进程从磁盘恢复同一会话 → 实际 pi-ai HTTP 请求 → Bash 工具执行与文件产物。

第二个进程只拿到通常启动所需的目录、配置和会话 ID，没有重新传入历史事件、seed、maxTokens 或待应用的目标选择。调用方额度通过第一进程的公共 Agent factory 输入；第二进程不加载该输入插件。没有直接构造私有 Controller 代替 Remote。

确定性模式只替代模型前向计算。HTTP/SSE 服务先检查真实请求的路由、额度、工具调用配对及可见 reasoning，再响应；验证错误时返回 422，不无条件消费成功脚本。真实 LLM 模式的代理只转发请求和模型响应，不修补历史、迁移结果或工具产物。

## 实际运行结果

Base 在构建正常运行资产后，通过普通会话的真实启动、请求、退出、磁盘恢复及续接测试（1/1）。它不是以缺少依赖或启动失败充当 feature 负例。

随后，对十份完整补丁运行相同、预先冻结的五项测试：

| 完整实现 | 新测试结果 | 具体失败 |
| --- | --- | --- |
| Oracle | 5/5 | 无 |
| 不同实现的 alternative | 5/5 | 无 |
| GPT-6 #1 | 4/5 | 两个历史调用的不同 ID 在目标请求中碰撞 |
| GPT-6 #2 | 4/5 | 同上 |
| GPT-6 #3 | 4/5 | 同上 |
| GPT-6 #4 | 5/5 | 无 |
| GPT-5.6 #1 | 3/5 | 空会话迁移、真实重启、再次选择后，调用方 73 变成目标默认 256 或第三路由默认 384 |
| GPT-5.6 #2 | 5/5 | 新的五项没有复现其另一组碰撞问题；原 32 项里的失败依旧成立 |
| GPT-5.6 #3 | 5/5 | 同上 |
| GPT-5.6 #4 | 5/5 | 同上 |

五项分别覆盖实际工具工作后迁移重启、空会话重开后选相同目标、选第三目标、容量拒绝后旧路由续接、没有调用方额度时使用目标默认值。每项还执行独立兄弟会话，比较部署配置，以及重启前后逻辑持久化记录前缀。

参考实现主流程实际运行 `cat invoice-a.txt`、`cat invoice-b.txt`，恢复后执行另一个 Bash 调用，磁盘上产生：

```text
A=137
B=251
Total=388
```

还运行了两份故意写坏的完整 Oracle 补丁：

- 只更新内存而不追加 `model/selection`：迁移当时成功，重启后首个请求实际仍使用 `old-model`，被拒绝。
- checked selection 中 `process.exit(0)`：父进程观察到 Remote 中断，整项失败，没有把子进程成功退出当作验收成功。

这是 50 个完整补丁/场景组合、一个 Base 基线和两个负例。它补充既有边界测试，不取代那些测试，也不是新的模型编码 rollout。

## 四次真实模型进程尝试

所有请求保持 `high`；没有 20 秒间隔配置、自动重试或静默重抽。每次真实尝试的失败都保留了。

| 尝试 | 路由 | 结果与范围 |
| --- | --- | --- |
| 1 | GPT-6 `v2/crawl` Completions → Responses | 第一个工具请求即返回 400：该模型在 Chat Completions 下不支持 reasoning_effort 与 function tools 组合。前置简单探针也遇到过 429 资源不足；本次明确的接口错误不能记为迁移实现失败。 |
| 2 | GPT-6 Responses → GPT-5.6 Responses，无 affinity | 真实迁移和重启已完成，目标模型开始工具工作；后续 native reasoning 请求返回 `invalid_encrypted_content`。该代理没有沿用已有实验网关的固定 `extra.session_id` 路由头。 |
| 3 | GPT-6 Responses → GPT-5.6 Responses，固定 affinity | **通过**。6 次实际模型请求全部 200；新进程中的 GPT-5.6 生成并读取验证了正确报告。源 GPT-6 没返回可用明文 reasoning，因此不将它记为真实明文 reasoning 迁移通过。 |
| 4 | GPT-5.6 Responses → GPT-6 Responses，固定 affinity | 源端完成工具工作并返回可用明文 reasoning。迁移重启后，目标收到 `input[4]` 中的 359 字符 `reasoning_text`，没有源端 opaque encrypted state；目标请求在模型生成前被 HTTP 400 拒绝。 |

第 3 次提供了真实推理、工具、持久化、进程恢复和跨实际模型续接的正例；第 4 次揭示了不能被确定性 SSE fixture 证明的外部协议能力。

## `reasoning_text` 限制是否与模型有关

不能仅凭一个模型的错误推断所有接口。我们又做了受控对照：保持第 4 次失败请求的历史、工具及 reasoning 内容，只更换目标 model 和对应凭证；另外单独测试补上 `summary: []`。

| 目标模型 | 原始 foreign reasoning 请求 | 仅补空 summary |
| --- | --- | --- |
| GPT-6 | 400：缺少 `input[4].summary` | 400：`input[4].content` 最多 0 项，实际 1 项 |
| GPT-5.6 | 同样的缺少 summary | 同样的 content 最多 0 项 |

因此，这个限制至少是当前 AIDP Responses 两条已测模型路由共有的，不是 GPT-6 特例。报错无法单独证明校验发生在网关本身还是其共同下游，也不证明所有其他网关/模型都一样。

“补 summary”只是独立定位实验，保存在 `local-probes/`；**没有**把这个修改放入转发代理或通过的 DSH 测试。它揭示第二道协议拒绝，不能视为修复。

题面把 `responsesReasoningText` 描述为面向支持该扩展的网关的 opt-in。当前提供的真实接口不满足这个前提。尚未选择下一轮契约：可以找到确实支持该输入的真实路由，或基于真实 Responses 能力重新设计可接受的明文表示。不能直接把现有测试改为允许丢弃 reasoning，也不能未经设计把另一种表示偷偷当作原契约。

## 范围和复现限制

- 现有 32 项仍负责更多 collision 家族、race、unknown capacity、disabled/native 行为，以及拒绝时精确的历史不变；新的五项不是所有边界的完整替代。
- Base 完整 `npm run build` 成功。Oracle 的 `npm run build:lib` 类型检查发现提交内测试文件的类型错误；随后使用仓库 `tsdown` 构建运行资产进行行为验收。**运行通过不等于全仓类型检查通过**；原始构建错误日志已保留。
- 五项测试中的 tokenizer、Controller、persistence、Bash 和 SDK 都真实运行；fixture 模型输出不能证明一个真实服务接受扩展字段。
- live 代理实现了已有网关需要的固定 affinity，没有修改输入历史。第 2 次失败和第 3 次修正后成功是两次不同的尝试，不能删除前者。
- 补充验收父子进程目前同 UID，尚未做正式 reward 信任边界隔离。两个负例证明了通常行为敏感性，不证明恶意候选无法攻击这个独立运行器。
- 请求模型名称与 high 已记录，不能据此声称固定了服务端模型权重版本。

## 证据

`process-e2e-evidence-20260912.tar.gz` 包含冻结测试、十份补丁的 SHA、50 项实际结果、正常与异常进程退出记录、请求与 Remote 应答、原始 Zstandard 日志、解码记录、实际工具报告、两个完整负例补丁，以及四次真实模型尝试和协议对照。API 凭证未写入证据，浏览器登录 token 已脱敏。

- 归档 SHA-256：`17df4989b66bd7c6f998b227b836b0893503d1a9b34891e527bb2260050991c0`
- 冻结构建 Base 镜像：`sha256:c31d8ae990656c65a0abec4f9518356f60d7d293fd4b095240a4c1e27621d98a`
- live Oracle 镜像：`sha256:15028d491ca4830758c76af7cf51c1412fc404965d54ed3de8acea524cb8ade0`
- 固定源 Base：`4e84901e6471b79ec0338099867ebb4606d12bb5`
- 未改动的 instruction SHA：`21a1259c807cf4d8ffe998e990aae0cd7c45aa201850d3fe9706b51bf8735c3f`
- `/tmp/aib-dsh-migration-process-e2e-design-20260912/evidence` 是便于逐文件查看的解包副本。

批量运行前后已核对完整候选补丁和确定性 suite 的 SHA 不变。本轮创建的临时测试容器和推理代理已停止、清理；运行结果与可复现镜像保留。
