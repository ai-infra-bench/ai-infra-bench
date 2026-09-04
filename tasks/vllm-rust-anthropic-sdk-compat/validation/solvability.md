# Solvability and verification basis

## Status

This task intentionally has no reference solution patch. Its compatibility
contract is defined by `anthropic==1.3.0` for the stable Messages resource,
excluding Message Batches, and by the observable behavior of the two HTTP
endpoints named in that resource.

The absence of a solution does not remove the need to validate the verifier.
The verifier uses independent positive controls for its protocol expectations
and keeps unsupported behavior in the older Python adapter separate from the
shared parity subset.

## Semantic boundary

```text
Anthropic 1.3.0 request over HTTP
-> real Rust route parsing, validation, chat rendering, engine request, and
   Anthropic response or SSE translation
-> Anthropic 1.3.0 typed SDK result or SDK exception
```

The Rust server, HTTP transport, request validation, renderer, tokenization,
engine-client boundary, response conversion, SSE framing, and SDK parser are
semantic components and run for real. Only model generation is substituted by
a deterministic engine. The substitute preserves output blocks, delta
fragmentation, ordering, finish reasons, usage, and request lifecycle.

## Why an implementation is reconstructable

The pinned source contains all required non-Anthropic components:

- the complete Rust OpenAI HTTP server, typed routes, validation, and error
  handling;
- the Rust chat layer, structured `ChatEvent` stream, renderer, tokenizer,
  reasoning parsers, tool parsers, and engine client;
- the Python Anthropic Messages adapter as a reference for the older common
  protocol subset;
- upstream tests for the Python adapter and Rust HTTP server;
- the installed Anthropic 1.3.0 SDK, whose stable request and response types
  define the newer compatibility surface.

The required change is therefore a new protocol adapter over existing engine
and chat primitives, not a new inference engine or model implementation.

The upstream three-phase design is tracked in
[vLLM issue 47753](https://github.com/vllm-project/vllm/issues/47753). Its first
phase has an open, unmerged
[request-surface and count-tokens PR](https://github.com/vllm-project/vllm/pull/52896),
which adds protocol types, request conversion, and token counting but does not
implement non-streaming or streaming Messages responses. This partial work is
later than the pinned Base and is absent from the agent image; it independently
supports the feasibility of the route and the realism of a count-tokens-only
incomplete control.

## Independent verifier controls

1. **Python parity subset.** Basic sync and async messages, string and block
   system prompts, raw responses, token counting, text streaming, tool
   definitions, and tool-use/tool-result history are sent through the official
   1.3.0 SDK to the pinned Python frontend. These cases must pass before they
   are used to score Rust behavior.
2. **SDK 1.3 fixture subset.** A verifier-only reference HTTP fixture emits
   protocol-valid non-streaming responses, SSE sequences, tool deltas, usage,
   and errors. The official SDK must parse them into the expected 1.3.0 types.
   The fixture also records the SDK's exact outgoing method, path, headers, and
   JSON body.
3. **Rust candidate path.** The same public SDK operations target the compiled
   Rust frontend backed by the deterministic engine. Assertions cover the
   SDK-visible result and the semantic request received at the engine boundary.
4. **Regression path.** Existing Rust OpenAI endpoints and health behavior run
   against the same server process.

Python behavior is not normative for cases where it disagrees with SDK 1.3.0.
IDs, timestamps, and model-generated text are checked by invariant rather than
copied byte-for-byte from the Python adapter.

## Known limitation

Without a complete correct Rust implementation, the verifier cannot be tested
against a full positive candidate. This is not hidden: publication evidence
must distinguish protocol-fixture and Python-subset positive controls from a
full Oracle pass. The task can be used under the project's verifier-first
policy, but evidence must not claim an Oracle or Harbor-Oracle result that did
not run.
