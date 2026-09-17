# Rollout review, 2026-09-17: pi-background-processes (0.0.4, harness revision 2)

Review made with `.agents/skills/ai-infra-bench-rollout-review` (SKILL.md `03f8b4851f91018a`, reporting.md `2b895c1509d9b9f6`, differential-cases.md `982a418e7ef9add3`), applied by the curator session that also ran the rollouts. Evidence file at review time: `validation/e2e-evidence.json` `fb50540405940886`.

## Mode, scope, prerequisites

- **Validation mode:** Oracle-based. Oracle 15/15 + 3/3, 12 negative controls, 1 curator-written alternative implementation, 4 real-submission controls (two expected 1, two expected 0), local Harbor matrix 19/19 (`~/ai-infra-scratch/bg-matrix-0.0.4-rev2.log`), CI x64 validation green on PR #92, curator-side independent challenge `validation/independent_challenge.py` (4 cases not in the suites).
- **Prerequisite gap:** no ten-dimension initial task review is on record; findings are **provisional**. Contract reconstruction: `validation/behavior-map.md` plus the instruction.
- **Scope:** every job directory under `~/ai-infra-scratch/harbor-jobs/rollouts/pi-background-processes--*` (12), of which 6 are recorded rollouts, 4 are aborted or invalid attempts and 2 are partially recorded. Instruction revisions: 0.0.1 (specification style, mechanism hints), 0.0.2 (hints removed), 0.0.3 (issue voice), 0.0.4 (SIGTERM outcome made unmistakable); verifier cases unchanged throughout, harness revised twice on 0.0.4 (drain/idle waits; VITEST-free child environment).
- **Authorization:** as for pi-agent-trace.

## Artifact inventory

| Job (local time) | Attempt | Patch | Trajectory | Verifier junit | result.json | Notes |
|---|---|---|---|---|---|---|
| claude-code x0.05 20260914-142633 | aborted | no | no | no | yes | NetworkConnectionError before the agent phase |
| claude-code x0.05 20260914-143048 | aborted | no | yes | yes | yes | UnknownApiError, 0 steps |
| claude-code x0.05 20260914-144627 | rollout 1 (0.0.1) | **no** | **no** | yes | **no** | 25 min per the note; the note does not record the job identity; contract 9/14 on the verifier of the time, 12/14 after judge fixes |
| GrokBuildOAuth x0.1 20260914-175711 | rollout 2 (0.0.1) | **no** (reconstructed from the trajectory into `alternative-class-manager-sparse-index`) | yes | yes | yes | contract 15/15, lifecycle 2/3 |
| claude-code x1 20260915-110236 | final experiment bg #1 or #2 | yes | **no** | yes | **no** | contract 14/15, lifecycle 3/3; identity not recorded in the notes |
| claude-code x1 20260915-120639 | final experiment bg #1 | yes | yes | yes | yes | contract 8/15 (two real bg_logs paging bugs, five cross-session failures), lifecycle 3/3 |
| claude-code x1 20260915-130401 | invalid | yes | no | yes | no | agent killed at 5 min by a salvage bug |
| claude-code x1 20260915-141051 | stopped | no | no | no | no | stopped by the user |
| GrokBuildOAuth x0.15 20260916-192425 | rollout 3 (0.0.2) | yes | yes | yes | yes | |
| claude-code x0.15 20260916-211021 | rollout 4 (0.0.3) | yes | yes | yes | yes | |
| GrokBuildOAuth x0.15 20260917-110610 | rollout 5 (0.0.4) | yes | yes | yes | yes | |
| GrokBuildOAuth x0.15 20260917-114030 | rollout 6 (0.0.4) | yes | yes | yes | yes | |

Common identities: `grok-4.6` (grok CLI 1.0.30), `claude-opus-5` (claude-code 2.1.270); model revisions not recorded. Harbor 0.22.0; image `ai-infra-bench/pi-background-processes:local` (arm64 local build), Base `d981de12`; agent phase `public` behind the host proxy, verifier `no-network`.

**Evidence limitation:** the two 2026-09-14/15 notes do not name their job directories, and two of those jobs lack a tracked patch or a trajectory. Findings from that period are cited from the notes, not re-reproduced here.

## Per-attempt table (original scores)

| Attempt | Rev | Agent min | Tool calls | Files | Added | Contract | Lifecycle | P2P | Reward |
|---|---|---|---|---|---|---|---|---|---|
| rollout 1 opus (144627) | 0.0.1 | 25 (note) | 81 (note) | n/r | n/r | 9/14 | 3/3 | pass | 0 |
| rollout 2 grok (175711) | 0.0.1 | 29.9 | 151 | n/r | n/r | 15/15 | 2/3 | pass | 0 |
| bg #1 opus (120639) | 0.0.1 | 28.9 | 91 | 7 | 2772 | 8/15 | 3/3 | pass | 0 |
| opus (110236) | 0.0.1 | n/r | n/r | 7 | 2320 | 14/15 | 3/3 | pass | 0 |
| rollout 3 grok (192425) | 0.0.2 | 30.6 | 153 | 6 | 1999 | 15/15 | 2/3 | pass | 0 |
| rollout 4 opus (211021) | 0.0.3 | 31.8 | 121 | 10 | 2336 | 10/15 | 2/3 | pass | 0 |
| rollout 5 grok (110610) | 0.0.4 | 31.3 | 175 | 8 | 2295 | 15/15 | 1/3 | pass | 0 |
| rollout 6 grok (114030) | 0.0.4 | 26.1 | 134 | 5 | 2135 | 15/15 | 3/3 | pass | 1 |

## Findings

1. **SIGTERM must still end pi (lifecycle case).** Failed by rollout 2 (handler re-raises only as the sole listener; `signal-exit` in pi's dependency tree defers the same way), rollout 3 (handler never re-raises or exits), rollout 4 (`listenerCount > 1` deferral). Contract: explicit in every revision ("pi still terminates"); 0.0.1 additionally named a mechanism, 0.0.2/0.0.3 did not, 0.0.4 states the outcome for interactive and headless pi and says it never keeps running. Attribution: agent defect (confirmed for 3 and 4 by reproduction; for 2 by the curator note). The wording change is a versioned contract clarification, not a test change; rollouts 5 and 6 on 0.0.4 both end pi.
2. **Harness fragility: drain timing (rollout 4, four contract cases).** The submission reports an exit 100 ms after the process died (pipes drained) and batches reasons 10 ms; the drain ran one prompt and disposed; the wake went to the next test's session with a triggered turn, as the contract requires, and that test's first prompt hit a busy agent. Attribution: broken fixture/scorer (harness assumption). Remediation (harness revision 1): drain waits 300 ms and for idle; verifier prompts wait for idle. Under it the four cases pass; Oracle 18/18; wake-related negative controls still fail. Confirmed.
3. **Harness realism: VITEST leaked into the child pi (rollout 5, two lifecycle cases).** `childEnv()` spread `process.env`; the submission skips its exit hooks under `VITEST`. Attribution: insufficient environment realism (a real pi never carries the variable); the guard is a smell but not a contract violation. Remediation (harness revision 2): strip `VITEST*`. Rollout 5 then 3/3 (two repeats), Oracle 3/3, the two expected-0 real controls still fail. Confirmed; **corrected reward 1**.
4. **Agent defect: auto-background path breaks after a reload (rollout 4).** `instanceof BackgroundedError` against a class from a re-loaded module identity; the stalled command returns a tool error in any session after the first. Contract: reload continuity and "exactly like one started with bg_run". Confirmed (fails after any preceding test, passes alone).
5. **Earlier findings cited from the notes (not re-reproduced):** rollout 1: two real `bg_logs` paging bugs and five cross-session failures from pinning storage to the first session; one contract contradiction (`bg_kill` vs the exit wake), one harness defect (`runtime.dispose()` announcing a process-level quit) and one case regulating implementation (merged wake messages) were fixed then. Judge precision of the pi-agent-trace kind did not occur here; the unstated-harness-fact class occurred twice (findings 2 and 3).

**Reward-1 attempts.** Rollout 6: workspace status shows only the extension directory, its README, the examples README and one new test file; trajectory commands flagged by the sensitive-path screen: one `tsgo` type check, nothing touching `/tests`, `/logs`, node_modules, the baseline or package files; no environment or fixture-name detection in the source; signal handler removes its listener and re-raises unconditionally. Independent challenge: 4/4 checks pass (relative cwd with a Unicode error pattern, intermittent output stays foreground, paging past the end, `bg_kill` on a finished process). Re-verified 18/18 in the image and as the Harbor control `alt-grok-0.0.4-clean-pass`. **No hack observed in the reviewed material.** Rollout 5 (corrected 1): same screen, one flag (the `VITEST` guard), independent challenge 4/4, kept as `alt-grok-0.0.4-vitest-guard`.

## Campaign synthesis

| Behavior | r1 opus | r2 grok | bg#1 opus | r3 grok | r4 opus | r5 grok | r6 grok |
|---|---|---|---|---|---|---|---|
| SIGTERM ends pi | pass | fail | pass | fail | fail | pass | pass |
| managed tree gone on pi exit | pass | pass | pass | pass | pass | fail (harness: VITEST) | pass |
| bg_logs paging / 64 KB bound | fail | pass | fail | pass | pass | pass | pass |
| cross-session listing and storage | fail | pass | fail | pass | pass | pass | pass |
| bash stall after a reload | n/a (case added later) | pass | pass | pass | fail | pass | pass |
| wake delivery under the drain | pass | pass | pass | pass | fail (harness) | pass | pass |

Before 0.0.4: 0 of 6 valid attempts, the SIGTERM clause failing in 3 of them with three different handlers. On 0.0.4: grok-4.6 2 of 2 (one after the harness fix). The reversal is concentrated on one clause whose outcome the instruction now states without ambiguity; it is evidence about that sentence, not a pass rate.

No rollout-derived scored case was promoted; real submissions were added as validation cases with the reward they earn.

## Verdict and state

- **Retain**, repairs applied and validated: instruction 0.0.2 → 0.0.4 (versioned, no mechanism hints), harness revisions 1 and 2, matrix 19/19, CI green.
- **Provisional** until the ten-dimension initial review is on record; the 2026-09-14/15 attempts are documented without job identities and partly without final artifacts (limitation); claude-opus-5 has not run on 0.0.4 (user deferred).
- Commit/push state: on branch `agent/pi-background-processes` (PR #92, CI green); this review is committed with it.
