# Independent fresh challenge -- vllm-int8-per-token-group-quantization

Curator-side verification harness. **Not** the agent verifier (`tests/`), **not**
referenced by `instruction.md`, **not** mounted into the agent image or any image
history layer. It exists only under `validation/challenge/` and is invoked directly
during dynamic validation (Phase D).

## Production API exercised
`int8_utils.per_token_group_quant_int8 (+ torch.ops._C.per_token_group_quant_int8)`

This is the same production entry point the agent verifier uses, so a correct
solution that passes `tests/` must also pass this challenge. The challenge is
**not** a copy of the verifier: it re-derives the invariant on independently
chosen inputs.

## Independent invariant
The public wrapper dispatches to the native custom op (not a Triton fallback) and matches a from-scratch reference quantization with the correct int8 range clamp and per-group scale.

## Fresh inputs (not drawn from the verifier or `ci-cases.json`)
Shape (6, 192) with group_size 96 plus a negative-heavy row; not in the verifier's (4,128)/64, (3,64), (1,80) set. A Triton-bomb guard proves the native path is taken.

## How Phase D runs it
```
python3 validation/challenge/challenge_int8_quant.py  (GPU/CUDA; Phase D)
```
Emits machine-checkable JSON and a final `CHALLENGE_INT8_QUANT=PASS|FAIL` line; exits
non-zero on failure.

Expected outcomes in Phase D:
- **Oracle**: `CHALLENGE_INT8_QUANT=PASS`.
- **Semantically-different correct alternative** (`alternate-native-kernel.patch`, apply_after=base, expected_reward=1): `CHALLENGE_INT8_QUANT=PASS`.
  Confirms the challenge scores the behavioral contract, not one implementation.
- **Base / incorrect** (`wrong-public-operator-name.patch (expected_reward=0)`): `CHALLENGE_INT8_QUANT=FAIL`.

## Provenance guarantee
This file is under `validation/`, which is never copied into the environment
image (see `environment/Dockerfile`). Phase C verifies via `docker history` and a
final-filesystem scan that no challenge, verifier, solution, or reward logic
leaked into the image.
