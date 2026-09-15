# 轻接口题面 review

本轮只修改题面与版本状态。v0.0.2 原题面和构建记录保存在同目录的 `instruction-before-light-interface.md`、`construction-before-light-interface.json`。当前题面为 v0.0.3，尚不能沿用旧评分器验收。

用户目标：同一批并行子 agent 在工作期间共享发现，使接收方下一步能使用新信息。保留现有 subagent 入口、独立子进程、自动进入模型上下文、明确的下一轮送达边界、完成前处理、顺序与不重复、团队隔离、取消清理和默认兼容。

实际参考：`vllm-implement-anthropic-rust-serving/instruction.md` 用既有 SDK 界定兼容；`vllm-persistent-kv-layout-namespace/instruction.md` 与 `vllm-kv-admission-thrashing/instruction.md` 用场景和结果约束实现。本题没有现成通信协议，因此显式要求解题者设计并记录接口，而不把评分脚本采用的接口当成产品必要条件。没有新增 SDK 或暗中引用 Codex 行为。

| 修改 | 语义与测试影响 |
| --- | --- |
| 删除固定 communication 参数、每项必填 id，以及启动前校验这些 id 的具体方式 | 解题者可设计开关和分配身份；每个实例仍须独立寻址。ROOT 的固定参数注入和 duplicate_ids case 不能原样用于新题。 |
| 删除 team_members/team_send 固定名称、参数、返回 JSON 及状态枚举 | 保留队友发现、私信、广播、真实发送者和逐个失败反馈。测试固定工具调用及字段读取必须适配，不能按旧名称拒绝合法实现。 |
| 删除 16 KiB 硬下限 | 保留 Unicode、完整送达和超限明确拒绝。现有 unicode_long 不能再因拒绝 16 KiB 而扣分；需要根据公开能力重新设计有效输入。 |
| 保留仅向正在运行的队友发送及无效请求显式失败 | pending/finished/self/unknown 的行为方向保留；具体参数及错误返回格式不固定。 |
| 合并生命周期与隔离叙述 | 下一模型调用送达、完成边界、顺序、不重复、私信隔离和取消仍是要求。现有受控时序和模型输入观测思路可以复用，不能跳过真实执行。 |

这次放宽了公开接口和大小要求，是契约修改，不是纯措辞压缩。参考解可以作为一种实现继续研究，但未重新验收。旧模型成绩（GPT-6 18/18、GPT-5.6 17/18）仅适用于旧题面/评分版本。

下一步先共同 review 新题面，再设计允许接口差异的测试接入方式。未修改测试来伪造通过，未启动模型评测，未提交或推送本轮文件。
