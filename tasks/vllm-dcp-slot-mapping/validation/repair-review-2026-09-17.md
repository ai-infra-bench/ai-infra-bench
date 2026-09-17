# PR60 支持范围与 fixture 修订：v1.5.0

选题保留；修正已确认的配置可达性问题，**不是最终验收通过声明**。已评分 7/10，小计 14/14；第 3、9、10 维未完整验证，整体分数待定。具体执行结果及范围以 `repair-calibration-2026-09-17.json` 为准。

| # | 维度 | 状态 | 证据或缺口 | 下一步 |
|---|---|---|---|---|
| 1 | 场景真实清楚 | 2 | 保留 V2 迁移、DCP、正常 batch 和 graph 的原题面 | 不泄露内部修法 |
| 2 | 正确性独立于 PR | 2 | 不要求特定 helper、缓冲区或修复位置 | 按消费到的行为评分 |
| 3 | 环境可解性 | U | 固定 Base 镜像；H20 真实 CUDA 已跑，声明的 A100 未复验 | 保留硬件范围限制 |
| 4 | 题面与测试双向对齐 | 2 | 删除不可达 hybrid layout，两个 block size 各走真实配置生成 | 见布局与映射说明 |
| 5 | 行为决定路径真实 | 2 | 配置→runner→实际 slot kernels/graph→sampler tokens | 不扩称多 rank serving |
| 6 | 不同正确实现可通过 | 2 | 三个既有替代实现走相同评分入口；不要求紧凑表宽 | 见正对照结果 |
| 7 | 错误实现因目标行为失败 | 2 | Base 和不完整控制到达 DCP 后输出 slot 错误 | 与环境失败分开 |
| 8 | Oracle 独立挑战 | 2 | 新合法 size32、边界63→64 与 near-max context 验证 | 保留独立公式/消费者 |
| 9 | 评分可信度 | U | 评分包装未改；旧提前退出控制不作为本次重跑，评分依赖可变性线索未验证 | 另行完成可信边界审核 |
| 10 | 验收与交接 | U | 功能控制、新哈希和日志记录；fresh DeepSeek/GPT 未启动 | 最终门禁保持未批准 |

## 身份与范围

- Base `be3af2d29e2507f32b2190fe015cd6609b348caa`，cutoff `2026-02-17T23:18:18Z`，task v1.5.0。
- 环境输入未变，复用镜像 `sha256:dee094a5fca85bb9d08b507d3d23b12b51d89c31b268bc9431800efed3c961d3`，没有无意义重建或虚构新 digest。
- 使用 task-review skill 冻结修订 `b40002e149e5d2e0896ca2cc3573a84f1f0b4091`。本轮针对已诊断问题修订，不声称完整重新完成所有安全与硬件审核。
- 实测共享 H20 的物理 device 4，Agent 和独立 verifier 的分配均有运行观察记录；没有抢占其他进程，不是独占性能测量。

## 配置缺陷与修复

旧测试手造两个 FullAttentionSpec group（size16/32，相同 heads/head size），page bytes 不同；Base `get_kv_cache_config_from_groups` 拒绝。默认 prefix caching 下多 group 进入 Hybrid coordinator，DCP>1 也不支持。题面只要求 supported layouts，因此不能要求 Agent 新增 hybrid-DCP 特性来迎合测试。

新版分别运行 block size16 和32。每个场景用真实 `get_kv_cache_groups`、`get_kv_cache_config_from_groups` 将两个 full-attention layer 归为一个合法 group，并交给真实 KVCacheManager 检查该布局。不同层消费同组 metadata 是正常布局，不再要求不同 group 的 slot 值不同。

表的请求块数量由 max_model_len=128、block size 与 DCP size 独立计算，不读取候选 table width 来决定需求；紧凑分配与安全过分配都能接受。slot 检查包含位置54–63及122–127，四种 size/rank/interleave 组合各运行两个 block size。graph 重放更新位置、请求顺序、query 分段和物理 block ID。

生命周期每次构造总 prefill64：长请求长度为逻辑块边界减一（size32/DCP2 时63），随后 decode 穿过边界，并与短请求结束、新请求加入、slot 复用交织。consumer 对同组两层 slot 使用合计17的权重，避免合计16与 vocab256 在 block size16/32 下抵消物理 block ID 变化。精确 slot 数组检查仍保留，不只依赖这个 token 指纹。

## 行为与检查映射

| 合同 | 输入→真实路径→观察 | 覆盖 |
|---|---|---|
| 支持普通 DCP 布局 | 两种合法配置→runner 初始化与 KV manager | 每个场景 |
| rank/interleave 下结果正确 | block IDs/positions→真实 slot kernel→精确数组 | 4组合×2 sizes |
| CUDA Graph 数据随请求变化 | 捕获后更改输入/blocks→真实 replay→精确数组 | 两种 sizes |
| batch 变化和跨块生成 | 8次合法 runner 消息→prepare/forward context/sample→按 request ID 的 tokens | DCP eager、DCP graph 各2sizes |
| 非 DCP 不回归 | size1/rank0 的 slot 与 graph 生命周期 | 两种 sizes |

语义边界：合法配置及 scheduler 消息 → 真实 V2 runner 输入准备、DCP slots/local lengths、CUDA graph 更新 → 请求输出。模型算术、attention consumer、KV tensor分配与通信group metadata 为替代边界；并未运行真实多 GPU collective、HTTP或完整模型精度。题面完全未变，也没有给 Agent 添加公开复现脚本。

## 验证与未完成项

本次最终版运行 Base、Oracle、三个不同正对照和一个不完整负对照，共6个真实 Harbor 控制。原先的五个评分攻击/退出控制未在本修订重跑，manifest 明确标为 pending，不沿用旧通过当新证据。评分可信度线索未复现，对应受阻探针没有换工具重试，不能写成已复现漏洞或已排除。

先前 h1 DeepSeek 三次原始 reward 为 `[1,1,1]`，其中一次触及1000 episodes；这些属于旧v1.4.1，不能当作v1.5.0新模型实验。此次仍未启动新的DeepSeek或GPT。旧 `instruction-e2e-*`、`isolated-image-calibration-*` 等文档保留历史意义；当前入口是本报告与 repair calibration。

Harbor task checksum 是写入最终证据之前的输入身份，发布时只更新证据/说明。完整原始产物保留于 curator campaign `deepseek-ten-per-task-20260916/next-iteration/controls/pr60-final-*`；精简评分日志、结果和执行文件哈希随任务提交。
