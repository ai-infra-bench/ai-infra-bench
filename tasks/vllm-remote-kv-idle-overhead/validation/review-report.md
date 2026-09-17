# PR #61：长期资源契约与公平性校准（v1.5.0）

本版在 v1.4.0 的 FCFS、完整生命周期检查之上补齐长期运行资源检查。仍采用 Oracle-based 校准；不是以模型通过率为目标。使用 `ai-infra-bench-rollout-review`（冻结修订 `b40002e149e5d2e0896ca2cc3573a84f1f0b4091`）的合同、差分行为和完整评分流程。以下校准记录保留当时语境；随后完成的三次新模型实验单列于文末，不与历史答案重放混同。此次发布整理不改变运行文件、原始模型输出或分数。

## 先公开资源要求，再评分

原题没有给出缓存容量和回收时限，因此 v1.4.0 的弱引用存活量不能直接扣分。本版在 instruction 最后一段以开发者口吻公开：长期运行、一次一个短请求、prompt 不超过64 tokens，warm-up 后可额外保留32 MiB Python内存；允许有界缓存以及延迟/批量回收，不要求对象立即销毁。没有给出修复文件、数据结构、内部根因或公开复测脚本。

这是**新版本的显式验收合同**，不能把它倒推为旧版模型本来就收到的要求，也不能把新评分当作新的模型通过率。32 MiB是本任务公布的资源预算，不是vLLM通用性能标准。测试检查实际保留内存，不要求所有对象的弱引用为零。

## 新用例的行为边界

同一个真实 Scheduler，max_num_seqs=1；依次正常 add_request → schedule → 确定性模型输出 → update_from_output → 客户端 terminal。local 和 remote 各运行一组，remote 先正常经历异步匹配及接收完成事件。每次同时检查输出token、单次结束通知、unfinished计数和无旧请求复活；只替代模型计算与传输事件生产者。

每组使用不同请求ID、32至64 token的短prompt、变化的单token输出，累计256次warm-up，然后在4096、16384次完成后采样。每次采样前执行16个正常空调度周期并进行GC。`tracemalloc` 在scheduler初始化后开始，比较当前存活Python分配量相对warm-up的增量，预算33554432 bytes；不是峰值分配、RSS或CUDA内存。驱动不保存请求/输出历史；不检查任何候选新增类、字段、容器大小或函数名。

允许延迟回收不代表无限增长也应被接受：实现可以选择自己的清理时机，但在公开预算内维持长期服务。有限16384次负载不能证明所有未来输入均有界；C扩展未计入的分配也不在此Python预算测量范围内。

## 公平性与负控制

- Oracle 和 event-ready-heap alternative：完整功能解法，后一份采用不同内部表示。
- bounded-history-cache：Oracle加最多保留2048份Request的有界缓存，故意不立即释放对象；正控制。
- batched-history-reclamation：Oracle加每3072次接入清空一次的历史列表；正控制。
- completed-history-retention：历史r03完整tracked最终补丁，作为保留内存负控制。模型完整捕获的 `/app` 另行只读重放，patch不冒充完整文件系统。

两份缓存控制是基于Oracle的公平性/变形控制，不能称为两个独立模型解法。保留r02抢占负控制和其他既有功能控制；五项既有评分安全控制本轮未重新运行，不沿用历史成绩声称评分可信度已经验收。

## 版本与执行身份

- 原始模型版本：v1.3.0 / PR head `f3e676b7178b707f2ad139c20229627786249a43`，三次原reward均为1。
- 新本地task：v1.5.0；18 checkpoints为17个检查组加complete，并非18个独立输入。
- Base、Oracle和镜像不变，镜像 `sha256:fd59b9b0cbbc1c4d5400d97e1eaeb1cdd4640f71983c9a5581b84449743ac88c`。
- 实验根目录：`runs/deepseek-pr60-pr61-r2-20260917/verifier-hardening-pr61-v150/`。
- `frozen-inputs.json` 在运行前记录完整task快照；每份候选、每次重放均核对运行前后hash，未使用文档更新后的hash冒充执行身份。
- 最小差分：8个subject、local/remote分别运行；完整候选评分用实际 `tests/test.sh`；Base/Oracle/正负控制另走实际Harbor 0.22.0。
- 直接容器使用私人Docker、network=none、runc、2CPU/8GiB；Harbor沿用 `--cpus ignore --memory ignore`，不声称硬资源限额或独占CPU。完整评分串行运行以降低idle比例检查之间的干扰。

## 已运行的独立资源用例

以下为16384次完成后的增量，MiB按1048576 bytes换算。各subject的两种模式均真正运行，不受前置FCFS或idle检查失败遮挡。

| Subject | Local MiB | Remote MiB | 新资源检查 |
|---|---:|---:|---|
| Base | 0.47 | 0.45 | 两项通过；不代表原缺陷修复 |
| Oracle | 0.47 | 0.45 | 两项通过 |
| event-ready-heap alternative | 2.22 | 2.18 | 两项通过 |
| bounded-history-cache | 8.35 | 8.32 | 两项通过 |
| batched-history-reclamation | 3.86 | 3.86 | 两项通过 |
| r01 | 0.47 | 0.45 | 两项通过 |
| r02 | 0.47 | 73.23 | Remote失败 |
| r03 | 71.30 | 71.26 | 两项失败 |

这些结果支持新测试能区分实际过量保留与有界/批量清理，不意味着所有合理实现已穷举。r02的完整评分可能先被已有FCFS检查拒绝；独立资源用例说明它还有另一项不符合新合同的行为。

r03最终补丁采用逻辑删除：调度时从活动索引中移除请求，但底层deque仍持有Request；其物理清理针对同一对象重新入队，不能回收本测试中已完成且不再复用的不同请求。它在短生命周期测试中能给出正确输出，但这次真实内存测量显示历史引用累积。这个源码机制用于解释诊断，不用于评分；候选仍可保留同样的数据结构，只要通过合理回收满足预算。额外历史扫描可能影响时延，但本轮没有把这点当作已测得的性能缺陷。

## 完整评分与当前限制

三份完整捕获 `/app` 只读挂载后，经实际 `tests/test.sh` 完整评分已完成，运行前后hash均一致。这不是三次新Harbor模型尝试：

| 历史答案 | 原v1.3.0 reward | v1.4.0重放 | v1.5.0重放 | 本版实际终止原因 |
|---|---:|---:|---|---|
| r01 / 7AozjUa | 1 | 1 | 1，18/18 | 完整完成 |
| r02 / NDtMrjy | 1 | 0 | 0，12/18 | 已有FCFS抢占检查失败；完整suite尚未执行到资源检查 |
| r03 / mJQtn65 | 1 | 1 | 0，15/18 | 本地保留内存超过32 MiB；remote另由独立资源用例确认失败 |

当前完整回放结果1/0/0不改写原始1/1/1；r03是被新公开资源合同拒绝，不能表述为原始题目中已有同一个数值约束。

11个实际Harbor控制全部完成，Harbor errors均为0，实际reward全部符合预期，冻结task运行前后hash一致：

| 控制 | Reward / 完成检查点 | 实际原因 |
|---|---|---|
| Base | 0 / 0 of 18 | 原始idle开销比22.76，目标缺陷尚在 |
| Oracle | 1 / 18 of 18 | 全部检查完成 |
| event-ready-heap-alternative | 1 / 18 of 18 | 不同内部表示的完整解通过 |
| bounded-history-cache | 1 / 18 of 18 | 保留2048份请求的有界缓存仍通过 |
| batched-history-reclamation | 1 / 18 of 18 | 每3072次接入批量回收仍通过 |
| dropped-client-output | 0 / 1 of 18 | streaming segment未返回预期客户端输出 |
| all-remote-only-shortcut | 0 / 1 of 18 | mixed idle比9.65，混合等待仍线性增长 |
| incomplete-agent-implementation | 0 / 0 of 18 | idle比12.99，目标缺陷尚在 |
| historical-oracle-starves-stream | 0 / 8 of 18 | 无remote completion时streaming continuation停滞 |
| preemption-backlog-regression | 0 / 12 of 18 | reset后先调度queued-0，违反FCFS |
| completed-history-retention | 0 / 15 of 18 | local保留增量74763075 bytes，超过公开预算 |

负例的0分都核对了实际行为断言，并非把导入失败、环境错误或进程退出码当作校准成功。必需检查数是18；负例触发前置失败后不声称后续检查也执行过。原始日志 `rollout-hardening-v150-logs/` 与机器汇总 `rollout-hardening-v150-results.json` 现统一保存在 [evidence.zip](evidence.zip)，包含冻结输入、完整回放和独立资源观察；更早记录在 [history/curation-history.zip](history/curation-history.zip)。

本轮只是scheduler子系统端到端校准，不含HTTP、真实NIXL/RDMA或模型精度。没有重新完整人工阅读全部历史轨迹，也没有开展新评分攻击探针；评分可信度审查仍未完成。题面发生资源合同变化，若用于新的模型能力比较，需要另行获授权后在冻结版本上产生新答案，不能将此开发回放当作held-out结果。

## 随后完成的三次新 DeepSeek 实验（r3）

2026-09-17 的 `deepseek-pr60-pr61-r3-20260917` 使用冻结 v1.5.0 题目，三次独立生成答案均完成完整 Harbor 评分。这不是上文的旧答案重放。

| Trial | Reward | 必需检查 | Harbor 异常 |
|---|---:|---:|---|
| pr61-deepseek-h1-r01__i9MEADK | 1 | 18/18 | 无 |
| pr61-deepseek-h1-r02__HB3KWFK | 1 | 18/18 | 无 |
| pr61-deepseek-h1-r03__j2vPuG5 | 1 | 18/18 | 无 |

请求模型为 `openai/deepseek-v4-flash`；服务端别名不提供不可变权重版本。逐份审核最终补丁、可见工具行为和评分原因，三份答案均修改生产 scheduler/request_queue 并进行了测试迭代。额外普通行为挑战对每份答案运行六个 seed × FCFS/priority，与 Base 的输出/调度轨迹一致；priority 只是诊断，不是额外隐藏合同。已审核范围没有发现新的明确功能缺陷或评分误判。

这不是“证明不存在作弊”：部分工具输出有原生截断，未逐字阅读全部推理，也没有完整审计所有容器外状态。评分信任审核仍未完成，reward 1 不等于对任意输入的正确性证明。新实验摘要、原始 reward/stdout 和逐份审核文档在 `evidence.zip` 的 `fresh-agent/r01` 至 `r03`；完整轨迹保留在上述 workspace campaign。原报告内的相对路径保留原实验语境，非当前 task 目录的文件链接。
