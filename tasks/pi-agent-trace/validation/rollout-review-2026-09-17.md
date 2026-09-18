# Rollout review, 2026-09-17: pi-agent-trace (0.0.6, verifier revision 2)

Review made with `.agents/skills/ai-infra-bench-rollout-review` (SKILL.md `03f8b4851f91018a`, reporting.md `2b895c1509d9b9f6`, differential-cases.md `982a418e7ef9add3`), applied by the curator session that also ran the rollouts. Evidence file at review time: `validation/e2e-evidence.json` `817efb697197745e`.

## Mode, scope, prerequisites

- **Validation mode:** Oracle-based. Oracle `solution/oracle.patch` (17/17), 27 negative controls, 4 alternative implementations (`alt-grok-run5`, `alt-grok-run8-fixed`, `alt-opus-run1` expected 1; `alt-grok-run1/3/4` expected 0), local Harbor matrix 31/31 (`~/ai-infra-scratch/at-matrix-11.log`), CI x64 validation green on PR #94.
- **Prerequisite gap:** no ten-dimension initial task review is on record for this task. Per the skill, every finding below is **provisional** until that review exists; the contract reconstruction used instead is `validation/controls-plan.md` (verifier QA matrix) plus the instruction itself.
- **Scope:** all 13 recorded attempts (`real_agent_rollouts`), grouped by the task revision each one ran against. Rollouts of one label are not comparable across revisions; the instruction changed materially at 0.0.2, 0.0.3, 0.0.4 (stated edges) and 0.0.5 (contract-only rewrite), the verifier at revisions 1, 3 and the two of 2026-09-16.
- **Authorization:** the user authorized every new rollout, every verifier and instruction change, and the commits and pushes; this document records them, it did not initiate them.

## Artifact inventory

| Rec | Label | Rev | Job (local time) | Patch | Trajectory | Verifier junit | result.json | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | grok run 1 | 0.0.1 / verifier 1 | 20260915-033648 | yes | yes | yes | yes | |
| 2 | grok run 2 | 0.0.1 / verifier 1 | 20260915-040535 | yes | yes | yes | yes | |
| 3 | opus 1 | 0.0.2 | 20260915-123704 | yes | yes | yes | yes | recorded late (2026-09-16) |
| 4 | grok run 3 | 0.0.3 / verifier 3 | 20260915-151314 | yes | yes | yes | yes | |
| 5 | grok run 4 | 0.0.3 / verifier 3 | 20260915-154957 | yes | yes | yes | yes | |
| 6 | grok run 5 | 0.0.4 | 20260915-174541 | yes | yes | yes | yes | |
| 7 | grok run 6 | 0.0.4 | 20260915-182437 | yes | yes | yes | yes | |
| 8 | grok run 7 | 0.0.5 | 20260915-195647 | yes | yes | yes | yes | AgentTimeoutError at 3600 s; proxy incident |
| 9 | grok run 8 | 0.0.5 | 20260915-212903 | yes | yes | yes | yes | rerun after a preflight failure |
| 10 | grok run 9 | 0.0.6 | 20260916-105659 | yes | yes | yes | yes | |
| 11 | grok run 10 | 0.0.6 | 20260916-133523 | yes | **no** | yes | **no** | salvaged: Harbor wrapper killed by host memory pressure, agent finished in its orphaned container, verifier run by hand there (proxy unset, network disconnect not confirmed); no watchdog |
| 12 | grok run 11 | 0.0.6 | 20260916-141903 | yes | yes | yes | yes | |
| 13 | opus 2 | 0.0.6 | 20260916-161837 | yes | yes | yes | yes | |

Common identities: model ids `grok-4.6` (xAI grok CLI 1.0.30, headless) and `claude-opus-5` (claude-code 2.1.270, subscription OAuth); model revisions **not recorded** by either CLI. Harbor 0.22.0; image `ai-infra-bench/pi-agent-trace:local` = image id `713cd734…` (linux/arm64 local build of the same Dockerfile bytes as the amd64 canonical image); Base `d981de12`; agent phase `public` behind the host proxy, verifier phase `no-network`; agent timeout multiplier 0.1 through run 9, 0.15 after. The evidence records were re-ordered on job timestamps during this review (Harbor's `started_at` is local-naive and one salvaged record had a UTC stamp, which had swapped the labels of records 10 and 11).

## Per-attempt table (original scores; verifier of the time)

Metrics: agent minutes from `result.json` `agent_execution`; steps and tool calls from `trajectory.json` (Harbor ATIF; tool calls are the CLI's top-level tool invocations); files and added lines from `agent-changes.patch` (tracked + untracked, excluding node_modules/dist; all submissions are new files, deletions 0).

| Rec | Rev | Agent min | Steps | Tool calls | Files | Added | Contract | Lifecycle | P2P | Reward |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.0.1 | 27.3 | 60 | 181 | 3 | 1480 | 5/6 | 1/1 | pass | 0 |
| 2 | 0.0.1 | 23.0 | 64 | 179 | 4 | 1475 | 6/6 | 1/1 | pass | 1 |
| 3 | 0.0.2 | 25.9 | 111 | 121 | 4 | 1758 | 11/11 | 2/2 | pass | 1 |
| 4 | 0.0.3 | 34.5 | 67 | 196 | 4 | 1889 | 12/13 | 2/2 | pass | 0 |
| 5 | 0.0.3 | 35.9 | 50 | 147 | 3 | 1877 | 12/13 | 2/2 | pass | 0 |
| 6 | 0.0.4 | 32.6 | 65 | 193 | 3 | 1723 | 15/15 | 2/2 | pass | 1 |
| 7 | 0.0.4 | 28.3 | 57 | 154 | 4 | 1766 | 15/15 | 2/2 | pass | 1 |
| 8 | 0.0.5 | 60.0 (timeout) | 42 | 131 | 3 | 1821 | 1/15 | 0/2 | pass | 0 |
| 9 | 0.0.5 | 33.4 | 65 | 186 | 4 | 1890 | 13/15 | 2/2 | pass | 0 |
| 10 | 0.0.6 | 34.3 | 80 | 210 | 3 | 1685 | 10/15 | 1/2 | pass | 0 |
| 11 | 0.0.6 | 41 (no watchdog) | n/r | n/r | 3 | 2027 | 13/15 | 2/2 | pass | 0 |
| 12 | 0.0.6 | 25.4 | 44 | 138 | 3 | 1672 | 12/15 | 2/2 | pass | 0 |
| 13 | 0.0.6 | 27.6 | 95 | 100 | 4 | 2070 | 15/15 | 2/2 | pass | 1 |

## Findings

Confirmed means reproduced in the task image from the recorded `agent-changes.patch` with the verifier of the stated revision (repro logs under `~/ai-infra-scratch/repro-run8/`).

1. **Judge precision, millisecond clock assumed (verifier revision 1).** Rec 1: run end 5 ns into the next millisecond and a turn start 1 ns after the event timestamp were rejected by `Date.now()`-based equality. Contract: sub-millisecond digits are the implementation's. Attribution: overstrict assertion. Remediation: both assertions allow sub-millisecond digits; the unmodified submission passes and is `alt-grok-run1` (validation case). Confirmed (curator record of 2026-09-15).
2. **Judge precision, shared nanosecond shutdown timestamp (verifier revision 3).** Recs 4 and 5: the shutdown case required chat, turn and run closes to share one nanosecond value. Attribution: overstrict assertion. Remediation: a window observed by the verifier around `dispose()`; unmodified submissions pass and are `alt-grok-run3/4`. Confirmed.
3. **Overstrict assertion, exact attribute maps.** Rec 12, third failure: a compaction end line carrying two extra `pi.usage.cache_*` attributes was rejected by `toEqual` on tool and compaction attribute maps, while the instruction never declares the table exhaustive and the chat map was already checked as a subset. Remediation (2026-09-16, revision "listed keys"): `toMatchObject` plus explicit absence checks for a failed compaction; rec 12 re-verified 13/15, reward unchanged 0 because of finding 6. Confirmed.
4. **Judge precision, nanosecond windows against the verifier clock.** Rec 13's clock is `Date.now()` at load, truncated to the millisecond, plus an `hrtime` offset, so it reads up to 1 ms behind the verifier; the shutdown window's exact lower bound failed 2 of 8 local repeats (16 µs), and a per-case `turn.start >= previousTurn.end` at nanosecond precision failed 1 of 9 (2 µs) although the shared invariant already compared in milliseconds. Remediation (2026-09-16, revision 2): 1 ms slack below verifier-clock windows; the two mixed-clock in-trace comparisons at millisecond granularity; a review of all 17 time comparisons is recorded in `README.md`. After it: rec 13 8/8 full-suite repeats, Oracle 4/4, recs 9–12 fail identically. Confirmed. The Harbor pass of rec 13 stands; under revision 1 it carried roughly a one-in-four chance of a spurious 0.
5. **Agent defects on the contract-only instruction (0.0.5/0.0.6), all reproduced:**
   - rec 9: concurrent tool end lines written in pi's persistence order (100 ms call after the 300 ms call, `endTimeUnixNano` decreased); shutdown closed `pi.run` with no attributes. A 54-line fix passes every layer (`alt-grok-run8-fixed`, expected 1).
   - rec 10: every compaction exported twice (entry scan closed the span, then the handler opened and closed a second one on the same entry); streaming chat closed at shutdown with a placeholder end time equal to its start; concurrent tool end times clamped to keep the file monotonic (100 ms call reported as 306 ms).
   - rec 11: concurrent order again; after `/reload` the new process re-claimed the first prompt's user entry and the first chat entry.
   - rec 12: the chat span's assistant-entry lookup never consumes the entry it used (three chats on one entry in the steering case).
   Each maps to an explicit sentence of the instruction (end order, timestamps from the clock at the event, exactly-once entry coverage, reload continuity). Attribution: agent defect.
6. **Rec 8 inconclusive.** AgentTimeoutError at 3600 s (multiplier 0.1) with the extension mid-refactor; the host proxy node was switched at 12:41Z and the grok CLI logged 401 retries from 12:43Z. Attribution: insufficient environment (proxy) plus budget; no capability claim. The chained rollout then exited at the proxy preflight and was rerun as rec 9.
7. **Rec 11 collection limitation.** No Harbor result.json or trajectory; verifier run by hand in the orphaned container after the agent exited; network disconnect attempted but not confirmed (the suite is offline by construction). Failures reproduced from the patch, so the defect findings stand; the record is marked `salvaged`.

**Reward-1 attempts.** Rec 13: trajectory read in full (95 steps; only the extension directory, its README, the examples README and one new test file written; pi's own suite, `tsgo` and `biome` run by the agent; no access to `/tests`, `/logs`, node_modules or the baseline; no environment or fixture detection in the source); traces of the hard cases dumped and inspected (true end times, end order kept, shutdown closes carry the run attributes). No hack observed in the reviewed material. Recs 2, 3, 6 and 7 passed earlier revisions with prescribed designs; their trajectories were reviewed by the curator at the time but **not re-screened for hacks in this review** (limitation). **No curator-side independent behavioral challenge exists for this task** (unlike pi-background-processes); the trace dumps are a partial substitute. Recommended follow-up: an `independent_probe` on a scenario absent from the suite (for example a tool that spawns a sub-agent which itself runs a parallel tool batch).

## Campaign synthesis (contract-only revisions 0.0.5/0.0.6)

| Behavior (contract sentence) | rec 9 | rec 10 | rec 11 | rec 12 | rec 13 |
|---|---|---|---|---|---|
| end lines in end order under parallel tools | fail | pass (by clamping) | fail | pass | pass |
| tool end times from the clock at the event | pass | fail (clamped) | pass | pass | pass |
| shutdown run close carries turn_count and entry id | fail | pass | pass | pass | pass |
| shutdown close time inside the dispose window | pass | fail (placeholder) | pass | pass | pass (after revision 2) |
| one compaction span per compaction entry | pass | fail | pass | pass | pass |
| each assistant entry referenced by exactly one chat | pass | pass | pass | fail | pass |
| entries resolved anew after reload | pass | pass | fail | pass | pass |

Five submissions, six distinct defects, no defect shared by two grok runs except the parallel-tool order (recs 9 and 11). The failures cluster on one skill: reconciling pi's event order with its persistence order. Two grok runs were within two cases of passing; claude-opus-5 passed once. These are development observations on an evolving revision, not a population pass rate.

No rollout-derived scored case was promoted; the alternative patches are validation cases with the reward they earn.

## Verdict and state

- **Retain**, with the targeted repairs already applied and validated (verifier revisions of 2026-09-16, 0.0.6 sentence). Rewards recorded before each repair are kept as recorded and annotated; rerun rewards are listed separately in the evidence assessments.
- **Provisional** until a ten-dimension initial task review is on record; also missing: an independent behavioral challenge, a hack re-screen of the four early passes, and the CI image publication step.
- Commit/push state: everything is on branch `agent/pi-agent-trace` (PR #94, stacked on #92, CI green); this review and the evidence re-ordering are committed with it.

## Update, 2026-09-18: the harness revision 3 rollout (reward 0)

Reviewed with the same skill files; task snapshot: 0.0.6, harness revision 3 (`[agent].user = "node"`, root-owned toolchain, `scope_exit_code`), tree at `25bbca7` (PR #94), local image `ai-infra-bench/pi-agent-trace:local` = `sha256:96703b6c…` (linux/arm64 build of the revision 3 Dockerfile). One authorized attempt (rec 14, "grok run 12"); the same day's `INVALID-cred-nonroot`, `INVALID-session-expired-cancelled` (2), `INVALID-no-proxy` and `INVALID-interrupted` job directories never reached a scored state and are excluded.

**Artifact inventory:** job `pi-agent-trace--GrokBuildOAuth--grok-4.6--x0.15--20260918-013035`, trial `pi-agent-trace__EKQfGes`: `result.json`, `agent/trajectory.json`, `agent/grok-build.txt`, `verifier/agent-changes.patch`, all JUnit reports and summaries, `test-stdout.txt`; `scope.log` absent (no out-of-scope change). Model `grok-4.6` (grok CLI 1.0.34), revision not recorded; Harbor 0.22.0; agent phase public behind the host proxy, verifier no-network; setup 2.7 min, agent 44.9 min, verifier 0.8 min; 72 steps (67 `source=agent`), 177 top-level tool calls (93 `read_file`, 42 `grep`, 21 `search_replace`, 9 `run_terminal_command`); final state 3 new files, +1827/−0 (`examples/extensions/agent-trace/{index.ts,README.md}`, `test/agent-trace-extension.test.ts`), no tracked file modified. The agent ran its own test file, biome, `tsc` on the examples project and the whole coding-agent suite before stopping; its final message describes the deliverable as complete.

| Rec | Rev | Agent min | Steps | Tool calls | Files | Added | Contract | Lifecycle | P2P | Scope | Reward |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 14 | 0.0.6 / harness 3 | 44.9 | 72 | 177 | 3 | 1827 | 13/15 | 2/2 | pass | clean | 0 |

**Replay through the grading path (diagnostic, not a new reward):** the candidate patch (sha256 `6e8d0456bed1ff2b…`, `tests/` tar sha256 `e091ee379c22f0aa…`, both computed before the run) applied as `node` in the revision 3 image and `tests/test.sh` run as root reproduces `reward.json` byte-for-byte in its exit codes and the same two contract failures. Hack screen: one read of pi's `vitest.config.ts`; nothing sensitive, no network, no history commands; no hack observed.

**Finding R3-1 (confirmed, agent defect): `service.version` exported as `"0.0.0"`.** Contract: explicit. The instruction names the package version in its first paragraph (`@earendil-works/pi-coding-agent` 0.85.1) and requires `service.version` = the coding-agent package version; the verifier asserts the literal. Cause in the final code: `codingAgentVersion()` does `createRequire(import.meta.url)("@earendil-works/pi-coding-agent/package.json")` inside a `try` that falls back to `"0.0.0"`. The package's `exports` map does not expose `./package.json`, so Node throws `ERR_PACKAGE_PATH_NOT_EXPORTED` (reproduced in the image from both the extension directory and the test directory) and the fallback is silently taken. The normal path is the public API: `packages/coding-agent/src/index.ts` re-exports `VERSION` from `src/config.ts` (which the Oracle uses). The candidate's own test asserts only `typeof … === "string"`, so its 11 local tests could not catch it. Attribution: agent defect (requirement explicit, value discoverable through the public API, failure in candidate behavior). Remediation: none to the task.

**Finding R3-2 (confirmed, agent defect, recurring): concurrent tool end lines out of end order.** Contract: explicit ("End lines appear in the order the spans ended: `endTimeUnixNano` never decreases from one end line to the next"). Reproduced with the candidate on the verifier's concurrent case (a 300 ms and a 100 ms `echo` call in one assistant message) and the trace file dumped in write order: line 7 is the end of the 300 ms call (end +302 ms), line 8 the end of the 100 ms call (end +111 ms). Mechanism in the final code: `tool_execution_end` queues the end record with its end timestamp and a resolver for the `toolResult` entry; `flushPending` writes each queued end as soon as its own entry resolves and keeps the others pending. the queue held the fast call first (its recorded end is the earlier one), yet the slow call's `toolResult` entry became visible on the branch at an earlier flush than the fast call's (pi appends the results of one parallel batch in call order), so the slow call's end line went out first and the fast call's followed at a later flush, with its earlier `endTimeUnixNano`. Correct implementations keep the queue in end order and write a pending end only after every earlier-ended pending span can be written (the Oracle and the three accepted alternatives do; `alt-grok-run8-fixed` is the 54-line fix of the same defect in rec 9). The order in which pi makes the entries visible is not stated in the instruction and does not need to be: the instruction fixes the observable (monotone end lines), the agent's own "parallel tools" test did not assert it, and the agent-harness reference classifies an unstated pi fact that the instruction does not contradict as an agent attribution. Same defect as recs 9 and 11 (the third valid grok attempt to fail on it).

**Attribution summary:** reward 0 is correct; both failures are candidate defects against explicit clauses; no overstrict assertion, fixture or environment cause; scope check did not fire; the non-root agent completed a full-length run with no credential, permission or install failure, which is the harness-revision 3 question this rollout was authorized to answer.

**Differential cases:** none proposed. R3-2 is already a scored case with a validated positive (`alt-grok-run8-fixed`) and negatives (recs 9, 11, 14); R3-1 is covered by the basic prompt case. The recurring failure is evidence about the model, not about missing coverage.

**State after this update:** evidence record rec 14 (commit `58cc054`) matches the job artifacts; documentation only, evidence-consistency audit rerun. Grok on pi-agent-trace at 0.0.6: 0/4 valid attempts (recs 10, 11, 12 and 14; rec 11 salvaged without a watchdog), opus 1/1 (rec 13).
