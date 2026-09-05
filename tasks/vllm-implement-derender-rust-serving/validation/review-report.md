# Task review

Retain the task. The frozen user statement, CPU environment and behavioral
verifier pass the three review gates for the supported scope below. No
blocking finding remains after qualification.

## Statement

The instruction is the user's exact English query, including punctuation and
spacing. It requests both Rust derender endpoints, non-streaming parsing and
metadata, supported chunked processing with client-carried state, engine-free
render-only operation, and preservation of existing APIs. This is a realistic
token-in/token-out serving workflow; it does not claim to reproduce a specific
historical incident.

## Environment and semantic boundary

The immutable vLLM Base is `e473e9036f979d546830aece9855027049faf0ba`.
The image contains its Python protocol/reference, the working native Rust
render-only executable, pinned offline Cargo/Python dependencies and Qwen
configuration/tokenizer/template metadata. It contains no model weights.

```text
real HTTP request with generated token IDs and original request context
-> production Rust render CLI/router, tokenizer, parser and response assembly
-> response or chunk plus client-carried state
-> exact text/metadata checks and continuation on an independent process
```

Generated token IDs are the normal interface input. Model computation and an
engine are not part of this semantic boundary. The real native tokenizer,
parsers, request/response transport and independent process state run without
substitution. Separate server/chat crate regressions exercise the existing
shared serving code with upstream engine fixtures.

A fresh Base container without task mounts started the render CLI and returned
200 for health, models and chat rendering, and 404 for both missing derender
endpoints. Git/PR-object isolation, normal import paths, resource hashes and
dependency compatibility passed. The cache-only rebuild reproduced the same
image ID. No future Rust derender source enters the Dockerfile or image.

## Verifier and reference independence

The 49 HTTP cases cover both response families, Unicode and escaped text,
multiple prompts/choices, exact usage, logprob token/byte reconstruction,
reasoning with real prompt context, tools and mixed outputs, invalid inputs,
special-token options, concurrent calls and client-carried continuation.

The independent challenge crosses special tokens and a split emoji. Another
test terminates the original server inside a partially decoded character,
then continues on a fresh process. The verifier treats returned state as an
opaque JSON object rather than requiring the Oracle's private representation.

The Oracle uses a bounded decode window; the correct alternative replays full
token history through the production incremental decoder. Both receive 1.
Four complete, compilable mutations omit continuation state, parsing,
logprobs or prompt usage and receive 0 through their planned behavior defects;
all retain passing existing API regressions.

Final measured outcomes:

- Python reference: 49/49 HTTP cases pass.
- Base: 9/49 HTTP cases pass, 40 fail at missing functionality; reward 0 in
  five rounds with identical failure names, no errors or skips.
- Oracle: 49/49 HTTP cases and 673 server/chat regressions pass, reward 1 in
  five final rounds.
- Correct alternative: complete verifier passes, reward 1.
- Four incomplete controls: rewards 0; 9, 8, 3 and 6 HTTP failures respectively.
- Fresh Harbor Oracle: one completed trial, zero framework errors, reward 1.

## Limitations and qualification notes

Supported chunked processing means the Base's plain-text chat/completion
protocol. Streaming reasoning/tool parsing and streaming logprobs are not
claimed. HTTP cases use the supplied Qwen vocabulary/template and explicitly
configured Hermes/Qwen3 parsers; this is not an all-model benchmark. No GPU
computation, throughput, or transfer behavior is claimed.

A broad diagnostic ran vllm-text in addition to the rewarded crates. Its
Qwen3-0.6B download-dependent test failed offline and one explicitly
network-dependent test was ignored; neither is part of the scored suites.
The scored server/chat suites have no ignored or failed tests.

One provisional stability attempt after restoring old-timestamp source files
reused a compiled discard-state mutation through Cargo's timestamp cache. The
source hashes were correct but the build log still showed the mutation's
unused-state warning. That qualification-container restoration was corrected
by touching the restored files and rebuilding. The fresh Harbor trial and all
five subsequent Oracle rounds passed. The failed restoration attempt remains
in the external raw logs and is not counted as a successful stability round.

No tests, Oracle implementation names, or curator reproducer are made available
to the evaluated agent. Final hashes, prepared-task checksum semantics and raw
log locations are recorded in `e2e-evidence.json`.
