# 最新 Python Anthropic 接口：20 项失败逐项分析

对照版本是 vLLM main `e962733e08d10f7ca65dac4df99e116460b8b174`，客户端是
`anthropic==1.3.0`。评分用例来自本任务提交 `f4163bc`，请求及断言未修改；
`pytest_plugin.py` 只把服务启动类替换成 Python 适配器。

115 项共 95 通过、20 失败、0 error、0 skip。其中 35 项是 SDK fixture 自检；
实际访问 Python 服务的 80 项为 60 通过、20 失败。进一步扣除 8 项已有 API/
后端正向检查，72 项 Anthropic 行为测试为 52 通过、20 失败。
另外，使用真实 CPU runner 和 dummy weights 的 10 项基础检查全部通过。

对照边界为：真实 HTTP/SSE → 最新 Python 路由/验证 → Qwen 模板和 tokenizer
→ AsyncLLM 输入处理 → EngineCore 请求 → 确定性的 EngineCore token 输出
→ 真实输出处理、工具/思考解析和 Anthropic 转换 → 官方 SDK。
只有 EngineCore 的生成与传输被替换；没有改写服务返回的 JSON/SSE。

## 如何判断保留

本报告采用讨论中收窄后的目标：实现明确列出的 vLLM Anthropic 服务能力，
并使这些能力的 HTTP/SSE 行为符合约定。当前 instruction 中“所有 SDK 功能”
仍需在下一阶段同步收窄；本次只测试和整理建议，没有删除评分用例。

- Python 尚未实现、且已决定排除的功能，不应继续要求成功处理。
- 已选能力中的错误传播、鉴权、字段格式等问题，不能因为 Python 有缺陷而删除。
- 如果断言超出说明、混入模型配置假设或重复已有覆盖，应改写/合并。
- “SDK 能按 HTTP 状态码抛出异常”和“错误包符合 Anthropic 协议”是不同要求。
  后者如果保留，必须在任务契约里写清楚，不能把 Python 的行为当作唯一标准。

建议按原 case 数量计：10 项保留行为目标，4 项改写或合并，6 项不保留成功要求。
这不是声称存在 20 个独立产品 bug；多个失败由同一个错误格式转换问题导致。

## 01. Thinking 然后正文的流式输出

Case：`test_reasoning_then_text_stream`

测什么：指定 Qwen reasoning parser，发送 `thinking={type:enabled,budget_tokens:1024}`，
注入 `<think>reasoning sentinel</think>answer sentinel`，要求 SDK 最终得到
有序的 thinking/text 两个块，并且内容完整。

最新 Python 为什么失败：原测试默认模板参数是 `enable_thinking=false`。
Python 的 `AnthropicMessagesRequest` 没有 `thinking` 字段，转换后的
`thinking_token_budget` 实测为 null，因此请求没有打开思考模式，结果只有 text。
这首先是测试配置与 Python 已有能力的边界不一致。

补充实验：仅把服务端模板配置改成 `enable_thinking=true` 后，Python 确实产生
thinking/text deltas，但 thinking 的 `content_block_start` 缺少 `signature`，
严格 SDK 立即抛出 `APIResponseValidationError`。使用去掉开头 `<think>` 的
正常续写输出，仍出现相同缺字段问题，排除了重复标签造成的误判。

保留建议：改写后保留“已开启 reasoning 的模型能输出合法 Anthropic thinking
流”的目标。不要要求尚未纳入范围的 SDK `thinking` 请求参数负责开启功能；
明确模型配置，再验证块顺序、内容和 SDK 要求的字段。不能因为原配置不匹配
而删除 reasoning 输出检查，也不能把整项直接解释为 Python 单一 bug。

证据：[请求类型][P-request]、[thinking 起始事件][P-thinking]、
[SDK 1.3 ThinkingBlock][SDK-thinking]；补充原始事件见 `failure-details.json`。

## 02. 非流式引擎错误的 Anthropic 错误包

Case：`test_engine_error_uses_anthropic_error_surface[nonstream]`

测什么：引擎以 `FinishReason.ERROR` 结束，SDK 必须得到失败，响应带
`type:error` 和 `error.type:api_error`，不能返回普通成功消息。

最新 Python 为什么失败：实际 HTTP 500，顶层错误包存在，但
`error.type` 是 `InternalServerError`。通用错误处理器把 GenerationError
映射成内部类名，Anthropic 路由直接复制这个名字，没有转换成协议错误类型。

为什么保留：引擎失败属于已选生成能力的正常异常路径，服务端错误协议应一致。
当前 SDK 已能按 500 抛出异常，失败点是错误类型契约，不应夸大为 SDK 完全无法
处理错误。保留时应把 `api_error` 格式写进说明，并将本 case 的 HTTP 断言
收紧为 500；当前与流式共用的 `(200,500)` 对非流式过宽。

证据：[通用错误映射][P-error]、[Anthropic 错误转换][P-error-adapter]、
[官方错误协议][API-errors]。

## 03. 流式引擎错误不能伪装为正常结束

Case：`test_engine_error_uses_anthropic_error_surface[stream]`

测什么：流式生成在尚未输出文本时遇到引擎错误，客户端必须观察到错误；如果
HTTP 200 已发出，应通过 SSE error 事件传播，不能作为正常完成返回。

最新 Python 为什么失败：实测 SDK 没有抛异常。原始 SSE 是 message_start、
message_delta（`stop_reason:end_turn`）、message_stop，没有 error 事件。
OpenAI 流式生成器把“没有文本、没有 token、此前也没有 token”的输出当成空
prefill chunk 跳过；这个 continue 位于错误 finish reason 检查之前，所以
第一条输出本身就是终止错误时，错误检查被绕过。之后 Anthropic 转换器按默认
stop 原因结束。

为什么保留：这是错误被报告为成功，直接影响请求结果和上层恢复逻辑。修复
Antropic 适配时必须保留引擎错误语义，不涉及新增模型功能或外部服务。
当前 case 只覆盖“首个 token 前失败”；应保留该边界，并另行补充已有内容之后
失败的场景，不应把本 case 描述成已覆盖所有中途错误。

证据：[OpenAI 流式生成器][P-openai-stream]；`failure-details.json` 保存了
原始 HTTP 200 和完整 SSE。

## 04. 缺 max_tokens 且消息为空的错误包

Case：`test_anthropic_validation_error_envelope`

测什么：发送 `{"model":"local-model","messages":[]}`，要求 HTTP 400、
Anthropic 错误包和非空错误消息。

最新 Python 为什么失败：缺少必填 `max_tokens`，请求先进入全局 Pydantic/
FastAPI 验证错误处理器。实际响应没有顶层 `type:error`，断言触发 KeyError。
该处理器返回通用 OpenAI 风格 ErrorResponse，未经过 Anthropic 路由转换。

保留建议：保留“验证失败也必须使用正确协议错误包”的目标，但这条输入与
第 14 项 missing_max_tokens 覆盖同一入口；messages 为空没有被单独验证。
建议把非空 message 断言并入负向矩阵，合并本 case；或把本 case 改成真正的
畸形 JSON，覆盖不同的解析失败入口。没有理由为了数量保留当前重复输入。

证据：[全局验证错误处理][P-validation]、[评分断言][T-sdk]。

## 05. SDK 默认 x-api-key 鉴权及拒绝错误密钥

Case：`test_x_api_key_authentication_and_rejection`

测什么：服务配置密钥后，官方 SDK 用正确密钥能请求成功，已有 Bearer 方式
继续有效，错误密钥仍被拒绝。

最新 Python 为什么失败：第一条正确 SDK 请求就得到 HTTP 401
`{"error":"Unauthorized"}`。补充实验确认：正确 x-api-key 为 401，
同一个正确密钥放进 Bearer header 为 200，错误 x-api-key 为 401。
鉴权中间件只读取 Authorization，不读取 x-api-key。

为什么保留：鉴权是现有服务能力，而 x-api-key 是官方 SDK 的默认发送方式。
要求用户关闭鉴权或改写 SDK header 才能使用接口，不符合所选客户端兼容目标。
修复必须同时验证正确密钥与错误密钥，避免用“关闭鉴权”换取通过。

证据：[鉴权中间件][P-auth]；三组 HTTP 对照见 `failure-details.json`。

## 06. 工具结果中的 tool_reference

Case：`test_request_variant_reaches_rust_semantic_path[tool_result_tool_reference]`

测什么：历史 tool_use 对应的 tool_result 内容包含
`{"type":"tool_reference","tool_name":"TOOL_REFERENCE_SENTINEL"}`，
要求请求成功，而且引用名称出现在真实引擎 prompt 中。

最新 Python 为什么失败：HTTP 400，错误为 `BadRequestError`，消息是
`Unexpected item type in content.`。Python 明确识别并转换 tool_reference，
但把它保留成 tool 消息中的结构化 content 列表；Qwen 模板不接受这个项目类型，
请求在渲染阶段失败，没有进入生成。

保留建议：这与完全没有声明/处理的新内容类型不同，值得保留“引用与真实模板
兼容”的目标，但当前“名称必须进入 prompt”是额外语义，不能仅凭 schema 有该
类型就推出。应先明确本地服务对引用采取保留、展开还是忽略，再写相应断言。
若约定接收并保留引用，可继续要求名称被保留；若约定忽略，应验证忽略不会破坏
其余工具结果。若整体排除工具引用，则转成明确的拒绝测试。原 case 不宜不加
说明地宣称为必保留。

证据：[Python 已有工具引用转换][P-tool-result]、[Qwen 模板的 render_content
分支][Q-template]。

## 07. 用户输入中的 search_result

Case：`test_request_variant_reaches_rust_semantic_path[search_result_input]`

测什么：用户内容包含 search_result，要求请求成功，搜索结果的标题和正文都
进入真实 prompt。

最新 Python 为什么失败：HTTP 400。AnthropicContentBlock 的 Literal 类型
集合没有 search_result；该块的 source 字符串也与当前模型使用的 source
字段形状不同。请求在 schema 验证阶段就被拒绝。

为什么不保留原成功要求：这要求新增当前 Python 没有实现的内容类型，属于已
讨论排除的能力范围。它不是普通文本/工具支持中的回归。可在明确的“未支持
类型应规范拒绝”负向集合中另测错误协议，但不应继续要求成功渲染搜索结果。

证据：[内容块定义][P-blocks]。

## 08. 自定义工具的全部字段

Case：`test_request_variant_reaches_rust_semantic_path[custom_tool_all_fields]`

测什么：发送含 strict、defer_loading、eager_input_streaming、input_examples、
allowed_callers、cache_control 的工具定义；实际断言只查工具名称、说明和
input_examples 的文本标记是否在 prompt 中，并没有逐项验证“全部字段”。

最新 Python 为什么失败：HTTP 请求成功、工具名称和说明已进入 prompt，但
`TOOL_EXAMPLE_SENTINEL` 不在 prompt。AnthropicTool 没有 input_examples 字段，
转换只转发 name、description、input_schema、strict、defer_loading。

保留建议：保留自定义工具定义测试，缩小到约定支持的字段并分别验证。按当前
能力范围，不保留 input_examples 必须影响 prompt 的要求；未支持字段如果允许
被接受并忽略，应明确说明。也不应把此失败描述为 strict 或整个工具功能不可用。

证据：[工具 schema][P-tools]、[工具转换][P-tool-convert]。

## 09. server_tool_use 历史块

Case：`test_request_variant_reaches_rust_semantic_path[server_tool_use_history]`

测什么：assistant 历史中含 server_tool_use/web_search，要求其中 query 和
之后的用户消息进入 prompt。该 case 不执行 web search，但要求理解该历史类型。

最新 Python 为什么失败：HTTP 400，server_tool_use 不在内容块 Literal 中，
请求未进入转换、渲染或生成。

为什么不保留原成功要求：即使不执行外部服务，接受/转换该新历史类型也是额外
能力。收窄到当前 vLLM 支持范围后，应移出成功矩阵，而不能借“只是历史内容”
把未实现类型继续藏在必过要求中。

证据：[内容块定义][P-blocks]。

## 10. web_search_tool_result 历史

Case：`test_request_variant_reaches_rust_semantic_path[web_search_result_history]`

测什么：历史里包含 web_search 的 server_tool_use，以及错误结果
web_search_tool_result，要求 `query_too_long` 被带入 prompt。

最新 Python 为什么失败：HTTP 400，server_tool_use 和 web_search_tool_result
都不属于当前内容类型集合。错误发生在请求验证，不是搜索服务调用失败。

为什么不保留原成功要求：本地前端目前没有这组托管工具历史表示，原成功要求
超出收窄范围。它也不能因为载荷是工具的“错误结果”就被当成通用 HTTP 错误
处理测试；两者属于不同层。

证据：[内容块定义][P-blocks]。

## 11. web_fetch 与 code_execution 历史结果

Case：`test_request_variant_reaches_rust_semantic_path[web_fetch_and_code_execution_results]`

测什么：输入两个 server_tool_use 和对应 fetch/code 错误结果，要求
`url_not_accessible`、`execution_time_exceeded` 进入 prompt。

最新 Python 为什么失败：HTTP 400，相关内容类型都未声明，验证同时报告多个
不匹配；并未访问 URL 或执行代码。

为什么不保留原成功要求：要求新增两组未支持历史类型，不能用当前 Python
已支持功能作依据。建议移出成功矩阵；若未来明确加入这些类型，应分别给出
正常结果/错误结果的契约，而非只靠一个组合 case 定义功能。

证据：[内容块定义][P-blocks]。

## 12. Bash 与文本编辑器执行结果

Case：`test_request_variant_reaches_rust_semantic_path[bash_and_text_editor_results]`

测什么：输入 bash_code_execution_tool_result 和
text_editor_code_execution_tool_result，要求工具错误码和错误文本保留。

最新 Python 为什么失败：HTTP 400，相应 server_tool_use 和结果块不被
AnthropicContentBlock 接受，请求在 schema 层终止。

为什么不保留原成功要求：这不是普通自定义 tool_use/tool_result 的别名，
而是额外的托管工具类型。按已选范围，应移出成功矩阵；不应借普通工具调用
已支持，推导出这些联合类型也必须支持。

证据：[内容块定义][P-blocks]。

## 13. 工具搜索结果与 container_upload

Case：`test_request_variant_reaches_rust_semantic_path[tool_search_and_container_upload]`

测什么：输入 tool_search_tool_result 错误和 container_upload 文件标识，
要求错误文本与 file_id 都进入 prompt。

最新 Python 为什么失败：HTTP 400，server_tool_use、tool_search_tool_result、
container_upload 都未包含在请求内容类型集合里。

为什么不保留原成功要求：它引入工具发现和容器文件历史的额外语义，当前 Python
没有这些路径。应移出成功矩阵。未来若加入，应拆分工具搜索与文件引用两个
独立行为，避免组合 case 的一个失败掩盖另一项是否已实现。

证据：[内容块定义][P-blocks]。

## 14. 缺少必填 max_tokens

Case：`test_invalid_request_returns_anthropic_error[missing_max_tokens]`

测什么：messages 合法，但缺少 max_tokens，要求 HTTP 400 和规范 Anthropic
错误包。

最新 Python 为什么失败：状态码已是 400，但全局验证处理器返回通用
ErrorResponse，没有顶层 `type:error`。失败不是“没有拒绝非法请求”，而是
拒绝时使用了另一种协议格式。

为什么保留：必填字段验证是已选 Messages 接口的一部分，不能只覆盖成功请求。
建议以这项作为缺字段错误的主 case，并吸收第 04 项的非空错误消息断言。
错误包形状需在最终任务说明中明确。

证据：[全局验证处理器][P-validation]、[官方错误协议][API-errors]。

## 15. messages 为空

Case：`test_invalid_request_returns_anthropic_error[empty_messages]`

测什么：max_tokens 等必填字段齐全，但 messages 为空，要求在无有效对话时
返回 HTTP 400 和 invalid_request_error。

最新 Python 为什么失败：最新版本已从旧版的 500 改成 400，但错误类型仍是
`BadRequestError`。空列表在请求 schema 中未被禁止，后续渲染拒绝空对话，
通用异常被转换后保留了内部错误类型名。

为什么保留：这覆盖通过 schema 后、真正进入渲染的语义错误入口，与缺字段
case 不同。可以检测“只改全局 schema 错误处理，而遗漏渲染错误”的不完整
实现；保留这一行为不要求新增模型能力。

证据：[路由异常转换][P-error-adapter]、[通用错误映射][P-error]。

## 16. 非法消息角色 developer

Case：`test_invalid_request_returns_anthropic_error[invalid_role]`

测什么：向 Anthropic Messages 传入本契约不允许的 developer 角色，要求 400
及 Anthropic 错误包，而不是被 OpenAI 角色处理逻辑错误接受。

最新 Python 为什么失败：Python 正确拒绝了角色，但错误来自全局验证处理器，
响应缺少顶层 type，格式仍为通用 ErrorResponse。

为什么保留：两个协议共享内部聊天组件，角色边界容易被错误放宽。此 case
验证角色约束和错误格式。它与缺字段 case 共享当前根因，但输入维度不同，
适合作为同一个参数化负向矩阵保留，不需要各自额外的重复测试函数。

证据：[AnthropicMessage 角色集合][P-blocks]、[全局验证处理器][P-validation]。

## 17. 未知 content block 类型

Case：`test_invalid_request_returns_anthropic_error[unknown_content_block]`

测什么：输入 `type:unknown` 的虚构块，要求拒绝且返回 400/
invalid_request_error，防止把任意 JSON 都当作合法消息内容。

最新 Python 为什么失败：它已拒绝未知类型，但使用了缺少顶层 type 的通用
验证错误包。

为什么保留：这是协议结构的负向边界，独立于是否支持 document 或托管工具。
本 case 的 unknown 不属于 SDK 的合法类型，不应与“合法但本地未支持的类型”
混为同一功能缺口。可与其他验证错误共用参数化框架。

证据：[内容块定义][P-blocks]、[全局验证处理器][P-validation]。

## 18. 文本后端收到 base64 图片

Case：`test_unsupported_backend_media_fails_cleanly[base64_image]`

测什么：仅支持文本的后端收到 image/base64 请求，要求以 400/
invalid_request_error 拒绝。没有要求图片推理成功。

最新 Python 为什么失败：已返回 400，但 error.type 是 `BadRequestError`，
未做 Anthropic 类型映射。这里较旧 Python 的 500 已有所改善。

为什么保留：已支持 image 请求格式与特定后端不能处理图片是不同层；该测试
可检查后端能力错误是否正确返回给客户端，不需要 GPU 或视觉模型。
但当前 base64 数据只有 PNG 文件头，不是一张完整图片。建议换成完整的微型
图片，并确认拒绝来自文本后端能力检查，避免后续实现先解码图片时测到另一种错误。

证据：[评分输入/断言][T-request]、[路由异常转换][P-error-adapter]。

## 19. 文本后端收到 URL 图片

Case：`test_unsupported_backend_media_fails_cleanly[url_image]`

测什么：image/url 输入在文本后端上应返回规范 400，而非触发内部错误或
悄悄忽略图片。

最新 Python 为什么失败：与上一项一样，状态码正确，error.type 仍为
`BadRequestError`。当前失败并不是请求需要联网或图片下载失败。

为什么保留：URL 与 base64 是两条输入表示路径，负向边界都值得覆盖；可以
继续参数化，避免重复代码。当前 URL 是 `example.invalid`，建议使用可控的
本地图片 URL，或显式确认下载前的能力检查；否则无法保证未来仍在测同一层。

证据：[评分输入/断言][T-request]、[路由异常转换][P-error-adapter]。

## 20. 不支持的 document/PDF 输入

Case：`test_unsupported_backend_media_fails_cleanly[base64_document]`

测什么：本地范围不包含文档处理时，document 输入得到规范的 400 错误。
这是负向测试，和要求成功处理 search_result 的第 07 项不同。

最新 Python 为什么失败：document 不在请求内容类型集合中，在 schema 阶段
即被拒绝；error.type 是 `Bad Request`，不是 invalid_request_error。
它没有进入 PDF 解析、模板渲染或模型推理。

为什么保留：不支持一种功能仍需要对合法客户端请求给出可理解、符合约定的
错误；保留这个负向目标不等于要求实现 PDF。不过应把不支持文档的范围及拒绝
契约写清。当前载荷只是 PDF 头，建议用合法最小 PDF，或改成更明确的未支持
类型拒绝测试，避免将来文档 schema 扩展后由损坏文件意外“维持通过”。

证据：[内容块定义][P-blocks]、[全局验证处理器][P-validation]。

## 建议的下一步

先冻结收窄后的功能清单与错误协议，再执行以下修改：移出 07、09–13 的成功
要求；改写 01、06、08，合并/替换 04；保留 02、03、05、14–20 的行为目标，
修正过宽的错误断言和不完整媒体输入。之后用同一套共享断言复测 Rust 与 Python。
不能把“最新版 Python 全绿”设成删除测试的唯一目标，也不能在缺少明确契约时
要求 Rust 满足 Python 本身并未实现的新功能。

[P-blocks]: https://github.com/vllm-project/vllm/blob/e962733e08d10f7ca65dac4df99e116460b8b174/vllm/entrypoints/anthropic/protocol.py#L36
[P-tools]: https://github.com/vllm-project/vllm/blob/e962733e08d10f7ca65dac4df99e116460b8b174/vllm/entrypoints/anthropic/protocol.py#L74
[P-request]: https://github.com/vllm-project/vllm/blob/e962733e08d10f7ca65dac4df99e116460b8b174/vllm/entrypoints/anthropic/protocol.py#L121
[P-tool-result]: https://github.com/vllm-project/vllm/blob/e962733e08d10f7ca65dac4df99e116460b8b174/vllm/entrypoints/anthropic/serving.py#L404
[P-tool-convert]: https://github.com/vllm-project/vllm/blob/e962733e08d10f7ca65dac4df99e116460b8b174/vllm/entrypoints/anthropic/serving.py#L560
[P-thinking]: https://github.com/vllm-project/vllm/blob/e962733e08d10f7ca65dac4df99e116460b8b174/vllm/entrypoints/anthropic/serving.py#L867
[P-error-adapter]: https://github.com/vllm-project/vllm/blob/e962733e08d10f7ca65dac4df99e116460b8b174/vllm/entrypoints/anthropic/api_router.py#L39
[P-error]: https://github.com/vllm-project/vllm/blob/e962733e08d10f7ca65dac4df99e116460b8b174/vllm/entrypoints/serve/exception_handling/error_response.py
[P-validation]: https://github.com/vllm-project/vllm/blob/e962733e08d10f7ca65dac4df99e116460b8b174/vllm/entrypoints/serve/exception_handling/handlers/validation.py#L149
[P-auth]: https://github.com/vllm-project/vllm/blob/e962733e08d10f7ca65dac4df99e116460b8b174/vllm/entrypoints/serve/middleware/authenticate.py#L30
[P-openai-stream]: https://github.com/vllm-project/vllm/blob/e962733e08d10f7ca65dac4df99e116460b8b174/vllm/entrypoints/openai/chat_completion/serving.py#L449
[SDK-thinking]: https://github.com/anthropics/anthropic-sdk-python/blob/v1.3.0/src/anthropic/types/thinking_block.py
[API-errors]: https://platform.claude.com/docs/en/api/errors
[Q-template]: https://huggingface.co/Qwen/Qwen3.6-27B/blob/6a9e13bd6fc8f0983b9b99948120bc37f49c13e9/chat_template.jinja
[T-sdk]: https://github.com/ai-infra-bench/ai-infra-bench/blob/f4163bcf3166fd1799341d0bbc5defa8afea65b5/tasks/vllm-rust-anthropic-sdk-compat/tests/test_rust_sdk_matrix.py
[T-request]: https://github.com/ai-infra-bench/ai-infra-bench/blob/f4163bcf3166fd1799341d0bbc5defa8afea65b5/tasks/vllm-rust-anthropic-sdk-compat/tests/test_rust_request_matrix.py
