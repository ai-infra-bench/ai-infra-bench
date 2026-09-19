# PR #63 flash rollout review（完成，v1.3.2）

最终 v1.3.2 的评分与完整交付物重放、独立行为检查一致，可以保留该 task。发现并修复两处 verifier 问题：CPU-mask OOV 的隐藏范围扩展，以及空外层 embeddings 计数漏检。未发现仍需修改的评分问题；这是一项在已披露边界内的接受结论。

A100 上完成 3 批有效 flash 测试，每批并行 4 个，共 12 个模型答案；另保留 1 批 4 个网关配置失败。逐条 review 后各批原始奖励为 r02 `[0,0,0,0]`、r03 `[1,0,1,1]`、r04 `[0,1,0,0]`。以最终 32 项 verifier 重放分别为 `[1,1,0,1]`、`[0,0,0,1]`、`[0,1,0,0]`。旧结果原样保留。

当前 Oracle 和独立 index-copy 实现均 32/32，Base 和伪造成功退出均为 0。测试有效性、候选正确性和 task 可解性分别有对照证据；不要求四个模型答案全部通过才结束迭代。

## 范围与证据

验证模式：Oracle-based。使用 `ai-infra-bench-rollout-review` skill；文件哈希见 `rollout-evidence.zip` 内 `review/pr-63-rollout-skill-hashes.json`。初审及 v1.3.0 的 GPU、反作弊和 Harbor 集成证据是本轮前提；本轮重新打开了 OOV 用例的契约边界。

A100 上使用 Harbor 0.22.0、Claude Code 2.1.238 和 `/data/akg_kernel_bench_lite/kernelgen/env.sh` 配置的 `deepseek-v4-flash[1m]`。网关原始响应中的模型标签是 `deepseek-flash`，没有可验证的不可变模型修订号；reasoning effort 未覆盖。原始 usage/cost 仅作为网关/Harbor 记录保存，不当作已核实账单。

每批 4 个独立 Harbor trial，同时分别绑定 GPU 0–3；每个 4 CPU、16 GiB 内存、1 GiB shm、1 张 A100 40 GB。`--override-gpus 0` 避免 Harbor 重复注入 GPU，实际 Compose `device_ids` 和运行中设备绑定已核实。只有 agent 阶段允许模型网关主机，verifier 无网络。CLI 可执行文件离线安装，没有复制用户配置和历史 session。凭据只从指定文件导入进程环境，不在任务、参数或报告中；导出文本按真实密钥值扫描，本轮导出 redaction count 为 0。

Base：`36d7f19897843c9cbdb701ba88d0f2c29954fe44`。镜像：`ai-infra-bench/vllm-multimodal-merge-memory:hardening-1.3.0`，实际 image ID `sha256:9b8b0bfbce07832a29b5831c05726ca795f00eface39d678b9a9aea20646d51b`。verifier 更新不改变镜像；镜像尚未发布为 registry digest。

捕获器在 agent 最后写入之后、verifier 运行之前保存 tracked patch、全部未跟踪文件、Git 状态/历史、完整仓库 tar（含 .git、忽略文件和本地二进制）及 SHA-256 清单。实际 Harbor smoke 用 Oracle 和额外未跟踪哨兵证明捕获时序与恢复有效，奖励 1，26/26。第一版 smoke 因 OracleAgent 构造参数错误未启动 trial，已修正，未产生模型调用。

每个 campaign 在运行前保存 canonical task 和各 GPU 准备副本的哈希，运行后检查不变。重放同样冻结 tests、脚本及完整 archive 的哈希并在结束后核对。完整快照保留在 A100 `/data/codex-pr63-rollouts-20260918`；本地下载了轨迹、日志、patch、未跟踪归档和清单，不下载每个约 1.4 GB 的完整仓库包。重放使用整个保存状态，未缩减为 production patch。

## 已确认的问题

### F1：CPU mask + OOV 前置处理是未披露的范围扩展

题面要求解决 Qwen3-VL embedding merge 的显存压力，增加 CPU mask + CUDA embedding 的合并支持，并保留正常 CUDA mask 行为。Base 的 Qwen3-VL 未配置 OOV multimodal token 分支；两个 runner 将 mask 复制到 GPU。通用 `SupportsMultiModal` 的 OOV 前置处理采用 device-local `masked_fill`，它是另一项输入准备行为。

v1.3.0 将 CPU mask 支持隐式扩展到了 OOV token 文本 embedding 准备，并把这项隐藏要求作为最后一个零分断言。三个交付物已通过前 25 个检查，最终仅在未修改的 `interfaces.py` OOV `masked_fill` 处出现 CPU/CUDA 设备不匹配。它们的合并修复分别采用布尔索引、非阻塞 index_copy、pinned 非阻塞 index_copy；缺少相同额外修改不能作为三者都错误的证据。

v1.3.1 保留 CPU mask 的 in-vocabulary 集成用例，将 OOV 集成用例改为其正常 CUDA mask 路径，并通过既有 `configure_mm_token_handling` 初始化真实状态。仍使用实际 embedding lookup 和真实接口，不比较 Oracle 的算法。此修正没有删除 OOV 回归保护，也没有放宽同步、显存、顺序、计数或原地修改要求。

完整状态重放验证了实际 reward 影响：r02 GPU 0/1/3 从历史 0 重评为 1（26/26），GPU 2 保持 0。所有旧版重放均复现原始分数。

### F2：一个模型实现的索引拷贝确实同步

r02 GPU 2 用 CPU `nonzero` 计算索引，然后 `indices.to(inputs_embeds.device)` 未设置非阻塞拷贝。首个合法 CPU-mask merge 在同步 debug 检查中失败；其自建 11 个测试检查值、dtype、计数和设备，却没有检测主机等待。因此这是题面明确要求下的 agent 缺陷，修正 OOV 用例后仍为 0，不能把该尝试算作 false negative。

### F3：不把受初始化干扰的延迟测量变成评分

r02 GPU 0 的探索轨迹包含看似证明 CPU 布尔索引等待 GPU 的测量；但实验混入首次分配和初始化。独立实验预先分配并预热，再排入 CUDA sleep 和 event。CPU 布尔索引、非阻塞 index_copy、pinned 非阻塞 index_copy 都在 event 完成前返回；阻塞 `.to` 则等待约 0.46 秒，event 已完成。未据有干扰的轨迹测量新增扣分。现有同步保护仍保留，且明确不宣称覆盖所有自定义 native 同步。

## 第一批有效轨迹复核

所有 agent 消息、工具输入/结果和最终交付物均逐项复核；重复源码输出以确切内容/行引用复用阅读，原始 ATIF 和 native 日志保留。r02 GPU 0 的最终自然语言答复在 native 记录中本身即以半个单词结束，provider 标记 `end_turn`；并非导出器截断。最终代码和测试已完整捕获，原始回复限制如实保留。

- GPU 0：读实际 runner 和旧 Git 历史；比较显存与同步行为，最后用布尔索引并显式计数；最终新增测试 18 个通过，另有原有 4 个通过。尝试外部获取被阻止；读取镜像中安装的 vLLM 0.19.0 副本仍是原有 masked_scatter，没有得到修复答案。
- GPU 1：改用非阻塞 index_copy；一次错误覆盖整个 utils 后恢复并正确局部修改。修正自测 fixture 的计数和预期值错误。最终仅修改 utils，25/26 后死于越界范围的 OOV 用例。
- GPU 2：用 index_copy，但保留阻塞索引传输。修正自测中的 cuda 与 cuda:0 比较、行号和错误形状 fixture；最终 11 个自建测试通过，不代表同步契约满足。pip 安装 ruff 失败。
- GPU 3：从 CPU 整数索引改成 pinned 异步 index_copy，优化单元素 flatten，并为 empty/None 添加处理。修正自测的输入数量和 sync-debug 恢复错误，16 个新增测试加 11 个现有测试通过；真实 in-vocabulary 接口自测通过。uvx ruff 获取失败。

四条有效轨迹未观察到修改评分文件、跳过 verifier、伪造完成信号或成功获得上游答案。正常添加测试和读取 Base 之前的 Git 历史不算 hack。此结论是“已审查材料中未观察到”，不是对任意 native 内存攻击的证明。

最终完整文件清单与新启动的 Base 镜像对照：GPU 0/1/2/3 分别 4954/4946/4954/5063 个非 .git 文件。非缓存差异只有 utils.py 和 GPU 0/2/3 各自新增的测试文件；没有新增或改动 native .so/.a/.o。未跟踪测试内容与轨迹最后一次 Write/Edit 精确一致。额外变化为 Python 字节码与 pytest 缓存；完整保留并重放。

## 行为对照

| r02 交付物 | 原奖励/旧版重放 | 旧检查完成 | v1.3.1 完整重评 | 非连续目标 + 有效 0/1/7 行独立检查 |
|---|---:|---:|---:|---:|
| GPU 0 | 0 / 0 | 25/26 | 1，26/26 | CPU/CUDA 共 6/6 |
| GPU 1 | 0 / 0 | 25/26 | 1，26/26 | CPU/CUDA 共 6/6 |
| GPU 2 | 0 / 0 | 0/26 | 0，0/26 | CPU/CUDA 共 6/6（不覆盖同步） |
| GPU 3 | 0 / 0 | 25/26 | 1，26/26 | CPU/CUDA 共 6/6 |

v1.3.1 模式控制：Base 0；Oracle 1（26/26）；独立 index_copy 替代实现 1（26/26）；伪造 stdout 后直接退出 0（0/26）。未变的 checkpoint 防护控制沿用可归属的 v1.3.0 证据。

首个发起的模型批次 r01 共 4 个均因网关没有列入 Harbor agent egress 允许主机而发生 UnknownApiError，每个 10 次 API 重试，无模型响应、无工具调用、空最终改动。原始奖励均为 0，但归因是基础设施，不计作 4 次能力失败。修复仅对 agent 阶段开放指定网关后，r02 正常执行。

逐次 trial ID、task checksum、Agent Step、工具调用、最终文件与增删行数、total/agent/verifier 时长、生命周期完成信号以及原始 usage 见 [rollout-attempts.json](rollout-attempts.json)。Agent Step 计 ATIF 的 `source=agent`，工具数计显式 tool calls；r01 的单个 agent step 是 harness 合成错误消息，不是实际模型回复。

## 当前边界

没有运行完整 Qwen 权重、图像解码或 HTTP 服务，本轮验证真实 merge、真实接口准备、PyTorch CUDA 算子和 allocator。4× 显存阈值是回归上界，不是最优算法或吞吐保证。评分完整性防护覆盖既有 Python-level 退出/伪造控制，不声称抵御任意 native 内存篡改。修正来自本轮开发数据，不能当作独立 held-out 模型能力测量。


## 第二批有效轨迹 r03 与 F4

v1.3.1 的 r03 原始奖励按 GPU0–3 是 1、0、1、1，全部正常完成。四条轨迹的全部消息、工具输入/输出及最终修改已复核。GPU0/2 保留空容器提前返回；GPU1 做了完整空计数校验，却使用阻塞 `.to`；GPU3 用布尔索引和完整计数校验。

独立完整快照复现发现 F4：GPU0/2 面对空 list、tuple、零行 Tensor 与非零占位符的六种组合均未报错。旧 verifier 的 `(0,3)` 用例实际传入 `[empty_tensor]`，没有进入同一空外层容器分支，导致两个 false positive。v1.3.2 增加六个原有计数契约的回归用例，总数从26增至32；题面及输入语义未扩大。GPU1/3 在独立挑战中均正确报错；GPU1 的三次 GPU event 探针均发现等待，而另外三个无等待。所有尝试均通过连续改变 mask、数量和值的非连续目标独立语义检查8/8。

GPU0新增17个测试，已有11个通过；自测曾误把3对3当作不匹配，修正fixture后通过。GPU1追加109行到既有test_utils.py，自测23通过但只拦截item()，漏掉阻塞拷贝。GPU2自测显式定位并修正非阻塞拷贝，新增22+原有15通过；修正了嵌套fixture设备错误。GPU3新增21个、原有11+4通过，另做200随机等价检查；其测试显存峰值多减一次input bytes，不能采信为独立内存证据。14个模型映射测试下载失败保留在原轨迹中，没有改评分测试跳过它们。

r03各条轨迹中未观察到评分文件篡改、奖励伪造或成功取得外部答案。GPU0/2/3尝试WebFetch/WebSearch/gh，均被阻止、返回空内容或工具不存在。GPU3自然语言把下载失败称为pre-existing，但未做Base对照，此处仅记录观察到的下载失败。

全部未跟踪测试已从review过的Write/Edit顺序重建，与最终归档逐字节核对；GPU1无未跟踪文件。最终完整仓库清单和新版复评分数另附机器证据。v1.3.2对照结果：Base0、Oracle1（32/32）、独立替代实现1（32/32）、伪造stdout后退出0。

## 最后一批有效轨迹 r04

四条轨迹全部动作与结果、最终 production patch、新增测试均已核对，未观察到 hack。GPU1 再次读取安装的 vLLM 副本，仍为 masked_scatter，没有暴露答案；外部 WebFetch/搜索/包下载未成功得到修复。所有 4 个 Harbor trial 无框架异常，canonical task 和准备副本前后哈希均一致。

- GPU0：显式计数、pinned 非阻塞整数索引赋值，保留空外层直接返回。自测 15 项和现有 utils 4 项通过，但未测空外层配非零占位符。正式 26/32 后失败；独立六种空外层输入全部被错误接受。实际 GPU event 检查没有等待。
- GPU1：显式处理空外层数量，pinned 非阻塞 index_copy；最终仅修改 utils。直接实验覆盖设备、dtype、嵌套、计数、空输入和 view。两次基准实验参数顺序错误后修正。正式与重放均 32/32，独立语义和空计数全部正确，GPU 工作未完成时返回。CPU 大向量自测受 128 个 CPU 线程与容器 quota 影响，不据此承诺吞吐。
- GPU2：先采用阻塞 .to，经 sync-debug 实验改为 non_blocking=True，但漏掉空外层计数。新增 19 测试、既有 omni 11 测试通过。正式 26/32，独立空计数六项全错；该固定环境的 pending-event 三次均未观察到等待，不把未 pin 本身当作评分禁令。其“masked_scatter 会重复不足的源”解释不准确，不作为实现正确证据。
- GPU3：CPU 整数索引直接作用于 CUDA 目标，隐式 staging 导致同步；同时保留空外层直接返回。自测只拦截 item/cpu/tolist，不能捕获此等待。21 个新增 GPU 测试、11 个 omni、96 个 mrope 通过；CPU-only 实际为 11 passed/1 skipped，与最终答复笼统写 21 不同。正式首项即失败，独立三次均等待约 0.457 秒且 event 已完成，六项空计数也全错。

四份完整快照的非 .git 文件数为 4956、4946、4993、4998；忽略文件也逐项比对。除 Python/pytest 缓存外，差异只有 utils.py，以及 GPU0/2/3 各一个新增测试；native 资产无变动。新增测试从 Write/Edit 顺序重建，与最终 untracked 归档逐字节一致。完整状态重放的结果仍为 0、1、0、0；不是仅套用修复 patch 的替代重放。

## 所有尝试与重评

下表行数为最终 tracked diff 的新增/删除行加完整 untracked 文本行数，不是累计编辑量；均无新增二进制交付。工具次数按 ATIF 显式 tool_calls 计，不把 shell 内命令数当模型轮数。UUID、task checksum、模型/框架版本及逐文件哈希见 [rollout-attempts.json](rollout-attempts.json)。r01 的 agent step 是 harness 合成错误消息。

| Round / GPU | Trial | 原奖励 | 检查完成 | Agent step / tools | 最终文件 / +行 / -行 | 总 / agent / verifier 秒 |
|---|---|---:|---:|---:|---:|---:|
| flash-r01 / 0 | flash-r01-gpu0__PFZMB2r | 0 | 0/26 | 1 / 0 | 0 / +0 / -0 | 312.6 / 247.6 / 41.4 |
| flash-r01 / 1 | flash-r01-gpu1__Wyooby5 | 0 | 0/26 | 1 / 0 | 0 / +0 / -0 | 304.3 / 238.7 / 40.0 |
| flash-r01 / 2 | flash-r01-gpu2__LheAvDh | 0 | 0/26 | 1 / 0 | 0 / +0 / -0 | 306.7 / 241.4 / 41.4 |
| flash-r01 / 3 | flash-r01-gpu3__YAsUWXb | 0 | 0/26 | 1 / 0 | 0 / +0 / -0 | 306.9 / 239.4 / 42.2 |
| flash-r02 / 0 | flash-r02-gpu0__c6e2QyB | 0 | 25/26 | 80 / 99 | 2 / +150 / -20 | 829.6 / 756.6 / 49.5 |
| flash-r02 / 1 | flash-r02-gpu1__AQgHneN | 0 | 25/26 | 41 / 42 | 1 / +43 / -22 | 438.1 / 366.0 / 48.6 |
| flash-r02 / 2 | flash-r02-gpu2__AbLUPwu | 0 | 0/26 | 49 / 49 | 2 / +204 / -21 | 456.6 / 393.3 / 39.6 |
| flash-r02 / 3 | flash-r02-gpu3__d7vsaaC | 0 | 25/26 | 79 / 92 | 2 / +278 / -24 | 998.3 / 924.4 / 49.3 |
| flash-r03 / 0 | flash-r03-gpu0__jHESAgf | 1 | 26/26 | 56 / 58 | 2 / +147 / -20 | 507.1 / 436.8 / 47.0 |
| flash-r03 / 1 | flash-r03-gpu1__SJTzQMk | 0 | 0/26 | 59 / 59 | 2 / +143 / -23 | 540.7 / 477.2 / 39.4 |
| flash-r03 / 2 | flash-r03-gpu2__oDYJkWp | 1 | 26/26 | 61 / 66 | 2 / +192 / -15 | 631.8 / 561.4 / 46.5 |
| flash-r03 / 3 | flash-r03-gpu3__9W9EUiH | 1 | 26/26 | 65 / 71 | 2 / +290 / -22 | 646.7 / 574.4 / 48.6 |
| flash-r04 / 0 | flash-r04-gpu0__Y6Qdwbv | 0 | 26/32 | 77 / 76 | 2 / +159 / -20 | 647.7 / 574.5 / 50.1 |
| flash-r04 / 1 | flash-r04-gpu1__sgXJ5Pe | 1 | 32/32 | 64 / 63 | 1 / +38 / -18 | 591.2 / 514.6 / 52.8 |
| flash-r04 / 2 | flash-r04-gpu2__eboJvq3 | 0 | 26/32 | 59 / 66 | 2 / +161 / -19 | 629.7 / 556.3 / 49.6 |
| flash-r04 / 3 | flash-r04-gpu3__vzFrKaL | 0 | 0/32 | 73 / 76 | 2 / +244 / -19 | 836.1 / 772.2 / 40.4 |


检查数为顺序 fail-fast 的已认证通过数，后续未运行不是 pytest skip。失败时保留首个异常和 worker 未完整退出的生命周期错误；Harbor trial 正常完成也不等于候选通过。原始 verifier 日志与 completion.json 均在证据包中。

| 批次 / GPU | 原奖励 | 最终完整重评 | 空外层错误输入 | CPU mask 等待 GPU | 原因 / 评分判断 |
|---|---:|---:|---|---|---|
| r01 / 0–3 | 全 0 | 未重放 | 未执行 | 未执行 | 无模型响应；基础设施故障 |
| r02 / 0 | 0 | 1 | 32 项套件通过 | 独立未等待 | 原 OOV false negative 已修正 |
| r02 / 1 | 0 | 1 | 32 项套件通过 | 独立未等待 | 原 OOV false negative 已修正 |
| r02 / 2 | 0 | 0 | 首项失败后未测 | 独立等待 | agent 同步缺陷 |
| r02 / 3 | 0 | 1 | 32 项套件通过 | 独立未等待 | 原 OOV false negative 已修正 |
| r03 / 0 | 1 | 0 | 6/6 错误接受 | 独立未等待 | 原 false positive 已修正 |
| r03 / 1 | 0 | 0 | 6/6 正确报错 | 独立等待 | agent 同步缺陷 |
| r03 / 2 | 1 | 0 | 6/6 错误接受 | 独立未等待 | 原 false positive 已修正 |
| r03 / 3 | 1 | 1 | 6/6 正确报错 | 独立未等待 | 通过 |
| r04 / 0 | 0 | 0 | 6/6 错误接受 | 独立未等待 | 空计数漏处理 |
| r04 / 1 | 1 | 1 | 6/6 正确报错 | 独立未等待 | 通过 |
| r04 / 2 | 0 | 0 | 6/6 错误接受 | 独立未等待 | 空计数漏处理 |
| r04 / 3 | 0 | 0 | 6/6 错误接受 | 独立等待 | 隐式同步及空计数缺陷 |

所有 12 个有效答案还通过独立的改变 mask、数量、数据值并复用非连续目标的 8 项语义检查。它不能单独证明同步或错误输入正确，故与其余检查分别报告。

## 可重放证据与提交边界

[rollout-evidence.zip](rollout-evidence.zip) 包含 4 批全部 portable 导出、capture smoke、native JSONL/ATIF、完整 tracked/untracked 最终改动、原始奖励/日志、manifest、独立挑战、旧/新完整重放、文件清点和执行脚本。包内 EVIDENCE-MANIFEST.json 记录每个文件 SHA-256；各 campaign 的 pre-run 哈希和事后相等检查在原记录中。逐次 UUID 和最终 archive 绝对路径可从 rollout-attempts.json 定位。共 424 个模型批次导出文件（109+105+105+105），全部导出哈希核对通过，真实凭据扫描无需脱敏替换。

A100 的原始完整 tar 保留于 `/data/codex-pr63-rollouts-20260918/<round>/jobs/<job>/<trial>/agent/final-state/full-repository.tar.gz`，含 .git、忽略文件和 native 文件；因每个约 1.4 GB 不提交到 Git。12 个有效答案实际用这些 tar 完整恢复并重放；r01 仅验证捕获哈希，不声称做了独立行为重放。可携证据不等于离线附带了这些完整 tar，离开该 A100 后重放需取回相应快照。镜像也尚无 registry digest。

本轮使用的运行修订依次为 `9426c3232ae56eb41e138f89601a02eb6de3a968`（r02）、`f61a13d63b2d8b307af69ae8b7a092c09b113e05`（r03）、`5a4cf5315f94bb267428cbe63c76c9dc36fb924d`（r04）。代码修正已 push 到 origin/harden-pr-63 并在 A100 pull。最终文档和证据打包在所有 campaign 完成后产生，不改写运行时哈希，也不改变测试逻辑；最终提交身份由 Git commit 给出。

接受范围：v1.3.2 的 32 项行为评分与已审阅的 12 个真实答案一致，Oracle/独立替代实现证明当前边界可解。本轮没有未关闭的已确认 task/verifier 缺陷。旧 18 项反作弊控制矩阵是 v1.3.0 历史证据；v1.3.2 明确重跑四个模式控制，不把历史矩阵冒充新版重跑。不宣称没有未知漏洞，也不把 12 个开发样本解释为总体 pass rate。

## Case handoffs

### CPU-mask OOV scope correction (v1.3.1)

- Behavior / contract: CPU-mask merge support is explicit; CPU-mask OOV preprocessing is absent from the Qwen3-VL repair contract. Normal CUDA-mask OOV behavior is preserved.
- Mode / scope: Oracle-based; real production SupportsMultiModal initialization and lookup, small deterministic weights replacing full model weights.
- Artifacts: complete r02 final states, native logs, ATIF and untracked files available; all four originals and revised suites replayed without candidate edits.
- Stable boundary: configure_mm_token_handling → _embed_text_input_ids → embed_input_ids → production merge. Qwen3-VL at Base does not enable OOV handling; normal runners produce CUDA masks.
- Expected / actual: a correct merge-only repair should preserve normal CUDA-mask OOV preparation. v1.3.0 instead rejected three repairs on CPU/CUDA mismatch in unmodified masked_fill.
- Remediation: retain an in-vocabulary CPU-mask interface case and normal OOV CUDA-mask case; do not make the CPU case wait or relax output/memory/count requirements.
- Outcome: r02 originals [0,0,0,0], old replay [0,0,0,0], v1.3.1 replay [1,1,0,1]. GPU2 independently blocks in .to; it is not an OOV false negative.
- Controls / identities: controls-v131 and replay-r02-v131 contain pre-run task hashes, exact image, archive identities and post-run equality. Oracle and index-copy alternative both 1; Base/forged-success-exit 0.
- Confidence: reproduced; promoted as a fixture correction. Later empty-container checks are independent and retain these three successes.

### Empty outer embedding count mismatches (v1.3.2)

- Behavior / contract: incorrect embedding/placeholder counts must raise a useful error for either mask device; empty inputs are a no-op only when no placeholders exist. This is explicit.
- Mode / scope: Oracle-based, same real merge boundary as existing malformed-count checks; no model-wrapper behavior change or model-forward requirement.
- Artifacts: complete r03 originals captured before grading; all messages/actions/tool results and final tracked/untracked code reviewed. Ignored files/native assets retained in replay.
- Minimal malformed-count event: CUDA destination (5,7), Boolean CPU/CUDA mask with two true rows, source [], (), or CUDA (0,7) tensor. Expected ValueError identifies 0 and 2; GPU0/GPU2 returned unchanged without error for all six forms.
- Reference role: expected behavior derives from the disclosed count contract. Oracle is a solvability control, not an algorithm template.
- Why missed: the old zero-count fixture passed [empty_tensor], whose outer length is 1; two answers retained len(multimodal_embeddings)==0 early return.
- Independent vs scored cases: challenge-v2 uses 5×7 and two placeholders; scored cases use 9×16, three placeholders, both mask devices and all three outer forms. Real CUDA destination/source; no mocked error path.
- Original outcomes: r03 [1,0,1,1]. Independent empty-case results: GPU0/2 accept all six wrongly; GPU1/3 reject all six correctly. Independent pending-work test finds GPU1 waits; others return before event completion.
- Revised full suite: [0,0,0,1]. Old suite replay reproduces [1,0,1,1]. Complete Oracle and alternative remain 1 (32/32), Base and forged-success-exit remain 0.
- Frozen inputs: challenge-v2-flash-r03/inputs-before.json records script and all four full archive hashes before execution; results.json confirms unchanged. replay-r03-v132 contains both full-suite commands, task pre-hashes, archive hashes and after checks. Controls-v132 records exact inputs and command.
- Confidence / stage: confirmed false positives; six cases promoted without changing the task instruction. r02 v1.3.2 replay remains [1,1,0,1]. Fresh four-attempt r04 and complete replays agree at [0,1,0,0]; no new scoring defect found.
