# PR18 handoff device-copy review — v1.2.4

Retain the task. The reproduced P1 scoring omission is fixed and no blocking finding remains in this review. The original correct implementation plus `recv.cpu().to(self.device)` incorrectly scored 1; with the revised verifier the same behavioral mutation scores 0, with `gpu_cpu_handoff_sync` in all three NCCL scenarios. CONFIG and SCHEDULER_REENTRY still complete.

Gate 1 passes: the unchanged three-paragraph contract describes a feasible two-rank asynchronous pipeline token handoff and scheduler reentry. No implementation names or hidden-case hints were added. The agent budget is 36000 seconds.

Gate 2 passes: Base, dependency cutoff, Docker recipe and image are unchanged. Every Harbor run checked the exact image identity and an agent-user GPU canary. The solver still receives ordinary source and dependencies; the new observer and controls are verifier-side artifacts.

Gate 3 passes: real runner construction → execute_model → sample_tokens → real two-rank NCCL → token storage, row mapping and placeholders → next GPU input and scheduler reentry. Deterministic model/logit/sampler inputs replace weight execution, while the behavior-determining lifecycle, state transitions and transport remain real. No candidate-private initialization is injected.

The observer records actual tensor source/destination devices and explicit CUDA device/stream/event host waits. It works under production inference_mode. Blocking device-to-host copies and CUDA host reads fail; CPU metadata and the production nonblocking output copy remain valid. Instrumentation observes the call and reports typed failure afterwards, without replacing tensor operations. The independent challenge uses fresh five- and seven-request inputs, interleaved discards and nonempty histories. Rank reports are serialized after the observed call to avoid stdout interleaving.

| Public behavior | Executed coverage |
| --- | --- |
| Async PP configuration and real GPU tensor collective | CONFIG and three two-rank NCCL scenarios |
| No CPU-object collective or CUDA-to-CPU synchronization in handoff | Object-collective control; .cpu(), .to("cpu"), CPU-destination copy_, explicit host-wait controls; CUDA host-read regressions |
| Correct rows, discard mapping, one retained placeholder, next token input | BASIC, REORDERED, INTEGRATED and fresh 5/7-request challenges |
| Overlapping runnable scheduler rounds | Real scheduler, one and three requests, two schedule calls before output update |
| Alternative repair locations and normal CPU work remain valid | Inline NCCL, GroupCoordinator, constructor-owned transport, execute-owned state, CPU metadata scalar and pinned output-buffer controls |
| Failure cannot suppress remaining diagnostics | Existing early exits and post-broadcast failure through full Harbor, complete parent stage manifest |

17 full Harbor runs, 10 independent challenge invocations (20 scenarios), and 32 real-CUDA observer regressions met their expected outcomes. Base scored 0; Oracle and every declared correct alternative scored 1; all declared incorrect controls scored 0. Harbor reported zero errored trials. The final frozen Oracle repeated reward 1 with exact current executable hashes.

| Control | Expected | Observed |
| --- | --- | --- |
| oracle | 1 | 1 |
| alternate-inline-nccl | 1 | 1 |
| group-coordinator-broadcast | 1 | 1 |
| constructor-owned-transport | 1 | 1 |
| execute-owned-pending | 1 | 1 |
| cpu-metadata-scalar | 1 | 1 |
| pinned-output-buffer | 1 | 1 |
| d2h-roundtrip | 0 | 0 |
| d2h-to-cpu | 0 | 0 |
| d2h-copy-destination | 0 | 0 |
| handoff-host-wait | 0 | 0 |
| base | 0 | 0 |
| cpu-sync-object-collective | 0 | 0 |
| early-system-exit | 0 | 0 |
| early-os-exit | 0 | 0 |
| post-broadcast-failure | 0 | 0 |
| oracle (final frozen repeat) | 1 | 1 |

The post-broadcast failure control deliberately raises RuntimeError after the real collective. Its worker error and peer wait are expected; CONFIG and SCHEDULER_REENTRY must still complete, with no Harbor exception.

The initial observer pilot and the challenge's interleaved-report diagnostic are retained and explicitly excluded from these counts. Earlier matrices before the CPU-allocation fairness correction are also excluded. All final Harbor and challenge runs, including the final Oracle repeat, match every current executable file.

`e2e-evidence.json` records commands, raw logs, image identity, job/trial IDs, checksums, final hashes, and the limits of this instrumentation. No new Opus rollout is claimed. The original Oracle, instruction and scoring supervisor are unchanged. Changes remain local and uncommitted/unpushed.
