# Remediation and verification (1.3.0)

| Finding | Change | Evidence |
| --- | --- | --- |
| F1: stdout success spoof | Root parent requires authenticated ordered completion from the preloaded suite; stdout is diagnostic | Exit, stdout-forgery, and direct-callback controls all receive 0; see formal Harbor records |
| F2: incomplete CPU/CUDA contract coverage | Explicit CPU-mask async/CUDA-mask count-sync boundary, both-device memory/count checks, unique rows, real OOV interface branch; removed implementation-specific transfer ban | 26-case suite, accepted index-copy alternative, allocator/reorder/sync controls |
| F3: singleton broadcast | Oracle and alternative explicitly validate counts before assignment | Legacy Oracle fails 1/3 on GPU; repaired implementations pass both-device mismatch checks plus independent valid-input challenges |
| F4: stale evidence | Preserve v1.2.0 history; bind current records to actual image, input hashes, completion and raw logs | e2e-evidence.json and hardening-evidence.zip |

First GPU matrix exposed a further gap: PyTorch sync-debug did not reject explicit `torch.cuda.synchronize()`. That draft run is retained as `matrix-before-explicit-sync-guard`; explicit stream/event/device guards were added and the entire 18-run matrix was rerun. Only `matrix/` certifies the final verifier.

## Final Docker-entrypoint matrix

| Case | Expected / actual | Completed checks | Actual final observation |
| --- | --- | --- | --- |
| base | 0 / 0 | 0/26 | ValueError: Error during masked scatter operation |
| oracle | 1 / 1 | 26/26 | PASS: interface_True: {'passed': True} |
| alternative-agent-implementation | 1 / 1 | 26/26 | PASS: interface_True: {'passed': True} |
| legacy-oracle | 0 / 0 | 14/26 | AssertionError: cardinality mismatch 1!=3 accepted |
| legacy-alternative | 0 / 0 | 6/26 | AssertionError: temporary allocation is excessive: cuda 5.509 |
| incomplete-agent-implementation | 0 / 0 | 0/26 | ValueError: Error during masked scatter operation |
| early-exit-systemexit | 0 / 0 | 0/26 | SystemExit: 0 |
| early-exit-os-exit | 0 / 0 | 0/26 | os._exit(0) before any authenticated checkpoint |
| forged-success-exit | 0 / 0 | 0/26 | PASS: production merge is ordered, async, bounded, strict, and CPU-mask native |
| forged-checkpoint-callback | 0 / 0 | 0/26 | RuntimeError: checkpoint did not originate in the trusted suite |
| cuda-extra-allocation | 0 / 0 | 6/26 | AssertionError: temporary allocation is excessive: cuda 6.003 |
| reverse-rows | 0 / 0 | 0/26 | AssertionError: embedding order, values, or non-placeholder rows changed |
| cpu-sync | 0 / 0 | 0/26 | AssertionError: CPU-mask merge explicitly waited for CUDA |
| cpu-implicit-sync | 0 / 0 | 0/26 | RuntimeError: called a synchronizing CUDA operation |
| oracle-repeat-2 | 1 / 1 | 26/26 | PASS: interface_True: {'passed': True} |
| oracle-repeat-3 | 1 / 1 | 26/26 | PASS: interface_True: {'passed': True} |
| alternative-repeat-2 | 1 / 1 | 26/26 | PASS: interface_True: {'passed': True} |
| base-repeat-2 | 0 / 0 | 0/26 | ValueError: Error during masked scatter operation |

Oracle three runs and alternative two runs have identical observed maximum peak ratios: 1.00274658203125. The 4× threshold is a broad regression bound, not a throughput or universal optimality claim. Every candidate ran in a fresh offline container; cases inside a suite recreate their tensors.

Integrity protection is bounded: native memory tampering and arbitrary mutation of in-process observers are not claimed solved. At this historical v1.3.0 checkpoint, full Qwen serving and fresh model-agent rollouts were not run. No paid model API is required for the deterministic control matrix.

## Subsequent rollout remediation (v1.3.2)

The historical 26-case matrix above is not a v1.3.2 rerun. Flash rollouts exposed the CPU-mask OOV scope extension (corrected in v1.3.1) and missing empty-outer count checks (six added in v1.3.2). Current Oracle/alternative are 32/32; Base/forged-success-exit are zero. Twelve effective model attempts were reviewed and completely replayed, plus four preserved infrastructure failures. See [rollout-review.md](rollout-review.md) and [rollout-attempts.json](rollout-attempts.json).

## Repeated-call remediation (v1.3.3)

Two implementation-independent CPU/CUDA cases vary mask positions, source values and text rows across consecutive equal-sized calls. The stale-placement counterexample now receives 0 after passing the original 32 checks. Oracle, index_copy, content-keyed caching and all four saved GPT-6 medium answers pass 34/34. The 18-run matrix and six formal Harbor trials preserve all expected control outcomes. See [repeated-call review](repeated-call-review.md) and `repeated-call-evidence.zip`; original 26/32-case evidence remains historical.
