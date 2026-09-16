# 环境与产物采集复核（2026-09-17）

当前版本 1.2.1；这是对 [前轮语义审查](instruction-e2e-review-2026-09-16.md) 的环境修订补充，不把旧模型成绩迁移到本版本。题面、Oracle 和 Python/C 评分逻辑不变；新一轮 DeepSeek 的完整轨迹审查尚未完成。

## 问题与修复

- 两个 task 的正常上游 pytest 都缺少 tblib。本版在构建期安装固定版本 pytest/tblib；PR61 另缓存普通上游测试所需 OPT 配置/tokenizer 的不可变 revision，不提供任务专属公开复现脚本。
- 旧 donor 的另一个 vLLM Python 目录可被 Agent 读取；PR60 目录包含较新的 DCP 实现。已移除 donor Python、源码示例和相关缓存，原 site-packages 路径改为指向候选 Base 的 symlink，并使用 scratch 最终阶段排除历史 donor 层。发现暴露风险不等于证明旧 Agent 曾读取它；旧环境结果不得用于证明本版的隔离性。
- PR60 运行镜像中的 curator lock 含目标文件列表，已在构建验证后删除。所有 task provenance 仍在评测方文件中保留。
- Harbor artifacts 改为整个候选工作目录，已在实际评分入口确认保存 .git、上游 tests 和候选源文件，便于审查最终交付，而非仅分析聊天文字。

## 已执行验证

最终镜像 ID 与执行文件 hash 见 [新镜像校准记录](isolated-image-calibration-2026-09-17.json)。10 个 Base、Oracle、正确替代实现、不完整实现及评分绕过反例全部得到预期分数。Oracle 完成全部 11 个必需检查；两类提前退出和伪造成功反例未获分。Base 的失败来自目标行为，不是导入依赖错误。

全新离线 agent 容器执行了 8 项相关上游测试，全部通过。源码隔离检查确认精确 Base、仅可达历史、无 remote/tag/unreachable object，以及 donor 路径不再提供第二份源码。官方 review skill 的严格 artifact 审计通过；日志保存在独立实验目录，不将机械审计等同于语义正确性证明。

## 新实验与结论限制

采用 Harbor 0.22.0 / Terminus-2、openai/deepseek-v4-flash、max_turns=1000；服务商没有公开不可变模型 revision。计划每题十次，先各三次独立尝试，完整审查六次轨迹和最终代码后才扩展。各次参数与文件 hash 在运行前记录。基础设施故障与模型能力失败分别归因；正确率高低不决定任务是否合格。

PR60 本机用 H20；A100、真实多 rank/模型权重/服务端性能不在已验证范围。PR61 是 CPU scheduler 子系统，不宣称真实 NIXL/RDMA 或 HTTP E2E。共享 GPU 上的结果不作为独占硬件性能结论。旧版模型轨迹仍是历史研究材料，不能与新镜像的新样本合并统计。

