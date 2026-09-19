# Review contract

Active layer plus conflicting ambient/legacy configuration -> real modular factory and backend configuration resolution -> owner-dependent workspace reservation, rank-ordered preparation, expert execution with the active TP/EP configuration, and finalized local results. Unowned functional construction stays non-DP+EP, and existing single-rank Triton numerical behavior remains unchanged.

## Real components and allowed substitutions

The verifier composes two paths. The existing profile/numerical path executes real modular construction, CUDA workspace allocation, LoRA injection through modular construction, and production Triton expert arithmetic. Its FlashInfer-to-Triton adapter is retained specifically for workspace and single-rank arithmetic coverage; that adapter is not evidence of real FlashInfer preparation or expert selection.

The added path enters `flashinfer_cutlass_moe_fp8` and executes the real preparation builder, expert selector, modular forward, FlashInfer prepare, `FlashInferExperts.apply`, and finalize. Only group transport and the external FlashInfer arithmetic leaf are substituted. Transport consumes the actual local payload, concatenates distinct rank payloads in order, and returns the local slice of the summed virtual-rank output. The leaf uses a deterministic identity transform while recording the actual external kernel ABI. The parent independently checks payloads, routing, TP/EP arguments, and final CUDA output against its own inputs. These substitutions retain the ownership distinction; they do not replace any component that decides which configuration governs preparation or execution.

This is composed single-device CUDA validation of configuration ownership, not an NCCL multi-process or FlashInfer FP8 numerical benchmark. Real Triton arithmetic supplies the promised single-rank numerical regression coverage. Network timing and FlashInfer arithmetic implementation are outside this task's ownership contract.

## Contract-to-check mapping

| Public behavior | Observation |
|---|---|
| Layer ownership survives conflicting ambient and legacy state | Production factory, FlashInfer helper and LoRA-owned modular kernels reserve workspace for their active layer |
| Compatibility construction works without global state | Real unowned construction and functional CUTLASS call path execute without the global-config warning |
| DP+EP profiling reserves worst-case capacity | Real CUDA logical temporary/view extent meets the frozen 16,384-row bound; ordinary owners avoid the worst-case reservation |
| Single-rank Triton numerics stay unchanged | Eight forwards against references derived from parent-owned random operands |
| Downstream preparation follows the active layer | Real gather consumes local inputs and produces rank-ordered hidden states, expert IDs and weights |
| Expert execution follows current TP/EP ownership | Real expert apply passes the active rank and group dimensions to its external arithmetic boundary |
| Finalization follows active DP ownership | Real finalize reduces and returns the correct local rank slice; non-DP remains local |

Six new cases combine absent and stale optional configuration, DP=1/2, flattened TP/EP groups up to four, both EP states, nonzero TP/DP ranks, and unequal rank sizes of three/five. A fresh parent-generated workload changes values and routing on each run. Expert execution may be chunked; no exact number of expert calls, private field name, config identity, or allocation helper is required.

The independent curator challenge uses different code, twelve experts, hidden width 256, rank sizes two/four/seven, DP up to three and flattened TP/EP up to six. It runs the same real lifecycle and verifies a different leaf transform. It imports no verifier workload generator, observer or checker. The separate independent workspace challenge also changes geometry and owner combinations.

## Controls and evidence discipline

The previous Oracle and three previously mislabeled positive controls are preserved byte-for-byte as negative controls. Their numerical/profile success did not establish downstream ownership. Correct controls now include active full-config forwarding, lazy owner derivation with complete downstream propagation, a layer-owned method implementation, and extra workspace shape queries with complete propagation. Reading the full `layer.moe_config` remains a valid interface; its `moe_parallel_config` view refers to the same production owner.

Additional isolated negatives omit only expert TP/EP propagation or replace finalization with the first rank's unreduced slice. Existing wrong-owner, undersized workspace, constant-output, warning, early exit, direct report, and observation replay controls remain. They must fail through the real grading entrypoint; static audit or process isolation alone is not proof of correct scoring.

The grading parent retains authoritative random inputs before importing candidate code. Its result checks do not trust candidate-provided input descriptions. FlashInfer's standard `FLASHINFER_WORKSPACE_BASE` setting points its cache to the worker's writable per-run directory; interpreter startup policy is unchanged by this repair.

Workspace scoring still observes logical CUDA temporary/view extents through real allocation, excluding input-owned storage. Existing numerical coefficients remain rtol=0.03 and atol=0.5, with FP32 accumulation error propagated through BF16/FP16 rounding intervals. No numerical tolerance, profiling bound, timeout, or hardware requirement is relaxed.

Historical rewards and review failures retain their original identity. Setup-only diagnostic failures are recorded separately and do not count as behavioral rejection. The final evidence records image identity, executable hashes, actual commands, job/trial IDs, exit status, raw artifacts, independent challenges, and the final frozen Harbor Oracle run. No fresh model rollout is implied by replaying the saved Astra production patch.
