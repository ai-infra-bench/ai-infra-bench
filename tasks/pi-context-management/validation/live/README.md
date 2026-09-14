# 真实模型行为测试

这是模型使用扩展的独立测试，不参与 benchmark reward，也不是让模型编写实现的 solver pilot。模型请求发送到真实上游；本地服务只提供实验数据、收集报告和观测事件。

`run.py` 固定两个阶段的任务：比较 A/B/C，每组后记录笔记并切换；重开同一 session，再找回推荐方案的原始审计字段。笔记、搜索词、历史记录选择、工具调用参数均由模型决定。此场景有明确的三次切换要求；不评价自主决定何时切换的策略。

## 执行

在仓库根目录运行，每次使用一个新的输出目录：

```bash
python3 tasks/pi-context-management/validation/live/run.py \
  --repo artifacts/pi-context-hardening-20260914/oracle \
  --output artifacts/pi-context-live-new \
  --models gpt-6-astra gpt-5.6-sol
```

实际调用模型并产生费用。默认每模型一次、high reasoning、每次最多输出 8192 tokens、每阶段 900 秒/60 次请求，两个 worker。网关使用现有 `scripts/model_gateway/launch_router.py`、对应 Python 环境及 `/home/tiger/.env` 中已有凭证；可用 `--gateway-python` 指定其他已配好依赖的环境。凭证不传给 Pi。

## 判定

`result.json` 分别输出：

- 功能：实际请求的上下文保留/移除、原始字段与引用、session/文件保持，以及每组完成记录和切换。
- 历史恢复前提：本场景禁止把原始审计值抄进第一阶段笔记或最终回答；第二阶段的实际模型输入中，每个值都必须先由成功的历史搜索或读取返回。搜索预览带回字段也是合法恢复，不能误判。此限制只属于定向场景，不是扩展功能要求。
- 完成性：每阶段必须有正常的最终助手回复。JSON 模式下退出码 0 不能代替 `stopReason == "stop"`；正确提交报告后又遇到模型错误仍是不完整。
- 效率：成功切换调用数、相对本场景多余的切换、没有新证据的切换、同窗口重复读取/查询、工具错误及上游报告的 token 用量。它们是诊断指标，不直接决定题目得分；也不保证每次重复操作都无效。
- 基础设施：HTTP 429、HTTP 200 后的流内错误、重试和预算停止。`error` 与 `response.failed` 属于同一请求时只计一次。

工具完成事件按 phase + call ID 去重；模型请求重试不会增加成功工具计数。同一记录在切换后再次读取不算“同窗口重复读取”。没有预设最佳切换次数的场景可让 `behavior_metrics(..., expected_resets=None)`，不计算额外次数。

监控仅因声明的请求预算或时限终止进程；不因重复切换自动停止。它始终持有当前阶段的进程句柄，下一阶段只能在监控返回后启动，避免根据旧状态误杀后续阶段。人工干预或检查点恢复必须另外记载，不能算独立新样本。

## 回放与单测

以下命令不调用真实模型、不改写原始轨迹：

```bash
python3 tasks/pi-context-management/validation/live/replay.py \
  artifacts/pi-context-live-v2-20260914/gpt-6-astra \
  artifacts/pi-context-live-v2-20260914/gpt-5.6-sol \
  artifacts/pi-context-live-v2-20260914/gpt-5.6-sol-resumed \
  --output artifacts/pi-context-live-replay.json

python3 -m unittest discover \
  -s tasks/pi-context-management/validation/live -p 'test_*.py' -v
```

回放必须保留原运行状态：GPT-6 额外切换 0；GPT-5.6 额外切换 8，原始第二阶段被人工中断；恢复记录的第一阶段仍复用原轨迹，不重新计算为一次独立模型尝试。

2026-09-15 补齐最终回答和恢复前输入的检查。21 项单测通过；完整判定器回放已有轨迹，并拒绝两种隔离反例。见 [本轮结果](../v2/test-completion-review.md)。`replay.py` 输出观测指标和恢复前提，不重新裁定完整运行状态；完整判定器回放脚本及结果保存在该报告链接的 artifacts 中。
