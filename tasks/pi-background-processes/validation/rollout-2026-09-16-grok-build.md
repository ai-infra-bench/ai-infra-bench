# Real-agent rollout 3, 2026-09-16: Grok Build on the 0.0.2 instruction (local, linux/arm64)

First rollout on the 0.0.2 wording (outcomes and contract only, no mechanism hints).

| Item | Value |
|---|---|
| Agent | Harbor `grok-build` via `tools/harbor_agents/grok_build_oauth.py` (host `grok login` session) |
| Model | grok-4.6 (xAI `grok` CLI 1.0.30, headless) |
| Network | agent phase `public` behind the host proxy; verifier phase `no-network`; no 401 or network error in the CLI log |
| Budget | agent timeout multiplier 0.15 (90 min); the agent finished on its own in 31 min (11:25Z to 11:56Z) |
| Trajectory | 153 tool calls (69 read_file, 32 search_replace, 23 grep, 14 run_terminal_command, 6 write, 4 todo_write, 4 list_dir), 79.9 k output tokens, 6.9 M cached input tokens |
| Submission | `examples/extensions/background-processes/{index,manager,logs}.ts` + README (about 1.6 k lines), 22 new unit tests, no existing test file touched |
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-background-processes--GrokBuildOAuth--grok-4.6--x0.15--20260916-192425` |
| Reward | **0** |

## Verifier result

| Layer | Result |
|---|---|
| PASS_TO_PASS | pass, 0 regressed |
| Contract | **15/15 pass**, both `bash` override cases included |
| Lifecycle | 2/3: "SIGTERM to the pi process stops managed processes" timed out (30 s) |

## Root cause of the lifecycle failure (reproduced)

`agent-changes.patch` applied to the task image and the lifecycle suite rerun:
same single failure. The submission installs one listener per signal and stops
the managed processes in it, then does nothing else:

```ts
for (const signal of ["SIGTERM", "SIGINT", "SIGHUP"] as const) {
	process.on(signal, () => {
		stop();
	});
}
```

Installing a listener removes Node's default termination for that signal, so a
headless pi that receives `SIGTERM` stops its managed processes and then keeps
running; the verifier waits for the pi process to exit and times out. The 0.0.2
instruction states the requirement as an outcome: "Stopping them must not keep
pi alive: pi still terminates, by the signal or with a non-zero status."

Same clause as rollout 2 (2026-09-14, 0.0.1 wording: a handler that re-raised
only as the sole listener), different mistake: this one never re-raises at all.
Removing the mechanism hint "(re-raise the signal or exit non-zero)" did not
change what the model got wrong; it got the same clause wrong in a simpler way.

Verdict: a real defect on an explicitly stated clause; no judge change. The
submission is kept as the expected-0 control
`alt-grok-0.0.2-sigterm-listener.patch` (contract 15/15, lifecycle 2/3).
