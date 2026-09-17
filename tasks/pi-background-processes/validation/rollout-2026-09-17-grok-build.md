# Real-agent rollout 5, 2026-09-17: Grok Build on the 0.0.4 instruction (local, linux/arm64)

| Item | Value |
|---|---|
| Agent | Harbor `grok-build` via `tools/harbor_agents/grok_build_oauth.py` (host `grok login` session) |
| Model | grok-4.6, agent timeout multiplier 0.15; finished on its own in 31 min (03:07Z to 03:38Z), no 401 or network error |
| Trajectory | 175 tool calls (83 read_file, 37 search_replace, 29 grep, 10 run_terminal_command, 7 write, 4 todo_write, 4 list_dir, 1 get_command_or_subagent_output) |
| Submission | `examples/extensions/background-processes/{index,manager,log-file,process-tree,types}.ts` + README, one new unit test file, no existing test touched |
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-background-processes--GrokBuildOAuth--grok-4.6--x0.15--20260917-110610` |
| Reward | **0 as recorded, 1 under the corrected harness** |

## Verifier result as recorded

| Layer | Result |
|---|---|
| PASS_TO_PASS | pass |
| Contract | **15/15** |
| Lifecycle | 1/3: "pi process exit stops managed processes and their grandchildren" and "SIGTERM to the pi process stops managed processes" both timed out waiting for the managed tree to disappear |

## What was really wrong (reproduced)

This time pi *does* exit after `SIGTERM` (the 0.0.4 sentence had its effect: the handler
removes its listener and re-raises, with `process.exit` as the fallback). What survived was
the managed tree, and the reason is one line in the submission:

```ts
installHooks(): void {
	...
	if (process.env.VITEST) return;
```

The extension skips its exit and signal hooks when it believes it runs under vitest,
presumably so that its own in-process unit tests do not install process-wide handlers.
The lifecycle suite spawns a *separate* pi process and gave it `...process.env`, so the
runner's `VITEST` variable leaked into a child that is meant to be a real headless pi,
and the hooks were never installed there. A real pi process never carries that variable.

Harness fix (0.0.4, harness revision 2): the child environment no longer inherits `VITEST*`.
With that, this submission passes the lifecycle suite 3/3 (two repeats), the Oracle still
passes 3/3, and the two real-submission expected-0 controls still fail their lifecycle case.

Verdict: harness realism defect, not an agent error. The guard itself is a smell (an
extension that disables its safety hooks on an environment variable), but the contract does
not forbid it and production behaviour is correct. Recorded as the first grok-4.6 pass of
this task; the unmodified submission is kept as the expected-1 control `alt-grok-0.0.4-vitest-guard`.
