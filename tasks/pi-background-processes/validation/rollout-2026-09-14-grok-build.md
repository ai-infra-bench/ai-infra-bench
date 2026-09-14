# Real-agent rollout 2, 2026-09-14: Grok Build (local, linux/arm64)

Second live rollout, on the current contract (15 contract cases, 3 lifecycle
cases, `bash` override included).

| Item | Value |
|---|---|
| Agent | Harbor `grok-build` via the custom subclass `tools/harbor_agents/grok_build_oauth.py` (same install, flags, trajectory and watchdog; authenticates with the host's `grok login` session instead of `XAI_API_KEY`) |
| Model | grok-4.6 (xAI `grok` CLI 1.0.30, headless `--single --always-approve --output-format streaming-json`, web search disabled by Harbor default) |
| Network | agent phase `public` behind the host proxy; verifier phase `no-network` |
| Budget | agent timeout multiplier 0.1 (1 h); the agent finished on its own in 33 min |
| Trajectory | 151 tool calls (69 read_file, 32 search_replace, 24 grep, 12 run_terminal_command, 5 write, 4 todo_write, 4 list_dir), 82.4 k output tokens (77.6 k reasoning), 6.2 M cached input tokens |
| Submission | `examples/extensions/background-processes/{index,process-manager,log}.ts` + README (about 1.5 k lines), 12 new unit tests, no existing test file touched |
| Reward | **0** |

## Verifier result

| Layer | Result |
|---|---|
| PASS_TO_PASS | pass: 2158 baseline, 2170 candidate (12 new), 0 regressed |
| Contract | **15/15 pass**, including both `bash` override cases |
| Lifecycle | 2/3: "SIGTERM to the pi process stops managed processes" timed out (30 s) |

The submission implemented everything the contract asks for, including the
silent-command auto-background and the `output` wake, and lost on one
lifecycle clause.

## Root cause of the lifecycle failure (reproduced)

The trajectory was replayed into a container (5 `write` + 32
`search_replace` calls apply cleanly; the reconstruction is kept next to the
job under `~/ai-infra-scratch/grok-submission/`). Sending `SIGTERM` to a
headless pi process running the submission:

- the managed process group is stopped correctly (child and SIGTERM-ignoring
  grandchild gone within the 5 s SIGTERM-then-SIGKILL window),
- but the pi process itself never exits (still sleeping 6 min later).

The submission's handler re-raises the signal only when it is the sole
`SIGTERM` listener:

```ts
this.sigtermHandler = () => {
	this.stopAllSync();
	if (process.listeners("SIGTERM").length === 1 && this.sigtermHandler) {
		process.removeListener("SIGTERM", this.sigtermHandler);
		process.kill(process.pid, "SIGTERM");
	}
};
```

A bare pi SDK session already has one `SIGTERM` listener, installed by the
`signal-exit` package in pi's dependency tree, and that listener uses the same
rule: it re-emits the signal only if it is the only listener. Two polite
listeners defer to each other and nobody terminates the process. Interactive
pi would have masked this (its own handler shuts down and exits), so the bug
only shows in headless embeddings, which is exactly what the lifecycle suite
runs. The contract says: "Handling `SIGTERM`/`SIGINT` must not keep pi alive:
after the managed groups are stopped, pi still terminates (re-raise the signal
or exit non-zero)". The Oracle removes its own listener and re-raises
unconditionally, which lets `signal-exit` take the exit.

Verdict: a real defect in the submission on a clause the contract states
explicitly; no judge change.

The reconstructed submission, with the three signal handlers changed to drop
all listeners and re-raise unconditionally (the only edit), became the task's
correct alternative implementation
`alternative-class-manager-sparse-index.patch` (Harbor reward 1). It differs
from the Oracle in module structure (class-based manager, separate log store
with a sparse line index), wake bookkeeping (per-process state, no global
order queue), and delivery timing (25 ms coalescing timer instead of turn-end
flushing), so it is a genuine second solution rather than a reformatting.

## Comparison with rollout 1 (claude-code + claude-opus-5, 14-case contract)

| | claude-opus-5 | grok-4.6 |
|---|---|---|
| Wall time | 25 min | 33 min |
| Tool calls | 81 | 151 |
| Output tokens | 87.6 k | 82.4 k (77.6 k reasoning) |
| PASS_TO_PASS | pass | pass |
| Contract | 12/14 (one case since removed; remaining miss: `bg_kill` exit wake) | 15/15 |
| Lifecycle | 3/3 | 2/3 (SIGTERM deferral) |
| Reward | 0 | 0 |

Both submissions are one behavior away from reward 1, on different clauses.

## Pipeline notes

- Session-based auth for grok: the CLI accepts a copied `~/.grok/auth.json`
  in headless mode; Harbor's built-in agent insists on `XAI_API_KEY`, so the
  subclass satisfies that check with a placeholder and drops it before
  executing. The host session file was not modified by the run.
- `tests/test.sh` now writes `/logs/verifier/agent-changes.patch` (git status
  and diff of the agent's changes) so a rollout's submission is kept without
  reconstructing it from the trajectory. This does not affect reward.
