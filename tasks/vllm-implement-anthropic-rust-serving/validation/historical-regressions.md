# Historical Anthropic compatibility regressions

These upstream reports inform high-information verifier cases. They do not
define the task statement and are not visible during the agent phase.

| Source | Observable regression | Verifier case |
| --- | --- | --- |
| [vLLM issue 45367](https://github.com/vllm-project/vllm/issues/45367) | Streaming `message_start.message` omitted required `type` and `role`, which strict clients rejected. | Strict SDK stream parsing plus raw first-event assertions. |
| [vLLM issue 45079](https://github.com/vllm-project/vllm/issues/45079) | Anthropic usage omitted cache creation/read fields. | Non-stream and terminal-stream cache-read propagation, plus SDK parsing of the cache-creation count. |
| [vLLM issue 48874](https://github.com/vllm-project/vllm/issues/48874) | Mid-conversation system messages were rejected or rendered positionally in a way that displaced the user task. | Top-level plus inline system messages, multiple inline blocks, and system after user/assistant history. |
| [vLLM issue 38738](https://github.com/vllm-project/vllm/issues/38738) | Multi-turn tool history produced an invalid empty assistant message. | Assistant tool-use followed by one and multiple user tool-result blocks, with and without assistant text. |
| [vLLM issue 51572](https://github.com/vllm-project/vllm/issues/51572) | API-key middleware accepted Bearer authentication but rejected Anthropic's `x-api-key`. | Not scored after the user removed authentication coverage. |
| [vLLM issue 52489](https://github.com/vllm-project/vllm/issues/52489) | A `tool_reference` inside `tool_result` reached the template in an incompatible shape and crashed. | Tool-reference coverage removed at the user's request; ordinary tool-result text remains covered. |
| [vLLM issue 45807, referenced by the Rust RFC](https://github.com/vllm-project/vllm/issues/47753) | A matched stop string was flattened to generic `end_turn`. | Text stop reason maps to `stop_sequence` and preserves the exact matched sequence in stream and non-stream modes. |
| [vLLM issue 31871](https://github.com/vllm-project/vllm/issues/31871) | Streaming tool syntax leaked as text instead of becoming tool-call deltas. | Whole, single-token, and mixed token-chunk schedules using the real Qwen tokenizer; raw tool markers must not leak into text blocks. |
| [vLLM issue 51697](https://github.com/vllm-project/vllm/issues/51697) | End-of-stream flush duplicated tool arguments and leaked markers. | Concatenated `input_json_delta` parses exactly once and equals non-stream arguments. |
| [vLLM issue 18412](https://github.com/vllm-project/vllm/issues/18412) | Streaming tool calls lacked IDs that were present in non-stream responses. | Every stream tool block has a stable non-empty ID; parallel calls have distinct IDs. |

Additional source-level regressions represented by this verifier include
combined text and tool output, empty output, tool block ordering, and parity
between selected Messages and token-counting inputs. Thinking-signature and
media-rejection coverage were removed at the user's request.
