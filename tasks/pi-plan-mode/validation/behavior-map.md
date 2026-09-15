# Plan Mode verifier behavior map

Base: `d981de1229ef899957bbe968bc8dcda02a21f477` (Pi 0.85.1).

All candidate extension loading uses `DefaultResourceLoader` and the default export from the public task directory. Model responses come from pi's first-party faux provider. Inputs, tool dispatch, event settlement, tool selection, custom entries and custom messages are handled by the real `AgentSession`. Only the human UI selection is supplied by a verifier UI adapter; it does not implement plan state. No test imports candidate helper functions or inspects its private variables/persistence schema.

| Case | Public behavior | Independent observation |
| --- | --- | --- |
| C00 | Candidate worker privilege boundary | POSIX worker UID/GID 65534; protected reward/checker/baseline write-open denied; root-parent signaling permission denied |
| C01 | Complete normal status, read-only control | Exact public state/custom entry; provider call counter unchanged |
| C02 | Enter/re-enter and least active read subset | Public state identity/revision; actual dispatcher tool selection and exact restored original set |
| C03 | Explicit submission, exact strings, monotonic revision | Real `plan_submit` result text JSON equals details; identical draft increments revision |
| C04 | Reject malformed/empty/blank steps | Real failed tool result; authoritative state unchanged. Inputs use noncoercible objects and blank strings after Pi schema conversion; numbers/scalar strings can normalize to valid steps and are not falsely classified as errors. |
| C05 | Invalid controls are consumed with typed rejection | Exactly one custom result per input; no provider calls |
| C06 | RPC identity/revision approval checks | Single-cause no_plan/plan_mismatch/stale_revision cases; no approval custom message |
| C07 | Source-sensitive entry and approval | Real input source extension is forbidden through default session.prompt path |
| C08 | Prose/tool output is data, not authority | Faux assistant prose and real read tool file payload; no state/approval change |
| C09 | No writing in planning | Actual built-in write/edit/bash and custom side-effect tool attempts; filesystem unchanged; provider sees only allowed tools |
| C10 | Exactly one approved execution request | Captured plan-approved identity/steps; real file side effect and provider call count; repeated approval idempotent |
| C11 | New cycle and planning-only submit | Fresh plan ID and reset state; outside-mode tool submission rejected |
| C12 | Existing /plan, shortcut, /todos compatibility | Normal slash-command/registered-shortcut host paths; repeated use never restores write access |
| C13 | Busy entry cannot interrupt active tool batch | Real waiting tool with explicit release barrier; no state/tool mutation |
| C14 | Busy approval and pending-input boundary | Real read dispatch paused by a verifier hook; real follow-up queue; no approval |
| C15 | Stale interactive Execute cannot approve revision 2 | Real v1 review dialog held, v2 submitted by later RPC-driven model turn, old selection returned |
| C16 | Interactive Execute matches control approval | Real UI selection; exact displayed revision becomes approved and performs real write |
| C17 | Stay/Refine retain planning restrictions | UI choices through host adapter; no authoritative steps/revision change without explicit submission |
| L01 | Normal planning resume and tool restoration | Different Node PID, same real session file; state exact; original tools restored after later approval |
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

The verifier owns 18 contract cases and 4 lifecycle cases. All 22 have passed in the protected-reporter / UID 65534 Oracle debug run, including the real-core stale UI trace and permission checks. Fresh Base P2P has also passed all 2,154 projected cases with 50 unchanged skips, and five original auth-storage file runs passed 26/26 each. A reused Oracle container separately showed a possible timestamp-sensitive upstream assertion; it has not reproduced in fresh Base and no exception was enabled. See `baseline-environment.md` for the complete evidence and limits. Final task acceptance depends on the root agent's fresh Harbor matrix, not on these component checks alone.
