# Anthropic 1.3 Messages verifier contract

| Group | Behavior classes | Positive-control source | Candidate observation |
| --- | --- | --- | --- |
| Client modes | sync, async, raw response, streaming response, `create`, `stream`, `parse`, `count_tokens` | SDK fixture; Python where supported | SDK type, raw HTTP metadata, lifecycle |
| Conversation input | single and multi-turn, string and block system prompts, inline system, text, image, document, search result, thinking, redacted thinking, tool use and result | Python common subset; SDK 1.3 request capture for newer blocks | accepted request and semantic rendered/engine input |
| Parameters | max tokens, stop strings, metadata, cache control, service tier, inference geo, container, user-profile header, thinking, structured output | SDK 1.3 request capture | validation result and engine/chat options |
| Tool choice | auto, any, named, none, strict tools, disabled parallel use | Python common subset; SDK request capture | selected chat tool mode and public response |
| Tool output | one tool, mixed text and tool, parallel tools, repeated names, fragmented JSON, multiple tool results | SDK SSE fixture; deterministic engine | ordered blocks, unique IDs, reconstructed JSON |
| Non-stream response | text, thinking then text, parallel tools, empty output, primary engine finish reasons, SDK-only response reasons, usage details | SDK 1.3 fixture | typed `Message` and raw envelope |
| SSE | named events, block indexes, text/thinking/signature/tool deltas, terminal usage, and multiple fragmentation schedules | SDK 1.3 fixture | exact event invariants and final accumulated message |
| Token counting | simple, system, long history, tools, and structured output | Python where supported; tokenizer invariants | exact count and absence of generation |
| Errors and headers | malformed JSON, missing/invalid fields, context-limit response parsing, and both auth styles | SDK exception parsing fixture | status, Anthropic error envelope, request ID |
| Isolation | repeated calls, concurrent sync and async requests, unique IDs, and no cross-request block state | deterministic engine scripts | per-request results and cleanup |
| Regression | OpenAI chat/completions/models and health | pinned Base expectations | unchanged public response behavior |

Parameterized values and unpublished combinations vary within these disclosed
behavior classes. Reward never depends on Rust module names, helper names,
private fields, source layout, or similarity to the Python adapter.

The frozen verifier collects 86 cases: 17 SDK protocol-fixture controls and 69
candidate Rust HTTP cases. The separate Python frontend control executes ten
real-server checks for the older adapter's compatible subset.
