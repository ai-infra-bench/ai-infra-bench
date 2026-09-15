# v0.0.5：无网真实 DSH 行为验收

> 2026-09-13 后续审查发现 reasoning-only 消息丢失未被检出、固定错误文案额外扣分，以及磁盘历史检查只解压第一帧的问题。见 [独立反例复审](session-method-review-20260913.md)。以下保留当时的实际验收结果；全绿结果不能再作为当前版本无阻断问题的结论。

可保留本题。已把补充实验中的进程恢复和 Chat reasoning 检查接入正式二元评分，并同步题面、参考实现、错误对照和镜像记录。以下结果均为实际运行。工作区改动尚未提交，也未推送。

## 契约与边界

输入／事件 → Session Controller 的 checked migration、AgentLoop、LLM/SDK 请求序列化、持久化及恢复 → 目标请求、真实工具输出、重启后的选择与不变的历史前缀。

只替换外部模型计算：本地 HTTP/SSE 提供方先断言 SDK 发出的请求，再返回固定事件。真实启动 DSH CLI web host，通过公开 Remote 操作创建、迁移和继续会话；真实执行 Bash、读写文件、退出进程，再用另一个 PID 从 JSONL/Zstd 冷恢复。没有在第二个进程注入会话、选择或额度。首次创建时的 caller 插件只调用公开 Agent factory，重启后移除。

题面新增 `chatReasoningText`（默认关闭，仅 Chat Completions），与已经真实验证的 `reasoning_content` 行为对应；包括带工具和不带工具的历史 assistant 消息。保留原有 `responsesReasoningText` 扩展契约。容量、拒绝、隔离与 durable selection 契约不变。

## 环境

Base 与依赖保持原先截止点。Agent 镜像不含测试／参考实现；verifier 预构建正常 Base 资源，再在 UID 65534 下重建候选 host 模块，避免运行旧的 Base bundle。运行和工具不需要内网端点、凭证或 GPU。15 次直接评分全部使用 Docker `--network=none`。

Docker Hub 拉取固定 Node 镜像超时，因此本次构建复用已保留、摘要固定的 Base runtime，并在禁网条件下执行相同的构建后半段。实际命令、失败日志、成功日志及 [构建文件](build-from-retained-base.Dockerfile) 均归档；不宣称完整 canonical Dockerfile 的首次拉取成功。镜像 Git 工作区干净，只含 Base 分支，未发现 remotes、tags 或不可达未来对象。

## 正式检查

36 个 SDK／业务操作测试继续覆盖容量边界、异步变化、默认值、协议投影、调用配对和拒绝；新增的 7 个进程场景均为必过项：

| 场景 | 观察结果 |
|---|---|
| main | Chat→Responses 迁移；磁盘重启；历史 reasoning 和并行调用配对；目标原生调用；真实 report.txt |
| chat-provider | 跨提供方 Chat 迁移；两条 assistant reasoning_content；继续工具执行和原生 replay |
| chat-model | 同提供方更换模型；与上例相同的真实恢复与请求约束 |
| empty-same / empty-third | 请求前迁移、关闭重开、再次选路后仍保留调用方额度 73 |
| reject | 容量不足拒绝后，重启仍能使用原模型和历史 |
| defaults | 目标默认额度 256，再次换路使用 384，没有固化旧默认值 |

所有进程场景还检查 sibling 会话、模型目录／部署设置和历史事件前缀。参考路径共观察到 33 次本地模型请求；涉及报告的场景真实产出 A=137、B=251、Total=388。

## 实测结果

| 实现 | SDK／操作通过 | 进程通过 | Reward |
|---|---:|---:|---:|
| oracle | 36/36 | 7/7 | 1 |
| early-exit | 0/0 | 0/7 | 0 |
| base | 12/36 | 0/7 | 0 |
| oracle-repeat | 36/36 | 7/7 | 1 |
| forged-report | 0/0 | 0/7 | 0 |
| no-budget | 30/36 | 6/7 | 0 |
| no-revision-check | 35/36 | 7/7 | 0 |
| global-default | 35/36 | 1/7 | 0 |
| no-reasoning-transfer | 30/36 | 6/7 | 0 |
| no-chat-reasoning | 35/36 | 5/7 | 0 |
| volatile-selection | 28/36 | 1/7 | 0 |
| alternative-payload-projection | 36/36 | 7/7 | 1 |
| model-original | 23/36 | 2/7 | 0 |
| old-reference | 25/36 | 2/7 | 0 |
| alternative-repeat | 36/36 | 7/7 | 1 |

Oracle 和语义不同的正确替代实现各通过两次。替代实现通过 SDK `onPayload` 投影 Responses reasoning，验证不绑定参考实现的内部表示。Base 在普通生成→退出→恢复的独立冒烟场景通过；其正式评分为 0，失败不是由于环境无法启动。

提前退出／伪造报告由 root 父进程与 UID 65534 候选进程隔离；报告目录在评分期间为 root 私有。父进程核对固定 case 集合、终态、计数和子进程状态；无法仅凭退出码 0 得分。Harbor 实际完成补丁收集、传输和独立 verifier 执行：Oracle=1、early-exit=0、forged-report=0，三个 trial 都没有框架异常。

新的错误对照说明检查有效：no-chat-reasoning 在 Chat 请求边界失败；volatile-selection 在冷恢复后失败；no-revision-check 的七个进程场景虽可通过，但异步业务边界测试仍将它判 0。因此保留两层检查。

## 静态检查

仓库 `task_ci.py validate` 通过；38 个记录的执行／环境文件哈希、17 个镜像内测试文件及原始归档的 1558 个文件哈希均核对通过。Base 的 `pnpm-lock.yaml` 与依赖清单记录一致。

Skill 附带的通用审计器还要求 `deepseek-harness-` 名称前缀及 Python `requirements.txt`／`output.path` 布局，与本题既有 `dsh-` 名称和 pnpm lock 结构不兼容，因此该脚本未全绿，不将其报告为通过。仅为现有 `feature.patch` 文件名适配过的执行记录见 [机械审计记录](v005-mechanical-audit.json)；这些布局差异不改变实际 Harbor 结果。

## 身份与复现

- Verifier image: `sha256:54ea499b323969650ba28c996a91e075289373c4870aa2137230615cd7cf651f`。
- Agent image: `sha256:e87af67674c9b180ee88328bffd4b4279c1324c0567ac86be943f951287a2b0a`。
- [完整评分记录](e2e-evidence.json)、[执行文件哈希](executable-hashes.json)、[原始证据](v005-offline-evidence.tar.gz)、[skill 与工作区身份](v005-review-context.json)。
- 仓库运行输入与远端冻结副本一致，镜像内 17 个测试文件也逐一核对一致；本轮运行期间未改动这些输入。
- 运行：`harbor run -p tasks/dsh-session-model-migration -a oracle -e docker`。

本轮不重算历史 GPT-6／GPT-5.6 的 pass@4。离线评分验证 DSH 行为，不验证模型推理质量；真实模型实验另见 [先前的 DSH live review](dsh-chat-real-review-20260912.md)。Responses 的 plaintext 扩展只适用于题面声明的兼容网关。

后续已直接重评原始 8 份 patch，未重新调用模型；见 [patch 重评分](v005-eight-patch-regrade.md)。新增 Chat 契约和旧需求缺陷分开统计，历史奖励保持原样。
