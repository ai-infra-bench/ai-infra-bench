# Task review report

Retain the task under the repository's existing `verifier_only` policy and the
user's explicit selective-coverage decision. The original broad Messages and
token-counting instruction remains. Scoring covers the selected successful
serving paths; it does not establish full SDK compatibility or acceptance of
all hosted-tool types. No complete Rust solution or Oracle has been executed.

## Task and environment

The task asks for Rust frontend parity through existing vLLM serving primitives,
consistent with the public Anthropic Rust RFC and Rust parity roadmap. The
pinned July 1 Base has a working Rust OpenAI frontend but no Rust Anthropic routes.
The solver has its Rust routing/chat/engine primitives, the older Python adapter,
upstream tests and the installed official `anthropic==1.3.0` SDK.

The canonical image remains
`sha256:535bb97cac5f23043e7874dfde5037c1fee6d76d180d1da2e6e8217ca161d125`,
with Base `e196268bade5291c3fd80906bf9cd8c64851b21b`. The image retains the Rust
frontend/toolchain, offline dependencies and immutable Qwen3.6 configuration,
chat template and tokenizer. It contains no model tensors or task tests,
solution, validation artifacts or recoverable future Git source. The agent has
a 36,000-second budget and network-disabled runtime. Environment inputs did not
change; current isolation checks and asset hashes are in the evidence.

The latest Python comparison uses a separate image built from a complete newer
upstream archive. Neither that source nor its adapter enters the canonical image.

## Scored boundary and coverage

```text
Official Anthropic SDK -> TCP HTTP/SSE -> real Rust router
-> production Qwen Jinja renderer/tokenizer -> real engine-client IPC
-> deterministic Qwen token outputs -> real output processing/conversion
-> official SDK objects and stream accumulation
```

Rendering, tokenization, output parsers, transport and request lifecycle run for
real. Deterministic generation replaces model computation. The harness captures
actual rendered prompts and engine request IDs/constraints; JSON serialization
never substitutes for the model prompt. Count checks compare with actual prompt
IDs and independent HF tokenization while allowing caches. Schema constraints
execute in the real guidance matcher, including invalid JSON examples.

The expanded suite collects 86 pytest cases: 21 SDK fixture controls and 65 server
cases. The latter comprise 56 Anthropic behavior cases, eight native Qwen backend
controls and one existing OpenAI/health regression. Ten additional Python
controls run a real CPU model with dummy weights. Reward 1 requires exact counts,
no failures/errors/skips and all ten Python controls.

The retained cases cover sync/async/raw/streaming modes, text/system/multi-turn
history, consecutive same-role turns, ordered multiple text/system blocks,
ordinary custom tools and multiple results, tool choice and parallel tools,
fragmented tool JSON, structured output, real token counting with the SDK's
thinking/output/tool-choice/cache-control parameters, stops, optional cache usage, empty output
and concurrent request isolation. A native OpenAI reasoning control explicitly
enables thinking in the real template.

At the user's request, candidate tests omit unsupported search/hosted/reference
content and tool/cloud options, thinking signatures, engine-error propagation,
error-envelope format, authentication and media rejection. Fixture-only protocol
or error cases do not establish candidate coverage for those omissions. The
user retained the broader instruction with this coverage gap explicitly known.

## Validation and evidence

The latest Python reference `32601ef7a1ce8aaa6d777778435ec499248906fb` passes
86/86 cases and 10/10 real CPU controls. The nine added cases also pass against
all eight retained Rust candidates and therefore do not change their prior reward
outcomes. The earlier ten Harbor trials complete without framework errors: five
Base runs consistently pass nine server cases
and fail the 47 absent-route cases. Static/count-only controls produce 9/47,
byte tokenization 1/55, JSON rendering 5/51, and dropped constraints 8/48.
The latter mutations fail eight, four and one native checks respectively.

The pre-expansion Harbor results, hashes and exact input/trial identities are
recorded in `e2e-evidence.json`. The expanded suite is compared without changed
assertions against the latest pinned Python application in
`latest_python/results.json`.
That adapter replaces EngineCore generation/transport; real frontend, template,
tokenizer, parsers and HTTP/SSE execute. Its separate CPU controls use real dummy
weights. A Python pass is reference evidence, not a Rust solution Oracle.

Five Base repetitions and five deliberately incomplete controls exercise the
verifier through Harbor. Base must fail at the missing Anthropic paths. Static
responses and fixed counts must remain insufficient. Byte-tokenization,
JSON-rendering and dropped-constraint mutations must also fail native checks
that pass on unmodified Base, so their rejection does not depend solely on the
missing Anthropic routes.

Version 0.0.2 also declares a Harbor verifier collector. It records the tracked
binary diff, Git status, untracked path list, and a compressed untracked-file
archive before verifier injection, so failed and successful attempts retain the
exact candidate implementation for later review.

The original 115-case audit, 20 latest-Python failures and older Python component
probes are preserved under `history/f4163bc/`. They explain how coverage was
selected and must not be reported as current failures or current full coverage.

The repository validator supports `verifier_only`. The newer generic skill audit
script still unconditionally requires Oracle files and cannot directly validate
this authorized mode; exact executable hashes, manifest/control identities,
collection integrity, image isolation and actual Harbor results are checked
separately. No Oracle result is synthesized to satisfy that script.

No complete correct Rust implementation or semantically different complete
alternative has earned reward 1. Full positive-candidate validation remains
unmeasured, and a full score would still cover only the selected test subset.
