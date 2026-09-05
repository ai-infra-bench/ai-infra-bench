# Anthropic Messages verifier coverage

The user retained the original broad Messages/count_tokens compatibility
instruction and explicitly selected a smaller scoring scope. A passing score
establishes only the measured subset below, not full SDK compatibility.

| Group | Covered behavior | Observation |
| --- | --- | --- |
| SDK modes | sync, async, raw/streaming response, create, stream helper, parse, count | official SDK objects, event accumulation and request capture; ordered text blocks and multiple message_delta updates are accepted |
| Conversation | text, system string/blocks, inline system, multi-turn, assistant prefill, thinking/redacted history, ordinary custom tool use/results | successful request and actual rendered prompt; redacted history may be ignored |
| Tools | name/description/schema, choice auto/any/named/none, parallel setting, ordered IDs and JSON arguments | real prompt, non-stream and fragmented-stream output; no internal flag requirement for tool_choice=none; named and singleton-required selections are equivalent |
| Generation options | token limit, stop markers, effort, JSON schema | received engine limits, token-bounded output/usage/termination, effective renderer options, and executable schema constraints |
| Count/usage | full prompt including system/tools, repeated generation-free counts, output/cache usage | actual engine IDs and independent HF tokenizer; cached tokenization allowed |
| Lifecycle | empty output, stops, Unicode/JSON fragmentation, repeated/concurrent requests | no fabricated content, correct terminal events, no cross-request state |
| Existing API/backend | health/models/chat/completions/tokenize, real template/tokenizer, system/tool history, Unicode streaming, enabled reasoning, schema constraints, stops | existing Rust routes with independent prompt/ID/grammar observations |

The suite collects 93 pytest cases: 21 independent SDK fixture controls and
72 server cases. The server cases comprise 53 Anthropic cases and 19 existing
API/backend controls (18 in `test_real_qwen_backend.py`, one in the SDK
matrix). Ten additional Python checks execute a real CPU model with dummy
weights. Reward 1 requires the exact counts, all passing, with zero errors or skips.

At the user's request, candidate scoring omits search-result, server/hosted-tool
and tool-reference content, input examples and unsupported tool/cloud options,
request-side adaptive thinking/budgets, Anthropic thinking signatures, engine
error propagation, error-envelope format, API-key authentication, and media
processing/rejection. These are unverified portions of the stated objective;
the user-facing instruction has not been narrowed. Ordinary tool-result string,
text-block, error-result and multiple-result histories remain covered. A tool
result marked is_error is conversation data, distinct from an HTTP/server error.

The 21 SDK fixtures independently qualify client parsing/serialization; their
protocol-error or thinking fixtures never inspect candidate server behavior.
They must not be counted as candidate coverage for omitted requirements.

The Rust harness runs real TCP HTTP/SSE, production Qwen3.6 Jinja rendering and
tokenization, engine-client IPC, output processors and the official SDK. Only
generated engine output is scripted, using actual Qwen token IDs. The native
OpenAI reasoning regression explicitly enables thinking; other cases default to
false. `preserve_thinking=true` preserves compatible history. Weights, GPU
computation and positive multimodal preprocessing are outside the measured path.

Prompt captures observe the real rendered prompt. Count checks permit caching.
Schema checks execute captured constraints on valid and invalid examples; a
scripted schema-valid reply alone is insufficient. Six SDK generation-limit cases cover limits 1/7/19 in stream/nonstream modes.
Eight native cases cover chat/completions and completions, both response modes,
and two nondefault limit/temperature/top_p/top_k profiles. SDK 1.3.0 does not
directly expose the latter three parameters; they are existing OpenAI contracts.
Two native tool-none cases protect direct text in both response modes.
The deterministic engines truncate at the received max_tokens and report length.
The two parallel-tool success cases request 128 tokens for their 66-token script.

Mutation controls must fail
native checks that pass on Base, independently of its absent Anthropic routes.

The current full-suite Python comparison is in `latest_python/`. Earlier broader
measurements, including the original 20-failure analysis, are archived under
`history/f4163bc/`. No complete Rust implementation or full Oracle is available.
