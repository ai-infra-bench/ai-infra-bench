# Pinned Python Anthropic compatibility measurements

The reference is vLLM `e196268bade5291c3fd80906bf9cd8c64851b21b` with the official
`anthropic==1.3.0` client. A failure identifies a mismatch with the tested task
behavior; it does not establish that the behavior was introduced in SDK 1.3.0.
`python-case-map.json` maps every one of the 115 final verifier cases to the
available Python evidence, explicitly distinguishing equivalent request probes,
partial/component evidence, unmeasured cases, and non-Python controls.

## Real Python HTTP audit: 29 passed, 15 incompatible

`run_python_compatibility.py` starts the pinned Python server with a real CPU
runner and dummy weights, the frozen Qwen3.6 tokenizer/template, and an observer
around `AsyncLLM.generate` that records but does not modify inputs or outputs.
All 41 request-matrix cases have equivalent Python probes, plus three client-mode
probes. Request generation uses one output token because generated prose is not
part of these assertions. Tool history has a preceding user query, matching the
revised Rust inputs. Full per-case observations are in
`python-compatibility.json`.

| Cases | Result | What was measured |
| --- | --- | --- |
| String/block system, leading/mid/multiple inline system, assistant prefill, thinking/text history, redacted thinking, tool-use history, string/text/error tool results, long history | passed | Real HTTP success and preservation of the required content in the actual rendered engine prompt |
| Top cache control, container, service tier/inference geo, metadata/profile | passed for acceptance | Ordinary message still reaches the engine; this does **not** establish cloud-service execution or semantics for fields the local adapter ignores |
| Adaptive thinking plus `output_config.effort=high` | passed for the tested effort mapping | Request accepted and Python conversion preserves `reasoning_effort=high`; this does **not** establish adaptive-thinking budget/display support |
| JSON-schema output configuration | passed | Requested schema reaches Python generation parameters; generated schema compliance is not scored by this request probe |
| Multiple stop sequences | passed for request acceptance | The independent converter probe below finds that matched-stop response metadata is lost |
| Six count-token variants: plain, system, tools, thinking, structured output, user profile | passed | No generation from count requests; repeated counts stable; count equals actual generation prompt-token length. Acceptance of extra fields does not prove those fields affect rendering |
| Sync/raw/streaming-response access, text SSE lifecycle, async access | passed | Official SDK accepts the real server response and basic stream lifecycle |
| `tool_result` containing `tool_reference` | incompatible | Server returns 500: the real Qwen template rejects the converted content item |
| `search_result`, `server_tool_use`, web-search/fetch/code/bash/editor/tool-search/container-upload history groups | incompatible | Pinned Python content-block schema rejects these request types |
| Custom-tool full-field case | incompatible | The `input_examples` sentinel never reaches the real rendered prompt |
| Missing `max_tokens`, invalid role, unknown block | incompatible | Server rejects the request, but uses an OpenAI-style error envelope instead of the required Anthropic envelope |
| Empty messages | incompatible | Server returns 500 from rendering instead of the required 400 |
| Image inputs on the text-only model | incompatible | Server returns 500 instead of the required Anthropic 400 |
| Document input | incompatible | Unsupported block is rejected with an OpenAI-style envelope |

The 29 successes consist of 20 request variants, six token-counting variants,
and three client-mode probes. The 15 mismatches consist of eight request
variants, four invalid-request cases, and three unsupported-media cases.

## Python response-converter audit: 8 passed, 2 incompatible

`run_python_output_compatibility.py` executes the production Python Anthropic
response converters on reconstructed OpenAI responses/SSE, serves their outputs
over real TCP, and parses them with the official SDK. This measures the
converter stage, not the entire Python engine/tool parser path. Results are in
`python-output-compatibility.json`.

| Cases | Result |
| --- | --- |
| Empty non-stream response; thinking then text; combined text/tool; parallel tools; max-token non-stream finish | passed, including cache-read usage propagation |
| Text streaming with required start fields; empty stream; max-token stream finish | passed |
| Matched stop string, both non-stream and stream | incompatible: maps to `end_turn` and loses `stop_sequence` |

This audit exposed an extra restriction in the original verifier: it required
one empty text block for an empty stream, even though the instruction does not
require that representation and the SDK accepts `content=[]`. The verifier now
accepts either empty representation and checks no generated content, normal
termination, the stop reason, and zero output tokens. Missing error envelopes
and stop metadata are ordinary protocol/adapter defects; they
are not evidence of a new SDK feature. The stop-metadata limitation was already
called out in the [Rust RFC](https://github.com/vllm-project/vllm/issues/47753).

## What remains unvalidated

The original ten Python server controls still run as a separate reward gate.
Neither those ten controls nor the diagnostic probes execute all candidate Rust
assertions against Python. Deterministic parser fragmentation, concurrent output
identity, engine-error injection, configured API-key combinations, and the SDK
fixture-only extended response unions do not acquire a Python E2E pass from
these results. No complete Rust implementation or conforming alternative has
earned reward 1.

Verifier confidence comes from independent SDK controls, production-backend
positive controls, meaningful Base failures, and mutations rejected by checks
that pass on unmodified Base. Full positive-candidate validation remains a
separate required event when a conforming Rust implementation becomes available.

## Reproduce

Mount the task's `tests/` at `/tests`, `validation/` at `/validation`, and an empty
output directory at `/logs/verifier` in the canonical image with network disabled.
Run:

```sh
PYTHONPATH=/tests python /validation/run_python_compatibility.py --output /logs/verifier/python-compatibility.json
PYTHONPATH=/tests python /validation/run_python_output_compatibility.py --output /logs/verifier/python-output-compatibility.json
```

The first command saves raw server and engine-observation logs next to the JSON.
Those logs are diagnostic artifacts and do not enter the agent image.
