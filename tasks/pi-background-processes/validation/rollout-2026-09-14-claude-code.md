# Real-agent rollout, 2026-09-14 (local, linux/arm64)

Note: this rollout ran against the 14-case contract, before the `bash`
override (silent commands move to the background; `output` wake) was added
later the same day. Scores below are out of 14; the suite now has 15 cases
(two `bash` cases added, the merged-wake case removed).

First live rollout of the task through Harbor 0.22.0. Purpose: prove the agent
half of the pipeline (credentials, egress, trajectory capture, verifier on a real
submission) and look for judge defects that the Oracle and the negative controls
cannot reveal.

| Item | Value |
|---|---|
| Agent | claude-code 2.1.270, preinstalled in a derived image (`ai-infra-bench/pi-background-processes:rollout-cc`) |
| Model | claude-opus-5 |
| Auth | Claude subscription OAuth (`CLAUDE_FORCE_OAUTH=1`), no API key |
| Network | agent phase `public` behind the host proxy; verifier phase `no-network` (sidecar deny-all) |
| Budget | agent timeout multiplier 0.05 (30 min); the agent finished on its own in 25 min |
| Trajectory | 82 turns, 81 tool calls (64 Bash, 9 Edit, 5 Write, 3 Read), 87.6 k output tokens, 8.1 M cached input tokens, USD 8.09 by the CLI's own accounting |
| Submission | `examples/extensions/background-processes/{index,manager,log-store}.ts` + README (1.4 k lines), 18 new unit tests, two doc-table rows; no existing test file touched |
| Reward (frozen verifier) | **0** |

The Harbor orchestrator was killed by host memory pressure while the agent was
running; the container kept going, so the verifier was executed by hand inside
that container with the sidecar switched to deny-all, exactly the `tests/test.sh`
sequence Harbor runs. Artifacts (trajectory, agent diff, verifier logs) are under
`~/ai-infra-scratch/harbor-jobs/rollouts/salvaged-verifier/`.

## Verifier result on the submission

| Layer | Result |
|---|---|
| PASS_TO_PASS | pass: 2158 baseline cases, 2175 candidate (17 new), 0 regressed, only the 4 recorded environmental failures |
| Lifecycle | 3/3 pass (process exit, SIGTERM, durable records) |
| Contract | 9/14 pass |

Contract failures, classified:

| # | Case | Cause | Verdict |
|---|---|---|---|
| 6 | error and exit in one window coalesce into a single wake | The submission hands each wake to `pi.sendMessage` as it fires and relies on pi's steering queue; two messages reach the agent in the same turn instead of one merged message. | **Case removed** (2026-09-14, after review): it regulated the implementation (merge before `sendMessage`) rather than an observable outcome; two back-to-back messages carry the same information and cause no extra interruption. The contract now allows either form and only forbids repeating a reason within a window. The matching control `wake-per-reason-no-coalescing` was dropped with it. |
| 7 | bg_kill escalates to SIGKILL, removes grandchildren and wakes once | The submission disables wakes on `bg_kill`. The contract said both "exit wakes exactly once ... whether it exited on its own or was killed" and "nothing wakes the agent ... after `bg_kill`". | **Contract contradiction.** Fixed in `instruction.md`: `bg_kill` does not suppress the exit wake. |
| 12, 13, 14 | wake after session replacement; first-fire order; log flood paging | `bg_run` refused with "pi is shutting down". The harness disposed the session-replacement runtime with `runtime.dispose()`, which emits `session_shutdown` with `reason: "quit"`; the submission treats "quit" as process exit (correct for a real pi) and refuses further work in the same worker process. | **Harness defect.** Fixed in `tests/bg_support.ts`: the runtime is torn down with `session.dispose()` and no process-level quit is announced. |

After the fixes the same submission scores 12/14 on the contract suite (cases 6
and 7 still fail), lifecycle 3/3, PASS_TO_PASS pass; reward stays 0.
Re-verification logs: `~/ai-infra-scratch/recheck-agent-init/`.

A first re-verification in a container whose PID 1 was a bare `sleep` showed
two extra lifecycle failures and a different failure in case 7: orphaned
grandchildren were never reaped and the harness's `pidAlive` (a `kill(pid, 0)`
probe) kept reporting the zombies as alive. Harbor's containers run `sh -c
"sleep infinity"`, whose shell reaps them, so the frozen runs were unaffected,
but `pidAlive` now also reads `/proc/<pid>/stat` and treats zombies as gone.

## Changes made to the task from this rollout

1. `instruction.md`: the `bg_kill` sentence no longer contradicts the
   exit-wake rule, and the coalescing rule states that "delivery" means the
   agent receiving the message.
2. `tests/bg_support.ts`: runtime teardown no longer emits a process-level
   `quit` between tests.
3. `tests/test.sh` + `tests/baseline-pins.json`: the in-image PASS_TO_PASS baseline
   is verified against pins (Base case inventory digest, skipped-set digest,
   failure cap, allowed environmental failures) before it is compared, closing the agent-writable-baseline gap.
   (A first version pinned the file's sha256; that broke across image rebuilds
   and platforms and was replaced the same day.)
4. `tests/bg_support.ts`: `pidAlive` treats zombie processes as gone.

All four change the verifier or the contract, so Base, Oracle, and the
negative controls were rerun through Harbor afterwards (see
`controls-plan.md`).

## Pipeline lessons

- Harbor's egress sidecar (gost transparent proxy with SNI sniffing) passes
  direct TLS to allowlisted hosts but hangs HTTP `CONNECT` to a forward proxy.
  To use a host proxy, run the agent phase `public` and keep the verifier
  phase `no-network`; `tools/local_agent_rollout.sh` does this.
- Harbor installs claude-code with curl during the environment baseline; on
  the sidecar that download was reset. Preinstalling the agent in a derived
  image makes Harbor skip installation.
- A subscription OAuth access token from the local keychain expires in hours
  and cannot refresh inside the container; `claude setup-token` gives a
  long-lived one for repeated runs.
