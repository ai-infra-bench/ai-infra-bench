# Validation record

> **Historical evidence only.** The instruction, verifier, task configuration,
> or environment changed during the current hardening pass. These results do
> not validate the current executable snapshot and must be regenerated.

Status: focused CUDA behavior is calibrated. The task does not claim to run a
Mamba model, NIXL transport, or an end-to-end accuracy suite.

## Public contract and later upstream evidence

PR #42430 addressed a silent NIXL prefill/decode accuracy failure under FULL
CUDA graphs. A decode-side recomputation of token N starts with transferred
Mamba state h(N-1), but arrives as a scheduler-labelled, one-token prefill; the
FULL-CG path is decode-shaped.

PR #43034 was opened later to revert the merged patch after a four-GPU Hybrid
SSM/HMA nightly regressed from roughly 0.80 to 0.75 accuracy. That later result
is important Oracle risk, but it cannot be made a public requirement of this
historical task: the designated PR Oracle does not satisfy it. The task instead
grades the atomic behavior reported and implemented by #42430 and records the
missing end-to-end topology honestly.

## Verifier boundary

The hidden verifier uses a real CUDA device and the production
`BaseMambaAttentionMetadataBuilder` paths. It checks:

- ordinary decode remains decode-shaped;
- a prior-state one-token prefill becomes decode-shaped for FULL CG;
- a genuine first prompt token remains prefill-shaped;
- a wider speculative prefill remains prefill-shaped;
- a mixed prior-state/first-token batch is split correctly; and
- candidate logic performs no CUDA operation caught by synchronization-debug
  mode while metadata is built.

It intentionally does not claim coverage of model kernels, graph replay, NIXL
transport, Hybrid Memory Allocator behavior, or token-level accuracy.

## Controls

Validated on an NVIDIA H20-3e (compute capability 9.0) using the isolated Docker
daemon at `/root/workspace/dxz-workspace/.docker-dxz/run/docker.sock` and
`--network none`.

- Base: reward `0`; the prior-state row remains `(decodes=0, prefills=1)`.
- Oracle: reward `1`; the prior-state row becomes `(1, 0)`, the first-token row
  stays `(0, 1)`, and the speculative and mixed-batch guards pass.
- Broad reclassification counterexample: rejected by the first-token and
  speculative-prefill guards.
- Frozen Opus-4.8 candidate: reward `0`; enabling the generic
  `treat_short_extends_as_decodes` path under FULL CG also reclassifies a true
  first-token prompt, demonstrating that the guard rejects a plausible fix.
- Independently structured equivalent: reward `1`; it derives prior state from
  sequence and scheduled lengths and uses a conditional tensor selection,
  without depending on an Oracle helper or source spelling.

Base and Oracle were each repeated in three fresh containers with stable `0`
and `1` rewards, respectively.

The image contains the pinned base source, one synthetic git commit, no remote,
and no public reproduction copied into the Agent workspace. The Oracle patch
and hidden verifier are mounted only after the candidate patch is frozen.

## Remaining risk

This is a focused metadata invariant, not a substitute for the original
multi-process accuracy run. In particular, the later Hybrid SSM/HMA regression
shows that passing this task does not prove every Mamba/NIXL topology safe.

## Hardest-mode Agent evidence

Opus-5 ran for 3,785 seconds and 99 Agent turns with a `$10` budget. Without a
public reproduction it inspected Mamba attention builders, NIXL and SSM transfer
code, Model Runner graph dispatch, mixed-batch construction, and neighboring
attention backends. The budget was exhausted while it was still tracing the
classification path; the frozen patch is empty. This is recorded as “no
candidate within budget”, not a verifier crash and not a passing Base result.

A prior frozen Opus-4.8 candidate did produce the plausible broad fix described
above and is rejected by the strengthened first-token guard. Together these
runs show that the prompt does not hand the implementation to the Agent while
the verifier distinguishes an attractive but incorrect solution.
> **Historical evidence only.** The instruction, verifier, task configuration,
> or environment changed during the current hardening pass. These results do
> not validate the current executable snapshot and must be regenerated.
