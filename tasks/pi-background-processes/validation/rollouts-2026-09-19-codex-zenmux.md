# Real-agent rollouts, 2026-09-18/19: Codex CLI through ZenMux, three models, two runs each (local, linux/arm64)

Instruction 0.0.4. Agent: Harbor's built-in `codex` agent (codex-cli 0.153.0 preinstalled in a `:rollout-codex` image derived from the task image), agent user `node`, agent timeout multiplier 0.15 (90 min cap; every run finished on its own). The CLI talks to ZenMux's Responses API through a custom model provider (`--ak config=<codex config.toml>`: `model_provider = "zenmux"`, `wire_api = "responses"`, 1M context window; the key is forwarded as `OPENAI_API_KEY` and never appears on a command line). Provider and model were confirmed from each container's Codex session record (`session_meta.model_provider = zenmux`, `turn_context.model`), not assumed: a first attempt with the host's ChatGPT login ran OpenAI's gpt-6-astra instead and was stopped (`...gpt-6-astra...-INVALID-interrupted`, not counted). Launched with `tools/local_agent_rollout.sh` (`ROLLOUT_HARBOR_ARGS`) through the host proxy; agent phase public, verifier phase no-network.

| Model | Harness | Result |
|---|---|---|
| deepseek/deepseek-v4.1-flash | revision 4 | **1/2** |
| openai/gpt-5.6-luna | revision 5 | **0/2** |
| z-ai/glm-5.3-flashx | revision 5 | **0/2** |

Harness revision 4 and 5 score the same behaviour cases; revision 5 decides scope by content hashes and runs the submission's own tests separately. In all four revision 5 runs of this task `scope_exit_code` and `candidate_tests_exit_code` are 0: the new checks did not reject a genuine submission that added its extension, a README and a test file. The revision 4 submissions were not re-graded on revision 5.

## deepseek/deepseek-v4.1-flash, run 1: reward **1**

| Item | Value |
|---|---|
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-background-processes--codex--deepseek-v4.1-flash--x0.15--20260918-234635` |
| Agent phase | 2026-09-18T15:46Z to 16:18Z (31 min), no exception |
| Trajectory | 184 shell commands, 10 file-change items, 36 agent messages; 16.7M input tokens (16.4M cached), 192k output |
| Submission | 2665 added lines; `M packages/coding-agent/docs/extensions.md`, `M packages/coding-agent/examples/extensions/README.md`, `?? packages/coding-agent/examples/extensions/background-processes/README.md`, `?? packages/coding-agent/examples/extensions/background-processes/index.ts`, `?? packages/coding-agent/examples/extensions/background-processes/log-store.ts`, `?? packages/coding-agent/examples/extensions/background-processes/manager.ts`, `?? packages/coding-agent/test/background-processes-extension.test.ts` |
| Layers | contract 15/15, lifecycle 3/3, PASS_TO_PASS pass (tolerated: 1 pinned environmental case), scope_exit_code 0 |

Clean pass. Four files (`index.ts`, `manager.ts`, `log-store.ts`, README) plus one new test; it also edited two tracked docs (`docs/extensions.md`, `examples/extensions/README.md`), which the scope rule allows.

## deepseek/deepseek-v4.1-flash, run 2: reward **0**

| Item | Value |
|---|---|
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-background-processes--codex--deepseek-v4.1-flash--x0.15--20260919-005407` |
| Agent phase | 2026-09-18T16:54Z to 17:29Z (35 min), no exception |
| Trajectory | 231 shell commands, 0 file-change items, 27 agent messages; 26.5M input tokens (26.1M cached), 211k output |
| Submission | 3137 added lines; `M packages/coding-agent/examples/extensions/README.md`, `?? core`, `?? packages/coding-agent/examples/extensions/background-processes/README.md`, `?? packages/coding-agent/examples/extensions/background-processes/foreground-capture.ts`, `?? packages/coding-agent/examples/extensions/background-processes/index.ts`, `?? packages/coding-agent/examples/extensions/background-processes/log-store.ts`, `?? packages/coding-agent/examples/extensions/background-processes/process-manager.ts`, `?? packages/coding-agent/test/background-processes-extension.test.ts` |
| Layers | contract 15/15, lifecycle 2/3, PASS_TO_PASS pass (tolerated: 1 pinned environmental case), scope_exit_code 0 |

Failed cases:

- lifecycle: `SIGTERM to the pi process stops managed processes`: timed out waiting for managed process tree gone after SIGTERM

Genuine defect. `installShutdownHandlers()` registers `process.on("exit")` and a `SIGINT` handler only; there is no `SIGTERM` handler, so a SIGTERM ends pi with the managed tree still alive (`timed out waiting for managed process tree gone after SIGTERM`). The code comment shows the model reasoned about signal-exit and SIGINT and simply never covered SIGTERM, which the instruction names. A stray `core` file was left in the checkout (not penalised).

## openai/gpt-5.6-luna, run 1: reward **0**

| Item | Value |
|---|---|
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-background-processes--codex--gpt-5.6-luna--x0.15--20260919-121110` |
| Agent phase | 2026-09-19T04:11Z to 04:33Z (22 min), no exception |
| Trajectory | 96 shell commands, 43 file-change items, 10 agent messages; 14.3M input tokens (14.1M cached), 59k output, $0.40 as reported by Harbor |
| Submission | 1092 added lines; `?? packages/coding-agent/examples/extensions/background-processes/README.md`, `?? packages/coding-agent/examples/extensions/background-processes/index.ts`, `?? packages/coding-agent/test/background-processes-extension.test.ts` |
| Layers | contract 14/15, lifecycle 0/3, PASS_TO_PASS pass, scope_exit_code 0, candidate_tests_exit_code 0 |

Failed cases:

- contract: `ready wakes once and is delivered after the running tool batch`: expected 6 to be less than 5
- lifecycle: `pi process exit stops managed processes and their grandchildren`: timed out waiting for managed process tree gone after pi exit
- lifecycle: `SIGTERM to the pi process stops managed processes`: timed out waiting for managed process tree gone after SIGTERM
- lifecycle: `a later pi process resumes the session and reads finished records`: expected undefined to be 'line 1 started' // Object.is equality

Genuine defects. Cleanup hangs only on `pi.on("session_shutdown")` with `event.reason === "quit"`; there is no process `exit` or signal handler, so neither a headless pi ending nor SIGTERM stops the tree (2 lifecycle cases). The third lifecycle case reads `undefined` where the first log line of a finished record should be: records written by the first process are not readable by a later one. Contract: the ready wake lands after 6 entries where the case requires fewer than 5 (`expected 6 to be less than 5`); not root-caused.

## openai/gpt-5.6-luna, run 2: reward **0**

| Item | Value |
|---|---|
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-background-processes--codex--gpt-5.6-luna--x0.15--20260919-125025` |
| Agent phase | 2026-09-19T04:50Z to 05:06Z (16 min), no exception |
| Trajectory | 55 shell commands, 20 file-change items, 8 agent messages; 8.8M input tokens (8.7M cached), 46k output, $0.26 as reported by Harbor |
| Submission | 1167 added lines; `?? packages/coding-agent/examples/extensions/background-processes/README.md`, `?? packages/coding-agent/examples/extensions/background-processes/index.ts`, `?? packages/coding-agent/test/background-processes-extension.test.ts` |
| Layers | contract 14/15, lifecycle 1/3, PASS_TO_PASS pass, scope_exit_code 0, candidate_tests_exit_code 0 |

Failed cases:

- contract: `ready wakes once and is delivered after the running tool batch`: expected 6 to be less than 5
- lifecycle: `SIGTERM to the pi process stops managed processes`: Test timed out in 30000ms. If this is a long-running test, pass a timeout value as the last argument or configure it globally with "testTimeout".
- lifecycle: `a later pi process resumes the session and reads finished records`: child exited (code 1, signal null) before writing /tmp/pi-bg-verifier-akxO8f/second.json: file:///workspace/pi/packages/coding-agent/test/__verifier__/pi_child.mjs:76 if (hit.isError) throw new Error(`${toolName} errored

Genuine defects. The `SIGTERM` listener calls `stopAll()` and never ends the process (the `SIGINT` one does `process.exit(130)`), so with its own listener installed pi survives SIGTERM and the case times out at 30 s: the same family as the grok-4.6 failures on 0.0.1 to 0.0.3. In the resume case the second pi process exits 1 on a tool error while reading the finished records. Same contract failure as run 1 with the same numbers (`expected 6 to be less than 5`); two identical misses by one model while deepseek, grok and the Oracle pass make the sentence about wake delivery after the running tool batch worth a wording review.

## z-ai/glm-5.3-flashx, run 1: reward **0**

| Item | Value |
|---|---|
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-background-processes--codex--glm-5.3-flashx--x0.15--20260919-162009` |
| Agent phase | 2026-09-19T08:20Z to 08:22Z (2 min), no exception, no API error |
| Trajectory | 15 shell commands, 0 file-change items, 3 agent messages; 0.5M input tokens (0.5M cached), 7k output |
| Submission | 0 added lines; nothing |
| Layers | contract 0/15, lifecycle 0/3, PASS_TO_PASS pass, scope_exit_code 0, candidate_tests_exit_code 0 |

Failed cases (first four):

- contract: `registers bg_run, bg_logs, bg_list, bg_kill and bg_watch`: missing tool bg_run: expected [ 'read', 'bash', 'powershell', …(6) ] to include 'bg_run'
- contract: `bg_run returns a running record and bg_logs pages output in order`: tool bg_run returned an error: Tool bg_run not found
- contract: `bg_logs bounds a page to 64 KB and serves the newest lines by default`: tool bg_run returned an error: Tool bg_run not found
- contract: `exit wakes an idle agent exactly once with the exit code`: tool bg_run returned an error: Tool bg_run not found
- ... and 14 more

The model ended its own turn after two minutes: 15 exploratory commands, a last message "Design is settled ... I'm adding the extension now.", then `turn.completed` with no file written. No API error (no 402, no `turn.failed`). Nothing was submitted, so every behaviour case fails on a missing `bg_run`; PASS_TO_PASS and scope pass trivially. A valid verdict on the model in a one-shot headless run, not an infrastructure failure: the quota-interrupted attempt of the same model an hour earlier (`...-152323-INVALID-zenmux-quota-402`, not counted) had worked for 14 minutes and reached contract 11/15 before ZenMux answered 402.

## z-ai/glm-5.3-flashx, run 2: reward **0**

| Item | Value |
|---|---|
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-background-processes--codex--glm-5.3-flashx--x0.15--20260919-164616` |
| Agent phase | 2026-09-19T08:46Z to 09:06Z (20 min), no exception, no API error |
| Trajectory | 110 shell commands, 0 file-change items, 11 agent messages; 16.9M input tokens (16.7M cached), 54k output |
| Submission | 1007 added lines; `M packages/coding-agent/CHANGELOG.md`, `?? packages/coding-agent/examples/extensions/background-processes/README.md`, `?? packages/coding-agent/examples/extensions/background-processes/index.ts`, `?? packages/coding-agent/test/background-processes-extension.test.ts` |
| Layers | contract 5/15, lifecycle 0/3, PASS_TO_PASS pass, scope_exit_code 0, candidate_tests_exit_code 0 |

Failed cases (first four):

- contract: `bg_run returns a running record and bg_logs pages output in order`: tool bg_logs returned an error: EBADF: bad file descriptor, read
- contract: `bg_logs bounds a page to 64 KB and serves the newest lines by default`: tool bg_logs returned an error: EBADF: bad file descriptor, read
- contract: `ready wakes once and is delivered after the running tool batch`: expected 6 to be less than 5
- contract: `bg_kill escalates to SIGKILL, removes grandchildren and wakes once`: expected undefined to be 'killed' // Object.is equality
- ... and 9 more

Genuine defects across the board: `bg_logs` fails with `EBADF: bad file descriptor, read`, killed processes are not recorded as `killed`, processes are lost across a new session or fork, a wake does not reach the replacement session, and the log-flood case times out. The ready wake is delivered after the assistant's next text instead of before the next model request (`expected 6 to be less than 5`), the same miss as both gpt-5.6-luna runs; the instruction states the rule explicitly ("after the current assistant turn has finished executing its tool calls and before the next model request"), so this is a model error, not an ambiguity. It also edited the tracked `CHANGELOG.md` (allowed by the scope rule).

A first glm-5.3-flashx chain the same day was cut off by ZenMux (`402 Payment Required: subscription quota limit`) 14 minutes into its first run; Harbor still graded the half-finished work and reported `UnknownApiError`. Both of its jobs are marked `-INVALID-zenmux-quota-402` and are not counted. A run that ends with `exception_info` is not a verdict.
