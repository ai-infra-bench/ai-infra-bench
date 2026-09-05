# Anthropic 1.3 Messages verifier contract

| Group | Behavior classes | Positive-control source | Candidate observation |
| --- | --- | --- | --- |
| Client modes | sync, async, raw response, streaming response, `create`, `stream`, `parse`, `count_tokens` | SDK fixture; Python where supported | SDK type, raw HTTP metadata, lifecycle |
| Conversation input | single and multi-turn, string and block system prompts, inline system, text, image, document, search result, thinking, redacted thinking, tool use and result | Python common subset; SDK 1.3 request capture for newer blocks | accepted request and semantic rendered/engine input |
| Parameters | max tokens, stop strings, metadata, cache control, service tier, inference geo, container, user-profile header, thinking, structured output | SDK 1.3 request capture | validation result and engine/chat options |
| Tool choice | auto, any, named, none, strict tools, disabled parallel use | Python common subset; SDK request capture | selected chat tool mode and public response |
| Tool output | one tool, mixed text and tool, parallel tools, repeated names, fragmented JSON, multiple tool results | SDK SSE fixture; deterministic engine | ordered blocks, unique IDs, reconstructed JSON |
| Non-stream response | text, thinking then text, citations, hosted-tool result unions, parallel tools, empty output, primary engine finish reasons, SDK-only response reasons, usage details | SDK 1.3 fixture | typed `Message` and raw envelope |
| SSE | named events, ignored ping, stream errors, block indexes, text/thinking/signature/tool deltas, terminal reasons and usage, Unicode/escaped JSON, and multiple fragmentation schedules | SDK 1.3 fixture | exact event invariants, typed exception, and final accumulated message |
| Token counting | simple, system, long history, tools, and structured output | Python where supported; independent HF tokenizer | count equals actual generation prompt-token length; count requests submit no generation and may reuse cached tokenization |
| Errors and headers | malformed JSON, missing/invalid fields, every explicit SDK HTTP status mapping used by Messages, stream errors, context-limit response parsing, request ID, and both auth styles | SDK exception parsing fixture | status, Anthropic error envelope, request ID |
| Isolation | repeated calls, concurrent sync and async requests, unique IDs, and no cross-request block state | deterministic engine scripts | per-request results and cleanup |
| Regression | OpenAI chat/completions/models and health | pinned Base expectations | unchanged public response behavior |
| Real backend qualification | Unicode, multi-turn system history, tool history, tokenization, streaming decode, JSON constraints, and both stop strings | existing Rust OpenAI/tokenize routes; independent Python Jinja/HF tokenizers and real guidance grammar compiler | actual Qwen prompt text/token IDs; content reaches template; constraints reach and execute in the grammar matcher |

Parameterized values and unpublished combinations vary within these disclosed
behavior classes. Reward never depends on Rust module names, helper names,
private fields, source layout, or similarity to the Python adapter.

The frozen verifier collects 115 cases: 35 SDK protocol-fixture controls and 80
Rust HTTP cases. Of those 80, seven qualify the production Qwen backend through
existing routes, one covers the original OpenAI/health regression, and 72 require
Anthropic behavior. The separate Python frontend control executes ten real-server
checks for the older adapter's compatible subset.

The Rust harness calls the production `load_model_backends` with the immutable
Qwen3.6 assets already in the image. It delegates rendering, tokenization,
sampling defaults, and output processing to those backends. The observation
wrapper writes the already-rendered prompt and semantic request to a separate
capture file; serialized requests are never substituted for the model prompt.
Generated strings are encoded with the same real tokenizer before deterministic
token chunks enter the engine-client output boundary. Chunk sizes count tokens,
not bytes or Unicode characters. The text-only backend is configured with
`enable_thinking=false` and `preserve_thinking=true`; requests can exercise the
normal reasoning option overrides. Model weights, GPU execution, and positive
multimodal preprocessing remain outside this reduced serving boundary.

Eight tool-history inputs now include their preceding user query because the
actual Qwen template requires one. Stop strings are checked by observing that
either requested marker terminates the real decoded output, rather than by
requiring these sampling options to appear in rendered prose. Effort is checked
in effective renderer options. JSON constraints are checked at the stable engine
request boundary and executed with the pinned guidance matcher against valid,
wrong-type, and missing-required-field examples; a pre-scripted valid response
alone cannot satisfy the check.

The 35 fixture controls test SDK parsing/serialization, not candidate behavior.
In particular, all HTTP error mappings, citations, hosted-tool response unions,
and ping filtering in that fixture must not be reported as full Rust coverage.
The separate Python audit is documented in `python-compatibility.md`; it does not
change reward and does not supply a full Oracle.
