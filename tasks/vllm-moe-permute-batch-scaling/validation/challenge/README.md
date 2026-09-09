# Independent fresh challenge -- vllm-moe-permute-batch-scaling

Curator-side verification harness. **Not** the agent verifier (`tests/`), **not**
referenced by `instruction.md`, **not** mounted into the agent image or any image
history layer. It exists only under `validation/challenge/` and is invoked directly
during dynamic validation (Phase D).

## Production API exercised
`torch.ops._moe_C.moe_permute (native)`

This is the same production entry point the agent verifier uses, so a correct
solution that passes `tests/` must also pass this challenge. The challenge is
**not** a copy of the verifier: it re-derives the invariant on independently
chosen inputs.

## Independent invariant
`moe_permute` produces a genuine bijection over every `(token, top-k)` routed
slot: each slot lands inside its routed expert's aligned offset window, the
`inv_permuted_idx`/`permuted_idx` maps round-trip exactly, the permuted payload
is a byte-exact gather of the source rows, and the expert-id fill and `-1`
sentinel tail are correct. The mapping follows the routing map independent of
batch size (no batch-dependent shortcut), and the aligned 4096-token latency and 4096/512 ratio meet the published bounds. The challenge calls `moe_permute` only; it does not call
`moe_unpermute`.

## Independently chosen inputs
Correctness uses FRESH_TOKENS = (7, 63, 129, 257, 1000, 3000) with routing pattern 23*token+11*rank+3. Performance uses the published 512/4096 sizes with independent routing and the same 20 warmups / 50 timed iterations / 5 repeats protocol.

## How Phase D runs it
```
python3 validation/challenge/challenge_moe_permute.py  (GPU/CUDA native op; Phase D)
```
Emits machine-checkable JSON and a final `CHALLENGE_MOE_PERMUTE=PASS|FAIL` line; exits
non-zero on failure.

Expected outcomes in Phase D:
- **Oracle**: `CHALLENGE_MOE_PERMUTE=PASS`.
- **Semantically-different correct alternative** (`alternate-cuda-scaling.patch`, apply_after=base, expected_reward=1): `CHALLENGE_MOE_PERMUTE=PASS`.
  Confirms the challenge scores the behavioral contract, not one implementation.
- **Base / incorrect** (`diagnosis-only-linear-scan.patch (expected_reward=0)`): `CHALLENGE_MOE_PERMUTE=FAIL`.
- The timed-size specialization patch is retained under `validation/diagnostics/`.
  Its behavior outside the published timing cases is diagnostic. It is not an
  expected-failure control, because the instruction does not promise numerical
  latency bounds for those extra shapes.

These are expected outcomes, not new measurements. The current revision still
requires final-image Harbor and independent challenge execution.

## Provenance guarantee
This file is under `validation/`, which is never copied into the environment
image (see `environment/Dockerfile`). Phase C verifies via `docker history` and a
final-filesystem scan that no challenge, verifier, solution, or reward logic
leaked into the image.
