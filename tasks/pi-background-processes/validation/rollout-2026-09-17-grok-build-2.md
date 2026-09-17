# Real-agent rollout 6, 2026-09-17: Grok Build on the 0.0.4 instruction, second run (local, linux/arm64)

| Item | Value |
|---|---|
| Agent | Harbor `grok-build` via `tools/harbor_agents/grok_build_oauth.py` (host `grok login` session) |
| Model | grok-4.6, agent timeout multiplier 0.15; finished on its own in 26 min (03:41Z to 04:07Z); two harmless `Failed to fetch models` 401 warnings at start (the placeholder API key), no other network error |
| Trajectory | 134 tool calls (68 read_file, 26 grep, 17 search_replace, 8 run_terminal_command, 5 list_dir, 5 write, 4 todo_write, 1 get_command_or_subagent_output) |
| Submission | `examples/extensions/background-processes/{index,manager}.ts` + README, one new unit test file, no existing test touched |
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-background-processes--GrokBuildOAuth--grok-4.6--x0.15--20260917-114030` |
| Reward | **1** |

## Verifier result

| Layer | Result |
|---|---|
| PASS_TO_PASS | pass |
| Contract | 15/15 |
| Lifecycle | 3/3 |

Re-verified in the task image under the final harness (drain settle, idle waits,
VITEST-free child environment): 18/18, and again through Harbor as the matrix control. The signal handler removes its own
listener and re-raises the signal unconditionally, so a headless pi terminates; no
environment-based guard. First clean grok-4.6 pass of this task; kept as the expected-1
control `alt-grok-0.0.4-clean-pass`.
