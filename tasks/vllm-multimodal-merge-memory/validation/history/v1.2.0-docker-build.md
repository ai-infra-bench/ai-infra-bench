# Validation record

> **Historical evidence only.** The instruction, verifier, task configuration,
> or environment changed during the current hardening pass. These results do
> not validate the current executable snapshot and must be regenerated.

Validated on 2026-09-04 with the account-local Docker daemon at
`/root/workspace/dxz-workspace/.docker-dxz/run/docker.sock` and an NVIDIA
H20-3e. Runtime networking was disabled.

## Locked environment

- Base commit: `36d7f19897843c9cbdb701ba88d0f2c29954fe44`
- Oracle commit: `4f6eed3bd4a92c6bd513460ee85b917d6df88a17`
- Canonical base tree: `647523aac911ae44a1dcaab79ef66d58290b478e`
- Solution SHA-256:
  `6f4c23941397f5ca178724efd6a002a20ebe5b4075e0319265ebc50ad2d29256`
- Verifier SHA-256:
  `29b3116c16c0c6f3d558c301c25b5b0aa427e9b817524cce5385235d9fc867b5`
- Review image:
  `sha256:7c0babcc797e5175f8bcc8bacb8e64fecac7f6241575096fc489fb93921f480f`

The image is configured as `agent`, contains a writable one-commit source tree
with no remote, and is built only from `environment/`. The hardest task image
contains no public reproduction or `agent-test`; the Agent must derive its own
test from the reported production symptom.

The exact base predates the compatible official runtime image. All nine native
artifacts are copied from one digest-pinned v0.19.0 donor and hash-checked. The
scored merge primitive itself is Python/PyTorch; no candidate native operation
is substituted.

## Behavioural controls

| Candidate | Expected | Observed | Reason |
|---|---:|---:|---|
| Locked Base | 0 | 0 | A CPU placeholder mask reaches CUDA `masked_scatter_` and raises a device mismatch. |
| Accepted Oracle | 1 | 1 | CPU/GPU mask paths and all resource/correctness checks pass. |
| Frozen incomplete Opus patch | 0 | 0 | It optimizes only the same-dtype case; FP16/BF16 inputs still take the failing CPU-mask `masked_scatter_` path. |
| Independent GPT patch | 1 | 1 | A CPU-index implementation passes without copying the full boolean mask to CUDA. |

The hidden verifier calls the Base-existing production
`_merge_multimodal_embeddings` function and covers:

1. CPU masks under CUDA synchronization-debug mode;
2. rejection of an explicit full boolean-mask transfer to CUDA;
3. FP16, BF16, and FP32 output, nested inputs, stable placeholder ordering,
   in-place identity, and unchanged non-placeholder rows;
4. the existing CUDA-mask fast path and empty-input identity;
5. both directions of cardinality mismatch, requiring a `ValueError` whose
   message reports both counts and the relevant concepts without prescribing an
   exact sentence;
6. a broad CPU-mask peak-allocation guard below four times the target tensor.

Observed Oracle CPU-mask peak ratios were 1.003, 1.003, and 0.500. The
independent accepted patch observed 1.000, 1.000, and 0.500. This reduced test
does not claim full Qwen3-VL model accuracy or 8xH100 serving coverage.

## Fresh hardest-mode Agent run

Opus-5 was run after removing every public reproduction from the image. The
Agent traced the multimodal mask through Model Runner V2, inspected all merge
call sites and `CpuGpuBuffer`, checked the real CUDA environment, and built its
own `masked_scatter_` memory/device experiment. That experiment reproduced the
CPU-mask/CUDA failure without seeing the hidden verifier.

The model gateway then timed out after ten retries, before the Agent edited the
worktree. The run lasted 1,275 seconds and 30 Agent turns, cost `$1.303`, and
froze an empty patch. It is classified as infrastructure failure, not Agent
failure. With the hardened runner, the empty patch is scored as unchanged Base:
verifier exit `0`, reward `0`, and the expected production device-mismatch
trace. Network isolation was also probed from the live Agent container: the
authorized model API returned HTTP 200, while GitHub was unreachable both via
the CONNECT proxy and by attempted direct access.

Trajectory and result files are stored at
`ai-infra-bench-data/opus-5-gpu-v3-hard/vllm-pr-34246`.
> **Historical evidence only.** The instruction, verifier, task configuration,
> or environment changed during the current hardening pass. These results do
> not validate the current executable snapshot and must be regenerated.
