# PR #61 hardening — v1.6.0

The task remains a valid CPU scheduler task. This revision addresses the five concrete review findings: mutable in-process grading, missing EngineCore liveness coverage, weak idle scaling calibration, incorrect long-run reference memory behavior, and mapping-order false rejection. The task statement keeps the same behavioral contract and only splits its final paragraph. The image and environment inputs are unchanged.

## Behavioral boundary and substitutions

Requests and ready/cancellation events enter the production scheduler through its normal interfaces. Real `EngineCore.step()` calls the scheduler, receives deterministic model/connector outputs, updates lifecycle state, and produces client tokens and terminal outputs. Scheduler queues, KV ownership, unfinished accounting, preemption and cleanup are real. Model arithmetic and transport-event production are deterministic substitutes; they do not determine the target CPU scheduling defect. No HTTP, GPU, NIXL/RDMA or full model quality claim is made.

The parent process owns assertions, expected token digests, required group completion and reward. It starts with isolated Python and site loading disabled, never imports candidate vLLM, and samples the child's OS CPU clock. Candidate code cannot find or mutate a parent `run_suite` frame. A dedicated child exposes request operations and outputs. Tests check those outputs against independently generated expectations instead of accepting success checkpoints.

The resource observer counts requested live Python allocator bytes, including collection backing buffers. It starts before candidate imports and measures growth after warm-up; it excludes its own native bookkeeping and counts nested allocator-domain requests once. There is no reset API. The native code signs the current count together with a fresh parent nonce. Python replacements for timing or `tracemalloc` are not measurement sources. An independent 4 MiB allocation/reclamation probe checks the observer, including a fake `tracemalloc` function and attempted reconfiguration. This protects the demonstrated Python-level grading attacks; it is not a sandbox against arbitrary native memory access or allocator replacement.

## Bidirectional contract mapping

| Published requirement | Required group / observable assertion |
|---|---|
| Idle work must not scale linearly with unchanged remote waiters | Pure and mixed idle at 64/1,024/8,192 requests, median worker CPU cost measured by the parent |
| Local requests advance while transfers wait, and remote requests resume | EngineCore lifecycle with chunked prefill, out-of-order ready events, and all-remote polling |
| Request identity, token order, completion and later admission remain correct | Parent-generated tokens, actual client outputs, one terminal per request, drained state, fresh admission |
| Cancellation during transfer remains correct | Cancel before/after readiness and deliver late completion; cancelled work cannot return |
| FCFS holds across other temporarily blocked reasons | Grammar/remote/streaming waits compete for one slot; actual admission order is checked |
| Streaming and no-connector paths continue working | Multiple streaming segments without remote events; connector-disabled lifecycle |
| Existing scheduling behavior survives capacity and preemption | Backpressure and repeated prefix-cache reset with runnable backlog, local and remote-origin requests |
| Sequential short requests retain at most 32 MiB beyond warm-up | 32–64 token prompts, normal completion, same live scheduler, local/remote streams to 1,310,720 requests |
| Bounded caches and delayed/batched cleanup are allowed | Positive controls retain bounded Request history or reclaim in batches; GC/idle opportunities precede measurements |
| Internal representations are free | Reordered token-count mapping passes; no Oracle queue, placeholder, helper or container-size assertion |

Twelve groups replace the former seventeen groups plus a completion checkpoint. This reorganizes overlapping checks around the parent-owned boundary; it does not imply twelve distinct inputs. Parameterized runs include three idle populations in two modes, both cancellation races, two streaming populations, both backpressure modes, two preemption backlog sizes in two modes, and both long-run memory modes.

## Reference implementations and history

The Oracle drains the inherited `new_block_ids` buffer even when KV zeroing is disabled. This is the frozen Base defect later addressed by upstream vLLM PR #44490, not a regression introduced by the remote-wait optimization. The repaired heap alternative also discards completed per-request version entries. Separate controls restore each omission so that an incorrect positive cannot silently return to the calibration set.

The 32 MiB contract already existed in v1.5.0; it is not attributed to earlier versions. Historical model rollouts and rewards remain historical. This hardening performs reference/control replays and independent challenges, not fresh LLM capability trials. Previous reports and their original hashes are preserved in `history/curation-history.zip`; older raw calibration and model summaries remain in `evidence.zip`.

## Validation and environment identity

The machine-readable evidence index contains the completed final-snapshot matrix, first failure reasons, raw-log archive, separate stability/independent challenges and Harbor results. All runs labeled final use a frozen copy of the executable task. Later updates to this report, the evidence index and the log archive are evidence-only and do not replace execution-time hashes.

The locally available diagnostic image uses the verified exact Base tree and the same fixed CPU donor, dependencies, source overlay and cleaned filesystem. Full GitHub history acquisition failed during the preceding review, so this diagnostic image contains synthetic Git history and has a different image ID from the canonical task image. This limitation is recorded explicitly in the evidence index; local results are not misidentified as a canonical-image rebuild. No environment input is changed by this PR revision.

Finite workloads cannot establish bounds for every future input, and the allocation observer does not measure GPU memory, RSS or all arbitrary native allocation. Required native binaries remain the original image's documented ABI simplification. These limits do not exempt either reference from the stated behavior or public Python-memory budget.

## Completed local validation

All 22 final-snapshot Base/Oracle/control replays matched their expected rewards. Oracle, the repaired heap alternative, bounded history, batched reclamation and reordered token-count mappings each completed 12/12 groups with reward 1. The seventeen negative subjects received reward 0 for their recorded behavior, integrity or required-completion failure. The historical whole-Request retention control is now rejected at 16,384 completions for exceeding the byte budget, without waiting for a long-run timeout.

Five actual Harbor 0.22.0 trials completed with zero framework errors: Oracle and reordered mappings received 1; SystemExit(0), os._exit(0), and measurement-global tampering received 0. Oracle took about 405 seconds in the direct run; the other full positive runs took about 393–546 seconds. The verifier budget remains 600 seconds. Both Oracle memory streams finished with 96 bytes of observed growth; the repaired heap peaked at 128 bytes. Bounded and batched history peaked below 7 MiB. These are measured deltas for this workload, not universal memory claims.

The separate identity-reuse challenge passed on both Oracle and heap. The native observer calibration measured a 4 MiB allocation, remained accurate after replacing the Python tracemalloc function, observed reclamation, and refused reconfiguration. Repository validation, strict artifact audit (4 checks, 0 errors, 0 warnings), and diff whitespace checks passed.

Validation ran from the uncommitted `codex/pr61-behavior-hardening` worktree at `/tmp/ai-infra-pr61-review-20260919`, before the user-authorized commit and push to PR #61. Local hardening is complete. The evidence retains `final_acceptance: false` for task publication because the canonical image was not rebuilt/revalidated; all new runtime results identify the exact-source diagnostic image instead. Publishing the source changes does not represent a new runtime validation or model trial.
