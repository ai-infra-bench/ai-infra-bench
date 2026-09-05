# Frozen instruction and behavior contract

The user selected the exact text in `instruction.md`. It is retained verbatim,
including punctuation and spacing; this document is curator-side metadata.

Semantic boundary:

```text
HTTP request carrying generation token IDs and original request context
-> native Rust render-only router, validation, real tokenizer and parsers
-> chat/completion response or chunk plus client-carried continuation state
-> independently validated client-visible result
```

Generation is outside this boundary: generated token IDs are the normal public
input of derender. No model weights, model runner, or engine is necessary. The
verifier must not replace tokenization, parsing, state continuation, or HTTP.

| Instruction requirement | Required observation | Verification design |
| --- | --- | --- |
| Both named endpoints | Both accept their public request envelopes | Real TCP requests to the compiled Rust render-only executable |
| Non-streaming responses | Text, choice indexes, model/request metadata and terminal reasons | Python shared-subset control plus independent expected values |
| Reasoning and tool parsing | Configured parser separates content, reasoning and tool arguments using real prompt context | Raw model-format token inputs, real parser configuration, multiple tools and request variations |
| Logprobs and usage | Token strings/bytes and counts are correct | Real tokenizer reference, known token IDs and logprob numbers |
| Supported chunked-processing modes | Plain-text chat and completion chunks reproduce full decoded content | Single-token and mixed partitions, Unicode, empty/terminal/usage chunks |
| Client-carried state across instances | A stream continues on a fresh server without sharing mutable process state | Alternate independently started server instances; treat state as an opaque public value |
| Render-only without weights or engine | Standalone server starts and processes all derender inputs | No engine/model mounts or engine connection; actual render CLI |
| Preserve existing APIs | Models, health and render keep working; shared serving paths retain their behavior | Native positive controls and required upstream regression checks |
| Native Rust, no Python forwarding | Derender works while no Python server or engine exists | Isolated render-only processes with no external network |

The source snapshot supplies non-streaming parsing and plain-text chunked
derender protocols in Python. As discussed before the user froze the query,
"supported chunked-processing modes" refers to that existing scope; extending
chunked reasoning/tool parsing beyond the current Python protocol is not a
hidden requirement. Non-streaming reasoning and tool parsing remain mandatory.
Unsupported combinations and invalid inputs must have explicit errors and
must not silently degrade into raw marker output.

Python is a reference, not the sole definition of correctness. The verifier
checks supplied stop/length reasons for plain output and the actual names,
arguments and content separation of parsed tools. It does not add the pending
upstream tool-finish-reason rewrite as an undisclosed requirement. Chunked
reasoning/tool parsing and chunked logprobs are not part of the supported
chunked scope at this Base. The Oracle's bounded window and the alternative's
full-history replay are both accepted; state representation and growth strategy
are not graded.

The frozen matrix contains 49 HTTP cases: 24 general response/validation/API
cases, 14 continuation cases, and 11 parsing/logprob cases. An additional 673
existing Rust server/chat cases guard shared API behavior. No task behavior test
imports an Oracle symbol. The existing crate suites may grow without failing
the minimum baseline-count check.

Status: validated against Python, native Rust Oracle, four negative controls,
and a different correct state representation; see `e2e-evidence.json`.
