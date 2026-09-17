# PR60：HND 覆盖与 Oracle 修订（v1.8.2）

选题保留。上一轮轨迹审查确认：v1.8.1 的默认布局测试遗漏了 FlashInfer HND 的真实生成错误，旧 Oracle 得1但并未满足全部公开合同。v1.8.2 补充显式布局矩阵并修复 Oracle。本次是授权的 verifier/Oracle 修订与已保存答案重放，不是新模型评测，也不重写任何历史 reward。最终校准结果见本文及 `e2e-evidence.json`；独立的评分信任与 A100 认证仍未完成。

## 范围、依据与产物

- 使用 `ai-infra-bench-rollout-review`，对上一轮已确认问题重开相关功能门禁，不冒充全量初始安全审查。
- 采用 Oracle-based 校准：修订 Oracle、语义不同的完整 GPT 答案、Base 及相关错误控制。
- 公开题面已经要求支持的 paged-KV 布局、FlashAttention/FlashInfer、eager/graph。无需加入修法提示或修改题面来支持本次测试。
- 原始 GPT-5.6 Sol/high trial 为 `pr60-gpt56-sol-high-fairness-r01/task__GETsdtK`，v1.8.1 原始 reward=1、19/19。完整仓库含四个 tracked 实现文件及两个 untracked 测试；本次重放逐文件和 tracked diff 核对，不只摘取部分实现。
- 原始轨迹、旧 Oracle、历史证据和旧分数保留。旧版三个正控制归档到 `history/v181-positive-controls/`，不再当作未经新布局矩阵验证的当前正控制。
- 本次没有重新读取并认证所有历史轨迹，也没有新增模型调用；不把开发期差分测试当作独立 held-out 能力评测。

## 已确认 P1：旧 Oracle 的 HND 错误被默认布局测试漏掉

合法输入为相同离线 Qwen3、TP2/DCP2、FlashInfer、`VLLM_KV_CACHE_LAYOUT=HND`，分别 eager 和 graph。通过正常引擎接入三请求，发生错峰完成、新请求接入和跨 cache-block 生成；独立 CPU Transformers 对相同前缀计算全部256维 logprob。

上一轮独立诊断中，旧 Oracle 在两种模式下首个分布均有247/256个元素超出允许误差，最大绝对误差约1.62355（阈值0.02）；保存的 GPT 答案两种模式均通过，最大误差约0.00213。这是输出数值错误，不是启动失败或只检查内部变量得到的结论。

根因是旧 Oracle 把 paged cache 的 HND 布局也用于未缓存的新 K/V。后者仍为 token-major NHD。修订 Oracle 仅分开这两种输入的布局；verifier 不检查这个实现手法，也不要求特定字段、辅助函数或修复位置。

## 新增行为测试及边界

正常 `LLMEngine` 接入请求 → 两个真实 TP2/DCP2 worker 的模型、KV 写入、attention、collectives、graph replay → 请求 token、logprob、终止与排空。

| 维度 | 覆盖与判定 |
|---|---|
| 后端 × 布局 × 执行方式 | FA/FI × NHD/HND × eager/graph，共8个完整引擎组合，每组新进程显式设置布局 |
| 请求生命周期 | 每组3个请求、19个生成 token；短请求结束后新请求加入，另一个请求继续 decode |
| 独立正确性参考 | 相同不可变随机权重，CPU FP32 Transformers 对 GPU FP16 全词表 logprob；atol0.02、rtol0，并检查 greedy 容差、数量、完成和排空 |
| 真实执行 | 不 mock rank/group、不预填 KV、不替代真实 attention 或通信 |
| 检查完整性 | 新增两个后端 HND 完成检查点，必需检查点19→21；NHD不依赖环境默认值 |
| 既有回归 | slot、rank/interleave、block16/32、graph更新、非DCP FA/FI/Eagle及60步FI行为覆盖保留 |

旧 v1.8.1 的内部表示公平性修复保持不变：模拟消费者仅检查请求/token/position/slot，不强制 runner 预填可选本地长度。真实 backend 和完整引擎仍验证长度语义；允许在后端完成该计算。CPU参考是独立数值实现，不把 Oracle 输出作为唯一正确答案。

## 最终完整 Harbor 校准

当前冻结版本在同一最终镜像上通过实际 Harbor 入口运行。七项均符合预期、无 Harbor errored trial，运行前后全部 prepared 输入哈希一致；执行时间为2026-09-17 17:16:21—17:37:26 UTC。以下均为本版实测，不沿用旧成绩。

| 控制 | Reward | 完成检查点 | 实际因果结果 |
|---|---|---|---|
| 修订 Oracle | 1 | 21/21 | 八种完整引擎组合均通过独立 CPU 参考 |
| 原样保存 GPT 答案 | 1 | 21/21 | 八种组合全通过，允许不同修复位置 |
| Base | 0 | 2/21 | 真实 DCP slot 地址错误 |
| 旧 HND Oracle | 0 | 19/21 | FI HND eager 全词表247/256维超差，最大误差1.62355184555 |
| 旧 FA graph 缺陷 | 0 | 11/21 | 真实 attention 输出0，预期0.61328125 |
| 非 DCP Eagle 回归 | 0 | 13/21 | 草稿得到[[1,0],[1,0]]，预期[[1,6],[1,9]] |
| 无 FI 修复 | 0 | 14/21 | CUDA数值1024/1024维超差，最大误差0.029296875，阈值0.001 |

两份正控制各自的八条 `DISTRIBUTED_CHECK` 记录覆盖完整笛卡尔积，无遗漏/重复，最大 logprob 误差均为0.0024595260620117188，小于0.02。旧 HND Oracle 在同一完整评分中通过所有 NHD 及 FA HND 组后，因 FI HND 的真实数值错误得到0，而非由于环境、依赖或启动失败。

旧 Oracle 的历史1分不被覆盖；新版0分是缺失行为覆盖被补齐后的重评分。保存 GPT 的原始1分、19/19与本轮1分、21/21分别保留，后者不是额外一次模型成功。

## 版本绑定与复验

- 执行目录：`runs/pr60-hnd-hardening-20260918/controls/`。`frozen-hashes.json` 在执行前产生；每个 `*-inputs.json` 记录 prepared task 全文件哈希、命令、镜像和 GPU 绑定，执行后核对不变。
- Harbor 0.22.0；同一最终镜像 `sha256:462fc769cac14468d0c1a7128eb17116c728e12e31efaee14b9ea7fd6c3e9868`；Base `be3af2d29e2507f32b2190fe015cd6609b348caa`。
- instruction、环境文件和镜像相对 v1.8.1 不变。改变的是测试、Oracle、版本及验证材料；没有新增公开复测脚本。
- 本地工作树起点 `2aa19ca6c7a7b67124acc70043a4ac8cdc0a987f`，分支 `review/pr-60`。本轮不 commit/push，校准绑定文件快照而不是尚不存在的新提交。
- 当前 `evidence.zip` 保存本轮完整评分记录、HND诊断及历史v1.8.1证据；不会把旧通过记录改成新版本通过。

## 仍然保留的限制

本轮只确认受影响的功能修订及七项控制。H20 ×2 不能代替 A100 认证；已有 native donor/cutoff 差异未在本轮消除。完整评分信任审查仍开放，此前受限的安全探针没有重新执行或认证。完整引擎覆盖不等同 HTTP、生产模型质量、所有配置或吞吐测试。FlashAttention graph 使用题面已公开的 single-split 配置以避开独立的基础镜像启动兼容问题，实际 graph 与 collectives 未禁用。

因此可以报告具体缺陷已修及对应功能校准状态，但不能据此声称没有任何未来缺陷、绝对防篡改或已获得无条件合入认证。

## 后续发布授权（2026-09-18）

上述“不 commit/push”描述的是校准阶段。校准完成后，用户明确要求将本地修订推送到现有 PR #60。本次发布包含已校准的 v1.8.2 task 和证据，不改动冻结的题面、环境、测试、Oracle 或原始评分。执行身份仍以预运行快照为准；发布提交由本文件所在 Git 历史标识，不以事后提交哈希冒充预运行身份。PR61 与其他任务不在本次发布范围。
