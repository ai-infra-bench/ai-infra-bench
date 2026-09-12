# Independent fresh challenge -- vllm-async-pp-token-handoff

Curator-side verification harness. **Not** the agent verifier (`tests/`), **not**
referenced by `instruction.md`, **not** mounted into the agent image or any image
history layer. It exists only under `validation/challenge/` and is invoked directly
during dynamic validation (Phase D).

## Production API exercised
`GPUModelRunner.execute_model -> sample_tokens over a real 2-rank NCCL PP group`

This is the same production entry point the agent verifier uses, so a correct
solution that passes `tests/` must also pass this challenge. The challenge is
**not** a copy of the verifier: it re-derives the invariant on independently
chosen inputs.

## Independent invariant
Sampled tokens cross the PP boundary via a GPU (NCCL) collective with no object/CPU collective and no blocking GPU->CPU transfer or CUDA host wait; the receiver rebuilds prev_sampled_token_ids on-GPU, maps only kept requests to their original index, and appends a -1 placeholder to kept requests while leaving discarded ones unchanged.

The sender must finish production bookkeeping and return its real async output.
The receiver executes production cached-state update and prepares next-step GPU
input IDs, including a reordered retained-request batch. Only deterministic model
and sampler inputs are substituted; reaching a broadcast is not completion.

## Fresh inputs (not drawn from the verifier or `ci-cases.json`)
5 requests, interleaved discards at positions 1 and 3, reordered req_ids, all non-empty priors -- distinct from the basic/reordered/integrated scenarios (which only discard a trailing request).

## How Phase D runs it
```
torchrun --nproc_per_node=2 validation/challenge/challenge_token_handoff.py  (2-GPU NCCL; Phase D only)
```
Emits machine-checkable JSON and a final `CHALLENGE_TOKEN_HANDOFF=PASS|FAIL` line; exits
non-zero on failure.

Expected outcomes in Phase D:
- **Oracle**: `CHALLENGE_TOKEN_HANDOFF=PASS`.
- **Semantically-different correct alternative** (`alternate-inline-nccl.patch`, apply_after=base, expected_reward=1): `CHALLENGE_TOKEN_HANDOFF=PASS`.
  Confirms the challenge scores the behavioral contract, not one implementation.
- **Base / incorrect** (`cpu-sync-object-collective.patch (expected_reward=0)`): `CHALLENGE_TOKEN_HANDOFF=FAIL`.

Current measured outcomes are recorded in `../e2e-evidence.json`; expected
outcomes above are the contract, not a substitute for actual run records.

## Provenance guarantee
This file is under `validation/`, which is never copied into the environment
image (see `environment/Dockerfile`). Phase C verifies via `docker history` and a
final-filesystem scan that no challenge, verifier, solution, or reward logic
leaked into the image.

The wrapper also runs a seven-request case with new token values, request order,
mixed histories and interleaved discards. A shared observer measures real device
copies and runtime waits; expected request/output states are derived in this
challenge. Oracle and correct alternatives must pass both cases. Standalone
D2H and host-wait controls must fail through a typed behavioral reason.
