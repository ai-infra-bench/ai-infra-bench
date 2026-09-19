# PR60：版本审查与校准记录

## 最新发布：v1.8.6（2026-09-19）

v1.8.6 修复了声明环境 A100 所走的 FlashAttention 2 路径：全零 context prefill 不再进入 paged context kernel，FA2 混合批次拆分执行，CUDA graph 使用稳定输出缓冲区，并在 capture 时构造合法的非零 DCP context。verifier 的局部真实后端检查也不再直接向 FA2 提交其不支持的零/非零混合批次。

固定镜像中的官方 verifier 已在两张 NVIDIA A100-SXM4-40GB 上完成 Oracle 24/24、reward=1、worker_exit_status=0，14 组真实双卡引擎组合全部完成；未修改 Base 在预期的 DCP slot mapping 门禁处得到 reward=0、2/24。没有重跑历史模型答案、其他负对照或完整评分信任矩阵。详见 [a100-fa2-validation.md](a100-fa2-validation.md)。

## 历史：v1.8.5（2026-09-18）

最新题面已明确支持合法配置，而不只示例中的 interleave=2；verifier 增加超时子进程日志保存，不改变阈值、断言或评分。该冻结版本的四次 GPT-6 Astra/high 实测为 1 次通过、3 次失败；逐份轨迹及最终代码审查后，10 项隔离诊断支持失败来自候选实现遗漏，未确认新的 verifier 误判。详见 [latest-rollout-review.md](latest-rollout-review.md)。这不代表全范围无缺陷，也不将历史校准改记为最新版本成绩。

下方 v1.8.4、v1.8.3 章节保留当时的运行及发布状态（包括当时尚未推送的描述），不是当前版本状态。完整四项 Base/Oracle/正负对照校准属于 v1.8.4；v1.8.5 未重新执行该完整矩阵。A100 与评分信任审查等开放限制仍保留。

## 历史：真实引擎覆盖与 Oracle 修订（v1.8.4）

本轮由 GPT-6 Astra/high 串行实验的逐份审阅发现两个具体缺口。原始 r01 在 v183 得 1 分，但不能据此认定所有正常配置正确。完整模型轨迹和所有 tracked/untracked 修改已审阅，历史成绩不覆盖；新增输入先独立诊断，再纳入实现无关的行为评分。校准最终状态以 e2e-evidence.json 为准；下方 v183 章节是历史记录，不能当作 v184 成绩。

## v184 修订与公开合同

题面不变，未增加公开脚本、内部接口或修法提示。原合同要求 DCP 普通批量生成、支持的 cache layouts 和 CUDA graph 正确；部分 prefill 是在正常 token budget 下对该生成行为的检查，不是新增内部实现要求。环境和镜像不变。

1. 新增 FlashInfer NHD/HND × eager/graph 的部分 prefill：13/62/63-token 提示，block32、interleave2、maxbatch32，动态接入及结束，共 32 个生成 token。旧 Oracle 把 base-2 LSE 送入自然对数 merge，在 151/256 维 logprob 超差，最大约 0.107432；GPT-6 原答案同条件通过。Oracle 现统一合并前的 LSE 单位。
2. 新增 FlashAttention NHD/HND、interleave1 的 graph 启动及完整生成。旧 Oracle 和原 GPT-6 答案都存在 post-capture dummy 复用旧 attention 元数据的问题。Oracle 在要求跳过 attention 的 dummy 中不选 graph；独立人工正对照则更新 graph 所需元数据。两者均保留真实请求 CUDA graph 和正常 custom-allreduce。
3. 上述检查使用真实双卡 LLMEngine、model、KV 写入、attention、collectives 与图回放，按 request/token 逐个比较同权重独立 CPU FP32 Transformers 的全部 256 维 logprob，atol0.02/rtol0。既不绑定修复函数名，也不根据候选内部结构选择预期。

保留旧全部检查，总数 24，完整引擎组合 14；Eagle 集成测试仍有下述明确替代边界。新校准包含 Base、修复 Oracle、旧 v183 Oracle 反例，以及原 GPT-6 答案加另一种 dummy 修法的人工正对照。人工正对照不计模型成功样本。未新跑的旧控制明确 pending，不继承旧成绩；共享 H20 结果不代表 A100 或独占性能认证。评分信任与依赖 cutoff 等既有开放限制不变，不重复受限安全探针。

完整 Harbor 已完成：Oracle 1/24，另一修法的人工正对照 1/24，Base 0（完成2/24），旧 v183 Oracle 0（完成20/24，在新增 FI NHD partial-prefill 真数值检查失败）。两份正对照均完成14种引擎组合及3组 Eagle，所有输入哈希未变、无 Harbor 错误。只校准这四项，其余旧控制 pending。

版本更换后只续跑原授权剩余三轮；PR60 原 r01 属于 v183，r02–r04 属于新版本，不能直接合并为同版本 pass@k。PR61 未修改。不自动 commit/push。

## 历史：Eagle verifier 内部接口耦合修复（v1.8.3）

本轮只修订已确认的 verifier 公平性问题，不新增模型调用，不改写历史成绩，不自动推送。使用 ai-infra-bench-rollout-review 对受影响的功能门禁复验；不是全量轨迹/安全认证。v1.8.2 的 HND 修复及八组合引擎测试保留。

## 已确认的问题

原测试直接用两个参数调用 runner.prepare_inputs。保存的 GPT-5.6 Sol/high r02 给该内部方法增加必需的 use_cudagraph 参数，并同步更新真实生产调用点；公开任务没有冻结这个内部签名。旧 fixture 因 TypeError 失败，未触达原本要检查的 Eagle 行为。

原先的首个失败理由不公平，但不意味着 r02 全部正确：独立诊断已发现其 FlashInfer HND 输出错误。旧版 r02 得0、13/21必须保留；新版评分要把接口耦合与真正的数值错误分开。

## 正式修改

- 从正常 execute_model → sample_tokens → take_draft_token_ids 驱动请求，不直接调用 prepare_inputs 或 propose，不检查签名，不加入特定答案的参数适配。
- Target/Draft 权重用确定性模型替代；生产请求更新、输入准备、采样、Eagle proposal、FlashInfer CUDA attention、草稿回传真实执行。
- 从 scheduler 消息边界提供 permissive grammar mask，使正常结构化输出链路回传草稿 token，不读取私有 batch 状态。不把此测试称为 grammar 编译或真实 Eagle 权重端到端测试。
- 精确检查 target token 和两步 draft token，按请求 ID 比较，允许内部 batch 重排。覆盖 [4,7]、跨 block 的 [15,23] 及反序 [23,15]。
- 21 个必需检查点不变；真实双卡引擎 FA/FI × NHD/HND × eager/graph 八组合及独立 CPU 全词表参考完全不变。

题面、环境、镜像、Oracle 均不变。Agent 不会得到新的公开测试、实现提示或函数约束。

## 完整 Harbor 校准

五项均通过实际 Harbor 评分入口运行，新分数如下；保存答案重放不是新的模型实验。

| 对照 | Reward | 完成检查点 | 原因 |
|---|---|---|---|
| Oracle | 1 | 21/21 | 三组 Eagle 与八种真实引擎组合全通过 |
| 原样 r01 | 1 | 21/21 | 三组 Eagle 与八种真实引擎组合全通过 |
| 原样 r02 | 0 | 19/21 | 三组 Eagle 全通过，真实 FlashInfer HND eager 数值错误 |
| Eagle 回归反例 | 0 | 13/21 | 草稿 [[1,0],[1,0]]，预期 [[1,6],[1,9]] |
| Base | 0 | 2/21 | 真实 DCP slot 地址错误 |

r02 的 HND 输出247/256维超差，最大绝对误差1.623551845550537，允许0.02；未再出现内部签名 TypeError。原始0分、13/21不覆盖，新0分、19/21是不同版本下的重评分。Oracle/r01的完整引擎最大 logprob 误差0.0024595260620117188，小于0.02。

## 版本与原始资料

- 运行目录：runs/pr60-eagle-boundary-20260918/controls/。运行前冻结 task/ 和 frozen-hashes.json；每项 *-inputs.json 记录命令、镜像、GPU 绑定、prepared 全文件哈希。
- Harbor 0.22.0，共享 H20 ×2，两组不重叠设备，最多两项评分并行；不代表 A100 验证。
- 镜像 sha256:462fc769cac14468d0c1a7128eb17116c728e12e31efaee14b9ea7fd6c3e9868；Base be3af2d29e2507f32b2190fe015cd6609b348caa。
- 修改起点 af2e23e03652f0a50d6721d6ddb9e51c96ae4d04，本地 review/pr-60。结果绑定运行前文件快照，不伪造尚不存在的提交身份。
- 原始答案来自 gpt56-eight-parallel-20260918/pr60/ 下 r01/task__kUb8Fy3 与 r02/task__y2KxLKq。导出 tracked diff 和 untracked 测试，评分后核对文件与原答案一致。重放不是新增模型作答。
- 完成导出后，validation/evidence.zip 收录完整评分输出和输入身份；旧报告、索引和证据放在其 historical-v182/，更早材料递归保留。ZIP 不包含完整模型轨迹，原始实验目录另存。

## 仍然开放的限制

本轮只校准相关五项，不把未重跑的历史控制声明为新版通过。完整评分信任、此前受限安全探针、A100 认证及已有 native donor/cutoff 限制保持开放。没有重新逐条审核八份完整模型轨迹。Eagle 是明确替代边界的 runner 集成检查；另有真实 TP/DCP 引擎测试，但不等价于所有配置、HTTP、真实模型质量或吞吐基准。

不能据此宣称绝对没有缺陷、完全防篡改或无条件可合入。PR61 未在本轮修改。
