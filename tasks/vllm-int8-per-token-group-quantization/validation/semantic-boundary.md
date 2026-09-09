# Semantic boundary — vllm-int8-per-token-group-quantization

contiguous CUDA tensors -> public per_token_group_quant_int8 dispatch and freshly rebuilt native _C -> quantized values/scales, fallback behavior and speedup against frozen Base Triton

## Components executed for real

- A100 CUDA execution and event timing
- Candidate _C rebuilt from candidate native sources
- Public wrapper and public _C operator
- Real Triton fallback and byte-identical Base reference

## Allowed substitutions and their limits

- Synthetic tensor values replace model activations; shapes, dtypes, group sizes and numerical ranges preserve quantization semantics.
- For dispatch-only fallback checking, the platform interface reports a non-CUDA backend while the actual Triton numerical computation runs on CUDA. This is not a claim of an AMD hardware run.
- Full model forward, tokenizer, attention and unrelated donor native extensions are outside the quantization path.

For performance tasks, workload dimensions that influence latency remain fixed
to the public timing contract. A different valid correctness input does not
establish performance equivalence. Fresh independent cases exercise the same
production boundary; they do not replace the production implementation.

## Coverage

- Four native correctness shapes spanning FP16/BF16/FP32 and 2D/3D, with independent PyTorch expected values.
- Configurable epsilon and INT8 bounds, zero input and a non-power-of-two group.
- Public dispatch observed through the native operator profiler event and Triton launches, without naming a private candidate helper.
- Five public BF16 timing shapes, 40 warmups and five samples of 400 calls; every native/reference speedup must be at least 1.5x.
- Correct native alternative, compatible operator alias and renamed private helper; incorrect operator name, slow correct kernel and early-exit controls.

Independent correctness inputs execute the exact native artifact captured from an observed successful Harbor rebuild, in a fresh final image with source and binary hashes checked. This reuse is explicitly scoped as a challenge, not another rebuild or grading run.

## Cutoff and provenance

Base Python/source/history and target _C are exact-source. Torch 2.7.1, Triton 3.3.1 and CUDA computation determine the target. The later base image and import-support packages do not supply the target quantizer; unrelated donor extensions are labeled and excluded from the target path. General build tooling is pinned.

See `e2e-evidence.json` for actual run identities and `final-review.md` for the
current review outcome. Earlier build notes are historical observations.
