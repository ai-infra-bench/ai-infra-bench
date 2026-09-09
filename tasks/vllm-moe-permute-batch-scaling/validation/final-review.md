# Local review — vllm-moe-permute-batch-scaling

Retain the task; optimizing native MoE routing batch scaling without changing outputs is realistic.

**Outcome: PASS.**

Recorded: 2026-09-09T01:16:25.716913+00:00

## Gate 1: statement — PASS

A developer improves aligned native MoE permutation latency while preserving routing, inverse maps, payload bytes and sentinels.

Constructed profiling scenario; 250 us and 3.5 are explicit acceptance targets. Historical measurements remain separately identified and are not copied as current results.

## Gate 2: environment — PASS

expert routing and FP8 storage payload -> freshly rebuilt native _moe_C.moe_permute -> exact offsets/mappings/payload/sentinels and public A100 latency/scaling limits

- Actual A100 kernels
- Candidate _moe_C rebuilt from candidate sources and staged with recorded SHA256
- Public native operator with correctness before timing
- Actual CUDA event timing

Allowed substitutions:

- Synthetic routing and payload bytes replace upstream model/router execution. Expert count, top-k, hidden width, storage type, alignment and balanced routing are preserved.
- Full MoE network, serving HTTP and tokenizer are outside the permutation/timing boundary.

Exact Base/history and candidate native source. Torch/CUDA and native build inputs are locked; unrelated model/tokenizer behavior does not determine these operator results.

Base: `dc917cceb877dfd13f98c538c4c96158047d98bd`. Cutoff: `2026-01-22T23:21:35Z`.

Actual image: `sha256:6698c86f56f02fa0c16acb4da43776da59e9bf72abd276ce8cb58863d973e900`.

Agent-phase image audit checked source HEAD, clean worktree, remotes/refs, reflogs, unreachable/future objects, import path and absence of task verifier/solution/challenge inputs. The task-specific PR17 reference loader is now verifier-only.

## Gate 3: behavior and verification

- Nine token counts times aligned/unaligned modes: 18 correctness cases covering exact offsets, inverse/permuted maps, expert ranges, byte payload and sentinels.
- Seven public timing sizes plus two diagnostic sizes. Only public 4096 latency and 4096/512 ratio determine numerical performance acceptance.
- 64 experts, top-k 6, hidden 2048, FP8 E4M3 storage, alignment 128; 20 warmups, 50 iterations, five repeats.
- Parent validates sample completeness, positivity/finiteness, timing protocol and recomputes medians/ratio; there is no unmeasured +/-5% condition.
- Different correct CUDA scaling implementation, incorrect linear scan, immediate/delayed native exits and root-startup control.

alternate-cuda-scaling changes the parallelization strategy while preserving the complete permutation contract.

Independent routing/input variation executes freshly rebuilt native code and checks correctness plus the public workload limits.

| Case | Expected | Observed | Actual Harbor run |
|---|---:|---:|---|
| alternate-cuda-scaling | 1 | 1.0 | pr19-alternate-cuda-scaling-review |
| base | 0 | 0.0 | pr19-base-review |
| diagnosis-only-linear-scan | 0 | 0.0 | pr19-diagnosis-only-linear-scan-review-resumed |
| early-native-exit | 0 | 0.0 | pr19-early-native-exit-review-resumed |
| early-native-immediate-exit | 0 | 0.0 | pr19-early-native-immediate-exit-review-resumed |
| oracle | 1 | 1.0 | pr19-oracle-review-final |
| root-python-startup | 0 | 0.0 | pr19-root-python-startup-review-resumed |

Accepted current-revision trials have matching on-disk/Harbor rewards, zero Harbor errored trials and no trial exception. Base/negative outcomes are expected rejections, not failed validation of the task.

Independent challenges: alternate-cuda-scaling, base, oracle.

## Repairs and counterexamples

- Published previously missing performance workload parameters without changing either threshold.
- Isolated trusted scorer startup and used staged trusted entrypoints.
- Preserved the correction that the historical +/-5% timing assertion was never measured.

## Scope and evidence

- Performance claims are limited to the specified A100 and workload.
- The parent recomputes results from recorded samples; it does not claim that self-reported samples alone prove kernel execution.

The configured agent timeout remains 36000 seconds. Thresholds were not reduced. Candidate source is actually executed and native targets are rebuilt when required. No candidate is scored by comparison with an Oracle patch.

Raw evidence root: `/data/yinchen/task-final-review-20260908T163254Z`. Machine-readable task evidence: `e2e-evidence.json`.

Skill revision: `ee32cad166ca065f02945bda6b2f6dca3a025ddd`; recorded worktree and file identities are in `initial-provenance.json` at the evidence root.

Existing user edits were preserved. No commit, push, registry publication or PR change was performed. Final worktree states and this-review diffs are recorded at the evidence root.
