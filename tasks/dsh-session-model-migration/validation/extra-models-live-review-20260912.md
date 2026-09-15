# 两个新增模型的真实接口与迁移验收

日期：2026-09-12。用户指定模型名：`ali-deepseek-v4-pro`、`Minimax-M3`。
沿用用户给出的 AIDP 网关和已有实验凭证，全程请求 `high`。

## 结论

两个模型的 Chat Completions 路由均可返回明文 reasoning、调用工具。
修正 DeepSeek 的角色兼容配置后，两个方向的真实会话迁移、进程退出重启、
工具续接及报告验收均通过。每个方向各一次修正后的完整尝试，不是 pass@k 实验。

两者在当前 AIDP 路由均不支持 Responses。Chat 迁移中，SDK 将外来 reasoning
转为普通 assistant 文本。因此这次结果不能证明题面的
`responsesReasoningText` / `reasoning_text` 扩展已经在真实网关通过。
没有因此改写题面、Oracle 或原始 32 项 verifier，也没有改动原 pass@4 结论。

## 接口探针

| 模型 | Chat：high + tools | 明文 reasoning | Responses |
| --- | --- | --- | --- |
| ali-deepseek-v4-pro | HTTP 200，发起工具调用 | 有 | HTTP 400 / -1026 |
| Minimax-M3 | HTTP 200，发起工具调用 | 有 | HTTP 400 / -1026 |

Chat：`https://aidp.bytedance.net/api/modelhub/online/v2/crawl`。
Responses：`https://aidp.bytedance.net/api/modelhub/online/responses`。
Responses 返回：`the current product doesn't support response API`。
这是所测网关产品路由的限制，不能推广为 DeepSeek 官方 Responses 不支持。
最初四个探针仅确认模型返回工具调用；实际工具执行由下面的进程验收覆盖。

## 完整尝试记录

| 尝试 | 方向 | 结果 | 说明 |
| --- | --- | --- | --- |
| 初始 1 | DeepSeek → Minimax | 失败，源推理阶段 | DeepSeek 不接受 SDK 默认 developer 角色 |
| 初始 2 | Minimax → DeepSeek | 失败，目标推理阶段 | Minimax 已读取文件并迁移重启，DeepSeek 拒绝 developer 角色 |
| 修正 1 | DeepSeek → Minimax | Chat 会话续接通过 | 5 个实际请求全部 HTTP 200 / high |
| 修正 2 | Minimax → DeepSeek | Chat 会话续接通过 | 5 个实际请求全部 HTTP 200 / high |

通过既有配置设置 DeepSeek `supportsDeveloperRole: false`、
`maxTokensField: max_tokens`、`supportsStore: false`，没有修改模型响应或代理中的
请求历史。初始 Minimax 曾按自己假设的 `/repo` 路径读文件失败，随后自行找到了
正确文件；修正后的提示直接提供绝对文件路径，不提供金额或报告答案。
两版 runner 和所有失败证据均保留，没有静默重试或丢弃失败。

## 真实行为和核验边界

运行完整 Oracle 的已构建镜像：
`sha256:15028d491ca4830758c76af7cf51c1412fc404965d54ed3de8acea524cb8ade0`。
真实 `dsh web` CLI、Session Remote、Agent loop、SDK、磁盘 JSONL/Zstandard
和文件工具全部参与；代理只转发真实模型计算结果，不脚本化输出。

1. 源模型通过两个独立工具调用读取发票 A=137、B=251。
2. 空闲时 checked migration，不产生模型推理请求。
3. 第一进程实际退出；新 PID 启动并从原磁盘恢复同一个 session。
4. 目标请求包含两组 ID 唯一、调用与结果配对的历史工具数据。
5. 目标模型实际写入 `report.txt`，再调用工具核验内容。
6. 父进程独立读取文件，检查严格三行 `A=137\nB=251\nTotal=388\n`；
   比较持久化逻辑事件前缀，确认原有历史没有被改写。

独立证据复核：DeepSeek → Minimax 的容器内 PID 为 11 → 31；
Minimax → DeepSeek 为 11 → 36。每个方向源请求 2 次、目标请求 3 次。
DeepSeek 源返回 253 字符明文 reasoning，Minimax 源返回 303 字符；
两者完整明文均出现在目标 assistant 文本中，均未进入 reasoning 字段。
该观测是普通 Chat 投影的行为，不应当被计为 Responses 扩展成功。

声明的 65,536 上下文 / 16,384 输出额度属于保守测试配置，不是对真实模型
容量上限的测量。本轮也不替代已有的容量拒绝、竞态、caller allowance 等测试。
测试父进程和候选仍共享容器 UID，本套验收尚未升级为对抗性计分 verifier。

## 证据与后续

归档：`extra-models-live-evidence-20260912.tar.gz`，旁附 SHA-256 文件。
内容含四个接口探针、四次完整尝试、两版冻结 runner、请求/响应、
Remote 记录、进程启动与退出记录、磁盘快照和报告文件。
原始工作目录：`/tmp/aib-extra-models-live-20260912`。
所有本轮 Docker 容器和凭证代理均已停止并移除/退出。

要完成题目核心扩展的真实验收，仍需一个接受明文 reasoning 输入的真实
Responses 路由。DeepSeek 官方文档声明支持，但本轮给定的 AIDP 模型路由
没有开放该 API；不能用 Chat 通过或代理协议转换替代这项验收。
