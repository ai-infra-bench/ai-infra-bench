# Plan Mode verifier behavior map

Base: `d981de1229ef899957bbe968bc8dcda02a21f477` (Pi 0.85.1).

All candidate extension loading uses `DefaultResourceLoader` and the default export from the public task directory. Model responses come from pi's first-party faux provider. Inputs, tool dispatch, event settlement, tool selection, custom entries and custom messages are handled by the real `AgentSession`. Only the human UI selection is supplied by a verifier UI adapter; it does not implement plan state. No test imports candidate helper functions or inspects its private variables/persistence schema.

The semantic boundary is: normal user input or model tool call -> real Pi extension dispatch, plan transition, tool dispatch and session persistence -> public state, model-visible execution request, filesystem effects and independent-process resume. The provider supplies deterministic model output; it does not implement approval, tool restrictions or resume.

## Public observations and representation freedom

State observations require the five public fields `sessionId`, `mode`, `planId`, `revision` and `steps`. The verifier validates their presence and relevant types, then projects those fields without supplying defaults. Extra fields, including changing diagnostic metadata, are allowed and do not enter state equality checks. Approval is observed through `mode: "approved"` and the retained identity, revision and exact steps; `approvedRevision` is not required. Normal state must identify the current session, have mode `normal` and contain no steps, but its inactive plan ID and revision sentinels are not fixed. Active plan IDs must be nonempty strings. Submitted revisions must strictly increase; no initial revision or increment size is prescribed.

For successful `plan_submit`, at least one structured state from result details or JSON tool-result text must equal the subsequently observed public status. Neither duplicate output channels nor equal extra fields are required. Controls still append exactly one `plan-control-result` entry containing `operation`, boolean `ok` and valid public `state`; recognized operations must identify the requested operation. Missing or unknown operations have no fixed sentinel. Rejections may use any error-code vocabulary or diagnostic structure.

The `hasReason` helper only checks for a nonblank string recursively within raw result metadata outside `operation`, `ok` and `state`. It establishes the presence of a diagnostic candidate, not the usefulness or truth of arbitrary natural-language text. Rejection safety is independently checked through failed approval, unchanged public state and tool selection, provider call counts, and absence of approval execution; no specific reason text substitutes for those observations.

| Case | Public behavior | Independent observation |
| --- | --- | --- |
| C00 | Candidate worker privilege boundary | POSIX worker UID/GID 65534; protected reward/checker/baseline write-open denied; root-parent signaling permission denied |
| C01 | Complete normal status, read-only control | Required public state fields and successful status entry; current Pi session ID, normal mode and empty steps; provider call counter unchanged |
| C02 | Enter/re-enter and least active read subset | Public state identity/revision; actual dispatcher tool selection and exact restored original set |
| C03 | Explicit submission, exact strings, monotonic revision | At least one real structured tool-result channel equals public status; exact supplied strings and plan identity retained; each submission, including an identical draft, strictly increases the revision |
| C04 | Reject malformed/empty/blank steps | Real failed tool result; authoritative state unchanged. Inputs use noncoercible objects and blank strings after Pi schema conversion; numbers/scalar strings can normalize to valid steps and are not falsely classified as errors. |
| C05 | Invalid controls are consumed with rejection | Exactly one custom result per input, `ok: false` and a diagnostic candidate; state and tools unchanged; no provider calls |
| C06 | RPC identity/revision approval checks | Empty draft, wrong session or plan, and old or future revision are separately rejected; state, tools and provider count unchanged; no approval custom message |
| C07 | Source-sensitive entry and approval | Real input source extension is forbidden through default session.prompt path; state, tools and provider count unchanged |
| C08 | Prose/tool output is data, not authority | Faux assistant prose and real read tool file payload; no state/approval change |
| C09 | No writing in planning | Actual built-in write/edit/bash and custom side-effect tool attempts; filesystem unchanged; provider sees only allowed tools |
| C10 | Exactly one approved execution request | Captured plan-approved identity/steps; real file side effect and provider call count; repeated approval idempotent |
| C11 | New cycle and planning-only submit | Fresh plan ID, planning mode and empty draft without a fixed revision sentinel; outside-mode tool submission rejected; prior-cycle approval cannot change the new draft, tools or provider count |
| C12 | Existing /plan, shortcut, and progress display | Normal slash-command/shortcut paths never restore writing by toggling; real approved execution produces DONE markers, and /todos distinguishes pending, partial, and complete progress without changing plan state, tools, or provider count |
| C13 | Busy entry cannot interrupt active tool batch | Real waiting tool with explicit release barrier; no state/tool mutation or additional provider call |
| C14 | Busy approval and pending-input boundary | Real read dispatch paused by a verifier hook; real follow-up queue; rejection preserves draft, complete tool selection and provider count; no approval |
| C15 | Stale interactive Execute cannot approve a newer revision | Real earlier review dialog held while a later RPC-driven model turn submits a strictly newer revision; returning the old selection leaves the newer draft unapproved and the full restricted tool set unchanged |
| C16 | Interactive Execute matches control approval | Submitted steps appear in the review UI; real Execute approves the captured snapshot, restores the original tools, and sends one actual provider request containing its identity and exact steps; message details and file side effect agree |
| C17 | Stay/Refine retain planning restrictions | UI choices through host adapter; no authoritative steps/revision change without explicit submission; complete restricted tool set unchanged |
| L01 | Normal planning resume and tool restoration | Different Node PID, same real session file; all five public state fields retained exactly; original tools restored after later approval |
| L02 | Approved resume does not replay; state beats --plan | Different Node PID; zero provider calls during open/status; side-effect file remains exactly one marker |
| L03 | Fresh sessions isolate foreign state; fresh --plan | Candidate-generated custom state entries copied via public `SessionManager.appendCustomEntry`, without relying on their private schema; new session cannot consume old approval |
| L04 | Persisted normal resume ignores --plan | Real assistant persisted before idle close; different Node PID and same normal state, zero provider calls |

The resume fixtures first obtain an assistant message so pi actually publishes the session file, then close only at idle. No crash, in-flight shutdown, fork/tree/reload, or arbitrary hostile in-process extension semantics are asserted.

L03 intentionally constructs a foreign-state input through the public custom-entry API. It exercises the explicit requirement to reject state bearing another session ID; it is not evidence of spontaneous cross-session leakage during normal resume. L01/L02/L04 are the normal independent-process resume evidence.

## PASS_TO_PASS and integrity

`p2p-files.txt` is generated from the pinned Base tree. The intentionally changed `plan-mode-extension.test.ts` is excluded; plan utility tests and every other original coding-agent test remain. Candidate-added tests are outside the original-suite selection. `base-manifest.json` freezes every tracked Base file except the allowed plan extension directory and that explicitly mutable original test.

Scope verification also inventories nonignored untracked files using Git and rejects additions outside the two permitted directories. Ignored Base build artifacts are not treated as candidate additions. New symlinks in an allowed directory may not escape those directories.

`baseline-pins.json` must be generated from a new run of this precise old-suite selection on the prepared Base image. It pins the complete case/outcome map; no old background-process task pins or old run result are reused. The independent Python validator rejects missing/extra/duplicate cases and changed skip sets. An environmental Base failure, if any, is individually pinned and documented rather than generalized into a failure budget.

The prepared image may record the complete new Base suite including the four old `plan-mode-extension.test.ts` cases. Both baseline pin generation and candidate comparison validate raw XML completeness first, then project out precisely that basename's cases. No other testcase is excluded. Candidate invocation already excludes that file using the pinned Base file list.

Contract/lifecycle reward requires zero command errors and exact verifier-owned testcase inventories with no skips/failures/errors. Independent Python self-tests exercise early exit, omitted cases, duplicate cases, skipped cases and contradictory aggregate counts. A child process exiting zero without its observed state output is a test failure.

## Privilege boundary

The initial candidate account may modify only the allowed source/test directories and dedicated Vite caches. The verifier validates frozen source and additions before running JavaScript, then makes allowed source/test directories root-owned and removes/recreates candidate Vite caches. A trusted root-owned copy of verifier scripts controls reward and XML checks. Vitest runs its frozen configuration and reporters as root, using only fork workers. A trusted Node preload drops supplementary groups, GID and UID to 65534 at the pinned Vitest 4.1.9 `dist/workers/forks.js` worker entry; candidate extension code and fixture subprocesses run with that identity. Root-owned `/tests`, `/opt/pi-baseline` and `/logs/verifier` cannot be written by those workers. The coding-agent package directory itself uses root-owned sticky mode 1777 so frozen SettingsManager tests can create and remove their own cwd-local scratch directories; existing root-owned source/configuration entries stay protected from replacement. Worker HOME is a fresh owned temporary directory. C00 verifies the actual process and filesystem permissions without modifying a trusted artifact.

This prevents a worker from directly replacing the independent result artifacts or killing its root coordinator. It does not claim to prevent arbitrary monkeypatching of assertions or other JavaScript objects inside the same worker. The benchmark evaluates the public implementation contract, not a complete hostile-code sandbox.

## Qualification status

The verifier still owns the same 18 contract cases and 4 lifecycle cases. The
representation changes above do not remove the tool-policy, stale-review, busy,
approved-request-context, execution-once or cross-process-resume scenarios.
`minimal-public-state` is a positive representation control; the separate
`alternative-event-journal` remains the materially different implementation.
See `wrong-controls.md` for their distinct purposes.

Formal results belong in `author-results.md` and `e2e-evidence.json`, matched to
their executable hashes and statement snapshot. The 2026-09-17 formal matrix and four saved
candidate replays completed against the revised snapshot. All 14 author cases
returned their expected rewards, and the saved candidates retained their prior
grades. Static alignment and helper probes are distinguished from those Harbor
results in the evidence.

An original AuthStorage assertion was reproduced on untouched Base. Its exact
fingerprint is conditionally accepted while the complete 2,154-case inventory
and original skips remain required. Raw failures stay visible; unrelated errors
are not accepted. See `baseline-environment.md` for the evidence and policy.

During prior validation, an independent lifecycle review derived the normal-session resume scenario
before consulting the existing case inventory: a saved normal session resumed
with `--plan` must remain normal. It exposed a reference-implementation defect;
the corrected snapshot and event-journal implementations subsequently passed
this cross-process challenge, now retained as L04. This records the independent
challenge without prescribing either implementation's persistence schema.
