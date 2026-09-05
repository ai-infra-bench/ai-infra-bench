# Task review report

## Decision

Ready for staged use under the repository's `verifier_only` policy. The review
found no unresolved P0 or P1 issue in the instruction, environment, Base
boundary, verifier integrity, or declared controls.

This decision does not claim an Oracle pass. No complete correct Rust
implementation was available or executed. The first conforming implementation
must be treated as an additional verifier-validation event rather than as
evidence that already exists.

## Gate 1: authentic task

Pass.

- The requested endpoints and Rust parity work are tracked in vLLM's public
  Anthropic Rust frontend RFC, issue 47753, and the broader Rust parity roadmap,
  issue 44280.
- The pinned Base predates the RFC and the later partial implementation. It has
  a working Rust OpenAI frontend and Python Anthropic adapter but no Rust
  Anthropic route.
- The instruction states the observable compatibility target, the SDK version,
  the two in-scope interfaces, and the hosted-tool boundary. It does not name a
  proposed Rust module, helper, or patch structure.
- The installed SDK and the older Python adapter are intentional protocol
  references available to the solver. The later Rust pull request and its Git
  objects are absent from the image.

## Gate 2: environment

Pass.

- The image contains vLLM at
  `e196268bade5291c3fd80906bf9cd8c64851b21b`, a required and executable
  `vllm-rs`, Rust 1.95 with rustfmt and clippy, protoc 34.2, and an exact Python
  dependency lock containing `anthropic==1.3.0`.
- The dependency cutoff is September 1, 2026, matching the SDK release date;
  the source Base remains July 1, 2026.
- Runtime model assets are restricted to the pinned Qwen configuration,
  tokenizer, tokenizer configuration, and chat template. No model tensor is
  included.
- `/tests`, `/solution`, and `/validation` are absent from the agent image.
  Remotes, tags, reflogs, unreachable objects, the later partial PR commit, and
  test sentinel strings are absent.
- The task has a 36,000-second agent budget and network-disabled runtime.
- A warm-cache rebuild using the canonical no-provenance build mode reproduced
  image ID
  `sha256:535bb97cac5f23043e7874dfde5037c1fee6d76d180d1da2e6e8217ca161d125`.

The Dockerfile is a task-scoped hardened expansion of the shared vLLM template.
The differences pin the system snapshot and download hashes, require packaging
the Rust frontend, install protoc before the Rust build, retain the Rust
development tools, vendor Cargo dependencies for offline use, and embed the
resolved Python lock.

## Gate 3: verifier

Pass within the documented no-solution boundary.

The rewarded path contains 106 pytest cases: 35 official-SDK protocol controls
and 71 candidate Rust HTTP cases. Ten additional checks execute the official
SDK against the pinned Python vLLM server on the adapter's measured compatible
subset. Reward 1 requires the exact case counts with no failure, error, or skip,
and all ten Python checks.

The expanded SDK controls cover every explicit HTTP status mapping used by the
Messages client, plus ping filtering, stream error events, terminal stream
reasons, Unicode and escaped tool JSON fragmentation, cache and service-tier
usage fields, citations, and the SDK 1.3 hosted web, code, editor, tool-search,
and container-upload response unions.

The Rust cases start the real Axum router over TCP and exercise request parsing,
validation, chat rendering, tokenization, the engine-client boundary, output
processing, SSE framing, and official SDK parsing. Only generated model output
is deterministic. Tests assert public SDK results and semantic engine input,
not candidate file names or helper names.

Five frozen Base runs were identical: the SDK fixture passed 35/35, the Python
control passed 10/10, and the Rust matrix passed the existing OpenAI/health
regression while all 70 Anthropic cases failed. A direct
`VLLM_USE_RUST_FRONTEND=1 vllm serve` run independently returned 200 for health
and OpenAI chat and 404 for both missing Anthropic paths.

The two declared partial controls both received reward 0 and passed only the
existing OpenAI/health regression:

- fixed JSON endpoints passed one Rust case and failed 70;
- a fixed count-tokens-only implementation passed one Rust case and failed 70
  because it performed no observable tokenizer work.

Harbor 0.22.0 reproduced reward 0 for Base and both controls with one completed,
zero-error trial per case. The SDK fixture and Python control passed in every
manual and Harbor execution.

## Semantic boundary

```text
anthropic 1.3.0 SDK
-> real TCP HTTP or SSE
-> Rust build_router and endpoint validation
-> ChatRequest rendering and tokenization
-> real engine-client request boundary
-> deterministic model output only
-> real Rust output processors and Anthropic event translation
-> official SDK typed object, stream accumulator, or exception
```

The independent HTTP/SSE fixture is a positive control for SDK 1.3.0 wire
semantics, not a replacement for the Rust server. The Python frontend is a
positive control only for the subset it actually accepts. Neither is described
as a complete implementation Oracle.

## Remaining limitation

The verifier has not awarded reward 1 to a complete implementation. This is the
explicit limitation of `verifier_only` publication: protocol expectations,
client behavior, the real Base boundary, collection integrity, and incomplete
solution rejection are measured, while full positive-candidate validation is
deferred until such an implementation exists.
