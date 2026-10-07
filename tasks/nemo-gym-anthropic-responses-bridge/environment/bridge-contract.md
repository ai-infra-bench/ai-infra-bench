# Public contract for the NeMo Gym protocol bridge

This document defines the supported protocol subset and new public interfaces
for the requested Messages / Responses bridge. It is part of the task.

## Carry a conversation across the bridge

Support user/assistant text as strings or text-block lists, including Unicode
and empty text. Preserve content order around tools and reasoning, in both
requests and responses. Consecutive same-role messages may be merged and
adjacent plain text parts concatenated without losing or reordering content.

For multi-turn tool use, preserve function names, descriptions, JSON object
schemas, call IDs, JSON-object arguments and result text. Support multiple
calls, including results returned in a different order. A result can be a
string or text-block list, joined with newlines; absent or false `is_error`
means a normal result. Preserve automatic, disabled, required and named tool
selection, mapping `any` to `required` and retaining the selected name.

The protocols represent some conversation data differently. Use these mappings
in both directions:

| Data | Compatibility requirement |
|---|---|
| Instructions | Messages `system` accepts a string or text-block list. Responses uses `instructions` and leading system/developer messages. Preserve fragment order and text, joining fragments with newlines when a single string is needed. System/developer messages occur only before conversation messages in this task. |
| Images | User base64 JPEG, PNG, GIF and WebP blocks map to Responses `input_image` data URLs, preserving decoded bytes. |
| Reasoning | Plain Messages `thinking` maps to Responses reasoning `summary_text`, distinct from visible answers. Support local/open-model histories with absent or empty opaque signatures. |
| Generation settings | Preserve `temperature`, `top_p` and maximum output length, including explicit zero values such as `temperature=0`. |

## Return a usable reply

Return valid response envelope types and nonempty IDs. Generated envelope/item
IDs may change; tool-call correlation IDs must not. Distinguish completion,
tool use, truncation and refusal: Messages `max_tokens` and `refusal` map to
Responses `incomplete_details.reason` values `max_output_tokens` and
`content_filter`, respectively, and back. Otherwise, use `tool_use` if tools
were emitted and `end_turn` if they were not.

Preserve the backend's nonnegative input/output token counts and cache-read
usage. Anthropic input tokens exclude cache reads; Responses input tokens
include them. Preserve both the total and cached portion without double
counting. Do not expose Gym token ID/logprob arrays in Messages replies.

For `stream: true`, return `text/event-stream` consumable by the installed
Anthropic SDK. Emit one message start and stop, correctly open/update/close
content blocks, and include final usage and stop information. Text, reasoning
and tool-argument deltas must address their own blocks. The reconstructed reply
must match the non-streaming reply semantically. The backend Responses call
remains non-streaming; buffering its complete reply before emitting SSE is
allowed.

Invalid or unsupported data and backend failures must produce explicit errors,
not silently lost content or successful empty answers. This includes unsupported
content/tool types, remote images, invalid base64, malformed or non-object
function arguments, error-marked tool results and failed Responses results.
Conversion methods may raise descriptive exceptions. The HTTP endpoint must
return non-2xx before emitting a successful Messages stream and preserve a
backend HTTP exception's status.

## Integrate with Gym

Register `POST /v1/messages` on `SimpleResponsesAPIModel`. Translate the request,
call that instance's existing `responses()`, and translate its reply. Existing
servers use both `responses(body)` and `responses(request, body)`; preserve the
real HTTP request and session for the latter. Subclasses must remain able to
override Messages handling. Existing `/v1/responses`, `/v1/chat/completions`
and session middleware behavior must keep working.

Expose `AnthropicConverter` from `nemo_gym.anthropic_converter` with the following
public methods, using Gym's existing Responses types. Internal design is your
choice.

| Method | Result |
|---|---|
| `anthropic_request_to_responses(anthropic_body)` | `NeMoGymResponseCreateParamsNonStreaming` |
| `responses_to_anthropic(body, model, max_tokens, thinking, thinking_budget_tokens, extra_body)` | Messages request dictionary |
| `anthropic_to_responses(anthropic_response, request_body, model)` | `NeMoGymResponse` for the original typed `request_body` |
| `responses_to_anthropic_response(response, model)` | Messages response dictionary for a typed `NeMoGymResponse` |
| `anthropic_response_to_sse(anthropic_response)` | Messages SSE stream for a complete Messages response |

For request conversion, `body` is a typed
`NeMoGymResponseCreateParamsNonStreaming`. The `model` argument selects the
backend model; `max_tokens` supplies a default when the request does not provide
`max_output_tokens`. `extra_body` supplies additional backend options. Explicitly
provided supported request fields take precedence over those options, including
empty values such as `tools=[]`. `thinking` and `thinking_budget_tokens` default
to `None` in our usage; enabling provider-specific thinking modes is not required.

Use the installed OpenAI 2.7.2 and Anthropic 0.109.2 schemas. No external API
credentials are needed. Batch APIs, hosted tools, documents/audio/video,
server-side conversation storage, native compaction, encrypted thinking/signature
conversion, RL token capture, cache-creation/reasoning-token counts and
provider-specific sampling/thinking policies are outside scope.
