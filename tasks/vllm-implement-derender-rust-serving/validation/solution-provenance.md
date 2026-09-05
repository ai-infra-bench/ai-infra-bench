# Reference implementation provenance

The provisional Rust reference is based on the Apache-2.0 implementation in
vLLM PR #53419, head `11e04db829db6280be1a0a24c5b0ab1980a1528b`, whose stacked
history includes PR #53223 (detokenization) and PR #53418 (parsing). The original
PR base is `680e2177e473ed8dfaa9773f7ead185b369cab46`.

Only Rust source changes were used; the proposed route-test additions and GPU
E2E files are not the task's verifier. Existing upstream source at task Base is
retained. The route-registration change is rebased onto the task's current
`e473e9036f979d546830aece9855027049faf0ba` source. Independent task HTTP tests
exercise the production render executable and do not import Oracle symbols.

The proposal is not presumed correct. Any qualification corrections and actual
results will be recorded here before publication. The proposed patch and all
curator files remain outside the agent image.

Sources:

- https://github.com/vllm-project/vllm/pull/53223
- https://github.com/vllm-project/vllm/pull/53418
- https://github.com/vllm-project/vllm/pull/53419
- https://github.com/vllm-project/vllm/issues/42729
- https://github.com/vllm-project/vllm/issues/47161

Qualification changes adapt the proposal to the Base's `DecodedTextEvent`
representation (`decoded`, `sampled`, boxed terminal metadata), preserve actual
decoder token attributions and prompt context, and handle the newer usage
detail type during deserialization and response construction. The benchmark's
reference patch contains 18 production source files and excludes the upstream
route-test additions and tokenizer test-utility changes.

The Oracle passed all 49 HTTP cases and 673 server/chat regression cases,
including a fresh Harbor trial. Five final stability rounds passed. The
full-history/native-decoder alternative also passed the same complete verifier.

Status: qualified. Exact final patch and result hashes are in `e2e-evidence.json`.
