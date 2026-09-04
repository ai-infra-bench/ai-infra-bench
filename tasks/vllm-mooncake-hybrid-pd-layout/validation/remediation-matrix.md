# Mooncake hybrid P/D layout hardening

Review rules: `/tmp/ai-infra-review-skill.QQWW99` at `0753f6b587d24f1c81c192d5a84ad2ac626f168e` (clean), loaded from the latest `origin/main` during this review.

Task worktree: `/home/qunhong/workspace/ai-infra-bench` on `tasks/rq1-eight-reviewed-tasks-with-tokenizer-review` at `579a50eafc552ad76f2396e8a36d6843b67df6dd` when review began. The task had only the approved `instruction.md` edit before hardening.

Target semantic boundary:

```text
hybrid cache configuration plus P/D request lifecycle
-> real Mooncake scheduler, cache registration, group-aware transfer planning,
   and producer-to-consumer byte movement
-> decode-visible cache contents, request progress, and surfaced failures
```

The vLLM scheduler, Mooncake connector logic, cache registration, and transfer planning are semantic and must run for real. Model forward passes, model weights, GPU allocation, and the native Mooncake RDMA transport may be replaced by deterministic CPU tensors and an in-memory transfer engine because they do not determine the Python layout and lifecycle behavior under test. No task-specific reproducer will be installed in the agent image; this is an explicit user decision.

| ID | Priority | Finding and evidence | Planned change | Validation | Status |
| --- | --- | --- | --- | --- | --- |
| T1 | P1 | The approved draft still prescribes duplicate registration, exact per-physical-block transfer count/length, and the final-token recomputation mechanism. Those are implementation details rather than observable outcomes. | Preserve the scope while expressing copied-state equality, untouched neighboring data, cold/warm completion, and error behavior. | Instruction-to-verifier mapping contains no Oracle-only symbol or algorithm requirement. | fixed |
| T2 | P2 | The instruction hash in `e2e-evidence.json` is stale after the approved rewrite. | Refresh only after executable artifacts and runs are final. | Final strict artifact audit passes. | fixed |
| E1 | P2 | `task.toml` gives the agent 3,600 seconds; the remote-main project rule requires 36,000 seconds. | Set `[agent].timeout_sec = 36000`. | Remote-main task validator and artifact audit pass. | fixed |
| E2 | P1 | The recorded canonical image is absent locally, so current Base/Oracle claims cannot be reproduced yet. | Rebuild or recover the exact canonical CPU image without changing semantic dependencies. | Image identity, startup, Git isolation, import path, and patch applicability checks pass. | fixed |
| E3 | P1 | The task mentions GPU model deployments but provides a CPU image without native Mooncake. The allowed substitution must retain the real scheduler, connector, registration, planning, and byte-copy boundary. | Keep native transport and model execution outside the semantic boundary; construct transport-neutral verifier fixtures only under `/tests`. | E2E uses real production connector lifecycle and actual pointer-based CPU copies; evidence records the limitation. | fixed |
| V1 | P1 | Current reward imports `_expand_transfer_regions` and `_align_transfer_regions`, constructs workers with `object.__new__`, injects Oracle fields, and calls `_logical_to_kernel_block_ids` and `_build_transfer_params`. Base can fail on missing Oracle shape rather than behavior. | Rewrite scoring around pre-existing connector/scheduler entrypoints and final observable state. Private helpers may be used only for non-reward diagnostics. | Base failures are behavioral; a structurally different correct implementation receives reward 1. | fixed |
| V2 | P1 | `test_real_inmemory_pd_transfer.py` repeats the same private-helper path and is not an end-to-end connector lifecycle. | Replace it with a composed CPU E2E covering real scheduler admission, real worker construction/registration, producer/consumer transfer, and copied tensor contents. Mock only native transport/network/model boundaries. | Base reaches the target subsystem and fails; Oracle passes with no skips. | fixed |
| V3 | P1 | The Oracle and tests omit two merged follow-up fixes: warm full-prefix Mamba truncation ordering and physical-block transfer-length scaling. | Backport both behaviors into the Oracle and add lifecycle/byte-corruption regressions. | Warm replay completes; ratio-greater-than-one transfers preserve payload and sentinels under coalesced and split descriptors. | fixed |
| V4 | P1 | The task has no `validation/ci-cases.json`, no correct alternative implementation, and controls cover only Oracle-shaped omissions. | Add a case manifest, behaviorally distinct incomplete patches, and one correct alternative with different internal structure. | Every incomplete control scores 0; the alternative scores 1. | fixed |
| V5 | P2 | The JUnit checker accepts at least 23 tests and checks four Oracle-specific names rather than an exact behavioral inventory. | Require the exact final case count, unique names, zero failures/errors/skips, and required behavior groups. | Mutated or incomplete JUnit is rejected. | fixed |
| V6 | P2 | Recorded evidence predates the frozen contract and all planned executable changes. | Regenerate evidence only from actual Base, Oracle, control, alternative, stability, isolation, and Harbor runs. | Final evidence hashes and recorded results match the final task. | fixed |

Follow-up review rules: `/home/qunhong/workspace/ai-infra-bench-pr47-review-main-20260904` at `b86460b7d670631a31fafe61d4d2f92bb8865de9`, using the clean `ai-infra-bench-task-review` skill inherited unchanged from its `origin/main` parent `0753f6b587d24f1c81c192d5a84ad2ac626f168e`.

| ID | Priority | Finding and evidence | Planned change | Validation | Status |
| --- | --- | --- | --- | --- | --- |
| F1 | P1 | Replacing prompt-embedding suffix truncation with prefix truncation still received reward 1 because the verifier checked only the resulting length. Token-ID contents were likewise not compared with the original prompt. | Compare the retained token IDs and prompt embeddings with the exact original prefix through the scheduler entrypoint. | Wrong-end token-ID and prompt-embedding counterexamples now receive reward 0; Oracle and the structurally different alternative receive reward 1. | fixed |
| F2 | P1 | A fully cached block-aligned remote-decode request could fail in `request_finished` and still receive reward 1 because the warm-prefix case stopped after `schedule()`. | Advance the repeated request through `update_from_output`, assert successful completion, then complete a subsequent request on the same scheduler. | The completion-failure counterexample now receives reward 0; the warm request and a subsequent request complete under Oracle and the alternative. | fixed |
| F3 | P1 | Skipping logical-to-physical expansion only for exact `FullAttentionSpec` still received reward 1 because ratio-greater-than-one cases covered only MLA variants. | Add full-attention to the existing real connector transfer case and preserve exact destination payload and untouched-neighbor assertions. | The full-attention expansion counterexample now receives reward 0; full-attention, MLA, and sliding-window MLA ratio cases pass under Oracle and the alternative. | fixed |
| F4 | P1 | Breaking NIXL worker registration still received reward 1 while the instruction broadly promised NIXL P/D compatibility; the executable contract only exercises GDN remote-prefill token accounting. | Freeze the task contract at the behavior relevant to this Mooncake change: NIXL GDN remote-prefill token accounting remains compatible. | The existing connector-level NIXL scheduler case passes without importing helpers or asserting implementation structure. | fixed |

Final follow-up validation: Base received reward 0 in five of five runs with 3 passed and 16 failed behavior cases per run; Oracle received reward 1 in five of five runs with 19/19 behavior cases and the composed E2E passing without skips. The correct alternative received reward 1, all nine incorrect controls received reward 0, both final ratio-three challenges passed, and Harbor Oracle job `b34b01c7-2845-4a10-86a4-6a5d6c473674` completed one trial with reward 1 and zero errors.
