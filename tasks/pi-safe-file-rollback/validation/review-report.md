# Independent task review

**Disposition: retain version 0.0.3 for review.** All 12 author-control trials and one saved-answer replay produced the expected rewards with zero errored trials. Post-rollout review exposed a regression-fixture defect missed by initial qualification; the correction and its independent checks are recorded as R3 below. R4 records the first-person prompt rewrite and removal of unnecessary interface representation constraints. Current executable artifacts match the new evidence. No blocking finding remains for local task validation; public image distribution is still pending.

**Initial qualification: 10/10 dimensions scored; 20/20.** The table retains that rubric and updates the affected evidence. Initial scores did not establish exhaustive correctness or prevent the later fixture false negative. The current review preserves that fixture correction, checks prompt/verifier alignment, and reruns the full control matrix and unchanged saved answer. Model solve rate remains uncalibrated.

| # | Dimension | Score / status | Key evidence | Next action |
| --- | --- | --- | --- | --- |
| 1 | Realistic and clear | 2 — Pass | Plausible interrupted-coding workflow; valid Pi interfaces; explicit file, ownership and recovery boundaries | None |
| 2 | Correctness independent of a source PR | 2 — Pass | Self-contained behavioral contract; no prescribed historical implementation | None |
| 3 | Solvable in the environment | 2 — Pass | Exact Base, offline build, usable unprivileged development environment and clean image/Git audit | Retain the audited image |
| 4 | Bidirectional statement/test alignment | 2 — Pass | All 25 cases mapped; retry, ancestor navigation, both file/directory transitions and recovery interactions covered | Preserve the contract map |
| 5 | Real behavior-determining path | 2 — Pass | Real SDK, RPC, PTY, tools, Bash descendants, files, sessions and restart; actual provider input observed | None |
| 6 | Different correct implementations accepted | 2 — Pass | Oracle, CAS/framed-journal/rename alternative, interface variant and unchanged saved Astra answer each earn 1 with 25/25 behaviors | Retain fixture controls |
| 7 | Incorrect implementations rejected appropriately | 2 — Pass | Base and all eight negative controls earn 0 for intended behavioral violations; builds and regression gates succeed | Retain the controls |
| 8 | Oracle independently validated | 2 — Pass | Independent ancestor challenge exposed R1; repaired Oracle passes that public case and final full grading | None |
| 9 | Trustworthy grading | 2 — Pass | Independent observations, protected reports, exact inventories and actual successful early exit rejected with reward 0 | Keep claims within tested boundaries |
| 10 | Reproducible acceptance and handoff | 2 — Pass | Final Harbor identities/hashes recorded; strict audit: 5 checks, 0 errors, 0 warnings | Preserve final evidence |

## Three gates and execution boundary

**Gate 1 — statement: pass.** The first-person instruction was independently reviewed without access to the Oracle or verifier, then frozen before verifier edits. Its 550 words retain the behavioral difficulty while removing unnecessary response-schema definitions. It exposes no implementation algorithm, persistence layout, code location, root cause, private fixture, hidden-case inventory or public-solution link. Minimal SDK/RPC names, inputs and state fields define usable public entrypoints. Checkpoint order, optional metadata and rollback success payload are unconstrained. The constructed scenario makes no unsupported historical or measurement claim.

**Gate 2 — environment: pass.** Base is `d981de1229ef899957bbe968bc8dcda02a21f477`; cutoff is `2026-09-05T12:05:48Z`. The original dependency lock is preserved. Runtime model JSON comes from a hash-pinned npm release with the same Git head, published before the cutoff; production source remains at Base. The empty build context, historical layer scan and Git audit found no task-private artifact, future/unreachable source object or additional checkout. Normal source editing and the offline CLI work under the agent user. See [image audit](image-audit/summary.json).

The retained image is `sha256:f9cec7500e2e00d3f58ed5ddc9a40cbf13a69f8c885718e72398b1907e1c0e50`. The configured environment is Linux/amd64, CPU, 4 CPUs, 8 GiB memory, 20 GiB storage and no network. The 36,000-second agent budget meets the review's minimum-warning boundary. Image identity, rather than rebuilding live apt/apk inputs byte-for-byte, identifies the validated runtime.

**Gate 3 — verification: pass.** The smallest complete boundary is:

`public request / rollback / process termination -> real AgentSession, tools, persistence and recovery -> files, Git HEAD/branches/index entries, effective model context, public state/errors and restart behavior`

The local HTTP provider supplies deterministic valid model responses and records actual requests. It performs no file restoration, checkpointing or conversation rewind. The SDK peer only transports public operations. The supervisor terminates the execution tree from observed public file activity, without reading candidate journals or imposing a restoration order. Held model responses and Bash FIFOs establish causal interruption points. Real provider requests during recovery must observe fully restored files and conversation. A valid atomic restoration need not manufacture additional writes for a second interruption.

The independent supervisor validation passed 33/33 executions across 11 mechanisms, repeated three times, including threads, fork/vfork, rename, mmap and startup arming. Those probes validate the observer rather than the product implementation. See [supervisor evidence](supervisor-probes/summary.json).

## Coverage and fairness

[behavior-map.md](behavior-map.md) maps all 25 scored cases to the public contract. Coverage includes opt-in/disabled/in-memory operation; stable pre-request boundaries; real retry, steering and follow-up grouping; dirty/untracked files, bytes, permissions, creation/deletion/rename and both file/directory transitions; whole-operation human-conflict rejection; unrelated edits; failed/cancelled/in-flight Bash; first and repeated interrupted resumes; interrupted rollback; concurrent execution gating; filesystem failure/retry; ancestry/idempotence; and SDK, RPC and terminal interfaces.

Assertions observe public results, normal session entries, filesystem state, actual model input and stable Git semantics. Git checks include commit and symbolic HEAD identity, user branches and index entries; private Git refs and incidental index-cache bytes are not constrained. No private journal, helper name, storage order or source-text match affects reward. The alternative shares public integration with the Oracle but materially differs in persistence and restoration: immutable content-addressed blobs, checksummed append-only frames and staged rename publication. Its independent correctness obligations were checked in addition to its passing reward.

The original 2,158-test regression inventory and all its assertions remain intact. Version 0.0.2 adapts two legacy session stubs to the task's public disabled-state API; it does not alter event order or expected outcomes. Every final trial builds successfully, completes that inventory without missing/extra cases, passes the separate stable auth test and produces all 25 behavior results. Candidate code runs unprivileged; expectations and scoring reports remain protected while checks execute. Reports are made readable for collection only afterward.

## Final formal results

[e2e-evidence.json](e2e-evidence.json) records Harbor 0.23.0 job/trial identities, input and result hashes, case outcomes and durations for the 12 author controls. [saved-answer-regrade.json](saved-answer-regrade.json) separately records the complete saved-answer replay. All 13 version 0.0.3 trials completed with zero Harbor errors and no environment-kind behavioral failures. Eleven have 2,108 original passes and 50 skips; memory-only and early-process-exit-zero each have 2,107 passes, 50 skips and the one accepted Base timestamp failure. Every stable auth counterpart passes. These controls still fail for their intended behavioral defects; the existing exception policy is unchanged.

| Implementation | Expected / actual reward | Behaviors passed | Distinguishing result |
| --- | --- | --- | --- |
| Base | 0 / 0 | 0/25 | Required rollback capability absent |
| Oracle | 1 / 1 | 25/25 | Complete required behavior |
| Alternative | 1 / 1 | 25/25 | Different storage/restoration mechanism accepted |
| Interface variant | 1 / 1 | 25/25 | ID-only/reversed checkpoints, empty RPC success data and blocked conflict diagnostics accepted |
| Memory-only | 0 / 0 | 17/25 | Enablement/checkpoints/recovery lost across restart |
| Checkpoint at request end | 0 / 0 | 20/25 | Interrupted request lacks durable recovery boundary |
| Files-only | 0 / 0 | 13/25 | Removed conversation reaches effective context |
| Conversation-only | 0 / 0 | 8/25 | Workspace changes remain |
| Ignore conflicts | 0 / 0 | 22/25 | Human conflicts are accepted or discarded |
| Skip startup recovery | 0 / 0 | 19/25 | Unfinished execution/restore loses its gate |
| Abandoned branch included | 0 / 0 | 23/25 | Non-ancestor targets exposed as eligible |
| Early successful exit | 0 / 0 | 1/25 | Enabled SDK exits before serving behavior; disabled behavior still passes |
| Saved Codex / GPT-6 Astra xhigh answer | 1 / 1 | 25/25 | Unchanged answer passes the corrected regression fixtures and full behavior suite |

The repeated early-exit control receives reward 0 because enabled SDK execution ends before the required observations; only its disabled-mode case passes. Its current trial and result hashes are recorded in the control evidence. This establishes rejection of the demonstrated incomplete-execution control, not universal tamper resistance.

## Resolved independent findings

**R1 — P1, resolved: non-ancestor rollback after ordinary backward navigation.** The independent SDK challenge completed requests A/B, navigated back to A's user entry without sibling switching, then submitted B's now-non-ancestor checkpoint. The original Oracle accepted it and changed both files and effective conversation. Both implementations now validate against the current session ancestry. The existing public invalid-target case verifies list eligibility, rejection and unchanged files/conversation/Git state; it failed before repair and passes in the final Oracle and alternative runs.

**R2 — resolved: reverse file/directory transition in the alternative.** Replacing a tracked file's parent directory with a regular file leaves the tracked descendant discoverable by Git while `lstat` returns `ENOTDIR`. The alternative initially propagated that error. It now handles the missing descendant correctly and has a production regression test. The existing public shape case exercises both directions and passes for both implementations in formal grading.

**R3 — false-negative regression fixtures, resolved in version 0.0.2.** A saved Astra answer passed all 25 behavior cases but received reward 0 because four original TUI cases used incomplete mock session receivers. The candidate calls the newly required public `getRollbackState()` method during session binding; the real session supports it, while those fixtures did not. Initial qualification missed this coupling because both author implementations happened to tolerate the incomplete stubs.

The correction adds only the disabled-state method to the two affected fixture files when Base tests are rehydrated. All 301 rehydrated files and the 265-test-file inventory were independently checked: only those two files differ, and removing the mock additions reproduces their exact Base bytes. Original assertions, event ordering and barriers remain unchanged. In targeted independent runs, the corrected saved answer passes all eight cases; moving binding before rendering/subscription still fails four original assertions, and removing the stale-session guard still fails the subscription-count assertion. See [fixture review](regression-fixtures.md) and [machine-readable evidence](regression-fixtures.json).

The complete saved source snapshot was replayed without candidate repairs through the formal version 0.0.2 Harbor entrypoint. It earns reward 1: 25/25 behavior cases, 2,108 original regression passes, 50 existing skips, zero failures and the stable auth test passed. Its historical version 0.0.1 reward remains 0 in the preserved original record. At that version 0.0.2 correction, the public instruction, image, behavioral verifier, reference implementation and alternative were unchanged. This fixes test validity without changing task scope or establishing a new difficulty estimate.

**R4 — prompt and representation fairness, resolved in version 0.0.3.** The statement now reads as a first-person coding request, reduced from 950 to 550 words. It retains interrupted execution, partial Bash effects, whole-operation conflict rejection, restart consistency, interrupted recovery, ancestry and execution gating. No storage strategy, algorithm, source location or test construction is disclosed.

Checkpoint `entryId` and `sessionId` fields, list order and a particular RPC success payload are no longer mandatory. Their former indirect assertions are replaced by actual rollback and exact effective-message comparisons; checkpoint discovery uses public ID differences. Conflict rejection still requires unchanged files and conversation, and now also exercises a successful retry after the conflicting edit is removed. A preflight conflict may report `ready` or `blocked`; neither permits partial application. Independent review caught a draft change that split direct multi-request rollback into single steps; direct multi-request rollback and conversation equality were restored before the final matrix. The interrupted draft run is not acceptance evidence.

All 25 scenario identities and the original regression inventory remain required. The new `minimal-checkpoint-metadata` positive control differs only in public representation and shares the Oracle's recovery mechanism; it is not claimed as a third independent algorithm. It passes the same full entrypoint. The materially different blob-journal implementation and saved Astra answer also pass; all eight unchanged negative controls remain rejected. This is a fairness and wording change, not a lowered behavioral bar or a new solve-rate estimate.

**Regression determinism — resolved with a narrow exception and mandatory counterpart.** An unchanged Base auth-cache path can return an old credential when immediate equal-length writes have identical revision metadata. The diagnostic probe observed 166 such stale results in 200 Base fixtures, all and only with equal revisions; different-length writes produced none in 200 fixtures. The original Base test file itself passed all three bounded reruns, so it is not described as having failed there. The unchanged negative-control test reproduced the exact assertion failure. See [timestamp evidence](base-auth-timestamp-evidence.json).

The original test still runs. Only its exact named `AssertionError`, old/new message and source location are tolerated; missing/skipped/error/timeout or other failure signatures remain failures. Ten direct matcher challenges confirmed that scope. A separate equivalent test uses a different-length new credential and must pass its two-reader, cancellation, shared-lock and release assertions. All 12 version 0.0.2 trials passed 2,108 original tests with 50 existing skips, zero failures and no use of this exception. The policy and its historical diagnostic evidence are unchanged; it does not exempt a rollback defect or broadly disable an auth regression.

## Evidence integrity and limits

[artifact-audit.json](artifact-audit.json) records strict-evidence success: five checks, zero errors/warnings, 32 runtime artifact identities, image identity and all eleven patch applications. Its recorded evidence SHA matches the current E2E evidence, and every canonical runtime hash was independently compared with the current files. Prepared Harbor inputs are intentionally recorded separately: preparation adds only the retained-image binding to `[environment]`; control trials also receive the selected complete patch and corresponding solve launcher. These are explicit harness transformations, not unrecorded source changes.

This correction performed no new model inference; it reused one complete saved answer. One passing answer is not a population solve-rate estimate. The image and supervisor remain unchanged, so earlier image-audit and observer-probe evidence is retained rather than presented as newly executed. The changed instruction and verifier are bound to fresh version 0.0.3 Harbor results. Assurance covers the stated local Linux filesystem/process-termination contract and the exercised behavioral/control matrix; it does not extend to excluded power loss, concurrent writers, external service effects or every possible adversarial encoding. Executable changes require affected validation to be rerun; documentation-only evidence updates are tracked separately.

Review method: `ai-infra-bench-task-review` with the complete ten-dimension rubric. Skill SHA-256: `290cba688d869a08b494f40104d20b3cc39c38a737887c4b2a9c035a5dd21915`; rubric SHA-256: `71ac1af37abf18ee2963c0df09ddb6337bcfbf8dea4144c06d0446ba8e0ce8a7`.

Version 0.0.2 post-rollout method: `ai-infra-bench-rollout-review`, skill SHA-256 `767fe719670c4a10753d7643cddbbab9c73f111c025f2d09fe03a6cf72a22f1f`, with a separate reviewer performing actual fixture preparation, targeted TUI mutations and raw formal-trial checks.

## Final delivery review

The README uses the same task overview, environment, verifier table, validation
table, layout, build/run instructions and evaluation-limits structure as the
other Pi task. It distinguishes completed local validation from pending image
publication. Detailed fixture and review history stays in validation records.

The delivery retains the environment inputs, verifier, reference implementation,
Base-applicable controls and their reproducible validation evidence. Shared
repository files are unchanged. Personal identifiers, private host addresses,
credentials, host-specific filesystem paths, caches and scratch outputs were
not found in the retained task files. Container paths such as `/workspace/pi`
and `/opt/pi-baseline/` are documented runtime interfaces.

The final instruction and all 32 runtime inputs match the version 0.0.3 control evidence. All 13 formal trials use this final runtime snapshot; documentation and evidence updates are separately bound by the artifact manifest. The task version and Git history identify this revision for branch review. The retained image has no published repository digest; publication must establish a pullable immutable reference and validate it.
