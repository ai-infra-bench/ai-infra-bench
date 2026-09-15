# Version 0.0.4 review and acceptance

Retain the task. The statement, source Base, Oracle and alternative solution are unchanged. This revision closes a confirmed verifier false positive: the saved v0.0.3 GPT-6 answer collapses distinct tool calls during SDK ID normalization. The revised full verifier rejects that answer while both complete positive controls pass 32/32 twice. All eight negative controls and Base receive reward 0. Final Harbor returns Oracle=1, early-exit=0, forged-report=0 with no errored trials; source compilation and 116 focused upstream regressions pass.

## Four review methods

Applied statement-review, task-review, rollout-review and, at the user's request, guided-review as an internal promise/counterexample/code/observation audit. Skill paths, revisions, dirty state and content hashes are recorded in e2e-evidence.json. Detailed internal notes are at /tmp/aib-dsh-migration-v004-20260912/review-notes.md. The prior two-attempt audit is /tmp/aib-dsh-migration-v003-rollout-review-20260912/review-report.md; no teaching questionnaire was used.

## Gates and fixes

1. Statement: one plausible workflow, continuing saved work on another model. Capacity admission and gateway history compatibility support that workflow. Preserve the explicit new API, allowance/default/capability ownership, empty-session boundary and wire shape. No additional algorithm hints or hidden case inventory were added. Comparison read the Code Mode parallel feature, Anthropic Rust feature and Responses compound-tool bug statements; their development/staged status is recorded rather than treating them as all fully accepted tasks.
2. Environment: unchanged Base and solver digests; the verifier only adds tests. Rechecked exact HEAD, clean status, absent remotes/tags/reflogs/FETCH_HEAD, no unreachable source objects and absent task artifacts in both solver and Base images. Captured image inspect/history; reused matching locked dependency cutoff evidence. Only external generated SSE is substituted; actual Loader, session selection, token meter, SDK, agent/tool loop and saved-event reconstruction run.
3. Verifier: add long shared ID prefixes, punctuation normalization, a known `openai` provider route and an ordinary-ID control to the existing pairing test. Inputs reach the stable Session Controller and real HTTP serialization; assert distinct calls remain uniquely paired with their own output. No private new helper, hash algorithm or ID spelling is required. Remove two remaining English error-word regex constraints while still requiring rejection and nonempty errors. Grading and collection logic are unchanged.

## Behavioral mapping

| Contract | Observation |
|---|---|
| Retained work plus output fits; known hard capacity; equality allowed | Real token meter, exact-fit and below-fit cases, output-capacity rejection |
| Caller ownership and no invented default | Empty/nonempty durable reopen, destination-only defaults, catalog capacity reservation |
| Idle, no pending input, no stale commit | Controlled lookup barrier, queued-and-cleared input, active-generation gate, old selection/events |
| Local durable migration and usable rejection | Reopened real tool execution, sibling/default/settings isolation, continuation on rejected old route |
| Reasoning association, replay and distinct IDs | Actual Responses input ordering, matched tool values, new four ID cases, preserved native state and disabled behavior |

Guided-review specifically checked observation timing: empty-session admission is asserted before any new prompt; later continuation is given space for new work. Collision tests first confirm both source tools ran, then observe the destination wire payload; counting two output records alone would not prove pairing. The race case uses entry/release signals and inspects unchanged selection, rather than sleeping or assuming await is a lock.

## Results and limitations

| Saved answer | Original v0.0.3 | Full v0.0.4 regrade |
|---|---|---|
| GPT-6 high | 28/28, reward 1 | 29/32, reward 0 |
| GPT-5.6 high completed same-session continuation | 23/28, reward 0 | 26/32, reward 0 |

The GPT-5.6 original interrupted attempt remains a separate infrastructure-limited observation. Original artifacts/rewards are unchanged. Both regrades use complete captured patches including new files. The initial diagnostic suite's long-label inventory mismatch was corrected before promotion; all 32 final names were verified exactly. No hack was observed in the reviewed material; captured tool-output truncation and uncaptured container state remain audit limits.

The generic optional artifact auditor still assumes a `deepseek-harness-` slug, Python requirements output and `solution/oracle.patch`; this approved task uses `dsh-`, Base's pnpm lock and `solution/feature.patch`. Those structural errors are retained in the audit output. Repository validation and a task-specific complete pre-run executable hash check pass. No claim of a complete upstream lint/docs/live-provider suite is made.

The final immutable verifier is recorded in environment/verifier-image-manifest.json. Raw acceptance logs, commands, controls, image audits and Harbor results are in v004-evidence.tar.gz. Executable pre-run hashes match the current task; later evidence writes are not substituted for pre-run records. A launch-directory mistake was repaired before either model worker started or made an inference request; that launcher record is preserved outside the model samples.

Two fresh model runs are authorized and running on this frozen revision: GPT-6 high and GPT-5.6 high, one each, Codex 0.118.0, 36000-second agent budget, zero regular request pacing and no replacement-trial retries. Actual first requests confirm high effort and exact statement delivery. These are fresh samples, not old-answer regrades. The task remains development and all changes are uncommitted; no push or publication was performed.
