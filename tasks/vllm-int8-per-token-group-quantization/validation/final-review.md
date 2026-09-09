# Local review — vllm-int8-per-token-group-quantization

Retain the task; native INT8 kernel acceleration is a realistic infrastructure workload.

**Outcome: PASS.**

Recorded: 2026-09-09T01:16:25.715152+00:00

## Gate 1: statement — PASS

A developer replaces an A100 Triton quantization bottleneck with a native vLLM CUDA operator while retaining the fallback.

Constructed profiling scenario; 1.5x is an acceptance target, not a historical performance claim.

## Gate 2: environment — PASS

contiguous CUDA tensors -> public per_token_group_quant_int8 dispatch and freshly rebuilt native _C -> quantized values/scales, fallback behavior and speedup against frozen Base Triton

- A100 CUDA execution and event timing
- Candidate _C rebuilt from candidate native sources
- Public wrapper and public _C operator
- Real Triton fallback and byte-identical Base reference

Allowed substitutions:

- Synthetic tensor values replace model activations; shapes, dtypes, group sizes and numerical ranges preserve quantization semantics.
- For dispatch-only fallback checking, the platform interface reports a non-CUDA backend while the actual Triton numerical computation runs on CUDA. This is not a claim of an AMD hardware run.
- Full model forward, tokenizer, attention and unrelated donor native extensions are outside the quantization path.

Base Python/source/history and target _C are exact-source. Torch 2.7.1, Triton 3.3.1 and CUDA computation determine the target. The later base image and import-support packages do not supply the target quantizer; unrelated donor extensions are labeled and excluded from the target path. General build tooling is pinned.

Base: `14bf19e39f601163265b7c7d58d972b8a83d8896`. Cutoff: `2025-07-23T18:29:36Z`.

Actual image: `sha256:7a5c0cea0298025a52c9d150808797ef0d6fd1f564458791b5993825c2206401`.

Agent-phase image audit checked source HEAD, clean worktree, remotes/refs, reflogs, unreachable/future objects, import path and absence of task verifier/solution/challenge inputs. The task-specific PR17 reference loader is now verifier-only.

## Gate 3: behavior and verification

- Four native correctness shapes spanning FP16/BF16/FP32 and 2D/3D, with independent PyTorch expected values.
- Configurable epsilon and INT8 bounds, zero input and a non-power-of-two group.
- Public dispatch observed through the native operator profiler event and Triton launches, without naming a private candidate helper.
- Five public BF16 timing shapes, 40 warmups and five samples of 400 calls; every native/reference speedup must be at least 1.5x.
- Correct native alternative, compatible operator alias and renamed private helper; incorrect operator name, slow correct kernel and early-exit controls.

alternate-native-kernel uses a different native kernel implementation; alias and private-helper-name controls separately check implementation freedom.

Independent correctness inputs execute the exact native artifact captured from an observed successful Harbor rebuild, in a fresh final image with source and binary hashes checked. This reuse is explicitly scoped as a challenge, not another rebuild or grading run.

| Case | Expected | Observed | Actual Harbor run |
|---|---:|---:|---|
| alternate-native-kernel | 1 | 1.0 | pr17-alternate-native-kernel-review-b |
| base | 0 | 0.0 | pr17-base-review-a |
| compatible-operator-alias | 1 | 1.0 | pr17-compatible-operator-alias-review-a |
| early-native-timing-exit | 0 | 0.0 | pr17-early-native-timing-exit-review-c |
| early-os-exit | 0 | 0.0 | pr17-early-os-exit-review-c |
| early-system-exit | 0 | 0.0 | pr17-early-system-exit-review-c |
| oracle | 1 | 1.0 | pr17-oracle-final-review |
| renamed-private-triton-helper | 1 | 1.0 | pr17-renamed-private-triton-helper-review-a |
| slow-candidate-occupancy | 0 | 0.0 | pr17-slow-candidate-occupancy-review-b |
| wrong-public-operator-name | 0 | 0.0 | pr17-wrong-public-operator-name-review-b |

Accepted current-revision trials have matching on-disk/Harbor rewards, zero Harbor errored trials and no trial exception. Base/negative outcomes are expected rejections, not failed validation of the task.

Independent challenges: alternate-native-kernel, base, oracle.

## Repairs and counterexamples

- Moved the task-specific frozen-reference loader and reference source out of the agent image into verifier-only inputs, then rebuilt and audited the image.
- Removed the private Triton helper-name requirement; compare against independent numerical reference and observe public dispatch.
- Added a correct private-helper-rename control.

## Scope and evidence

- A100 performance is measured on the specified local hardware; no cross-device performance equivalence is claimed.
- No claim of immunity to arbitrary native-code interference with in-process observations.

The configured agent timeout remains 36000 seconds. Thresholds were not reduced. Candidate source is actually executed and native targets are rebuilt when required. No candidate is scored by comparison with an Oracle patch.

Raw evidence root: `/data/yinchen/task-final-review-20260908T163254Z`. Machine-readable task evidence: `e2e-evidence.json`.

Skill revision: `ee32cad166ca065f02945bda6b2f6dca3a025ddd`; recorded worktree and file identities are in `initial-provenance.json` at the evidence root.

Existing user edits were preserved. No commit, push, registry publication or PR change was performed. Final worktree states and this-review diffs are recorded at the evidence root.
