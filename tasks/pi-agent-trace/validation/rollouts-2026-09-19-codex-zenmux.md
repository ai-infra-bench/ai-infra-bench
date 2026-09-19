# Real-agent rollouts, 2026-09-18/19: Codex CLI through ZenMux, three models, two runs each (local, linux/arm64)

Instruction 0.0.6. Agent: Harbor's built-in `codex` agent (codex-cli 0.153.0 preinstalled in a `:rollout-codex` image derived from the task image), agent user `node`, agent timeout multiplier 0.15 (90 min cap; every run finished on its own). The CLI talks to ZenMux's Responses API through a custom model provider (`--ak config=<codex config.toml>`: `model_provider = "zenmux"`, `wire_api = "responses"`, 1M context window; the key is forwarded as `OPENAI_API_KEY` and never appears on a command line). Provider and model were confirmed from each container's Codex session record (`session_meta.model_provider = zenmux`, `turn_context.model`), not assumed: a first attempt with the host's ChatGPT login ran OpenAI's gpt-6-astra instead and was stopped (`...gpt-6-astra...-INVALID-interrupted`, not counted). Launched with `tools/local_agent_rollout.sh` (`ROLLOUT_HARBOR_ARGS`) through the host proxy; agent phase public, verifier phase no-network.

| Model | Harness | Result |
|---|---|---|
| deepseek/deepseek-v4.1-flash | revision 4 | **1/2** |
| openai/gpt-5.6-luna | revision 5 | **0/2** |
| z-ai/glm-5.3-flashx | revision 5 | **0/2** |

Harness revision 4 and 5 score the same behaviour cases; revision 5 decides scope by content hashes and runs the submission's own tests separately. In all four revision 5 runs of this task `scope_exit_code` and `candidate_tests_exit_code` are 0: the new checks did not reject a genuine submission that added its extension, a README and a test file. The revision 4 submissions were not re-graded on revision 5.

## deepseek/deepseek-v4.1-flash, run 1: reward **1**

| Item | Value |
|---|---|
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-agent-trace--codex--deepseek-v4.1-flash--x0.15--20260919-002002` |
| Agent phase | 2026-09-18T16:20Z to 16:52Z (33 min), no exception |
| Trajectory | 198 shell commands, 2 file-change items, 26 agent messages; 23.2M input tokens (22.9M cached), 191k output |
| Submission | 1908 added lines; `M packages/coding-agent/examples/extensions/README.md`, `?? packages/coding-agent/examples/extensions/agent-trace/README.md`, `?? packages/coding-agent/examples/extensions/agent-trace/index.ts`, `?? packages/coding-agent/test/agent-trace-extension.test.ts` |
| Layers | contract 15/15, lifecycle 2/2, PASS_TO_PASS pass (tolerated: 1 pinned environmental case), scope_exit_code 0 |

Clean pass. Single-file extension plus README and one new test; also edited the tracked `examples/extensions/README.md` (allowed).

## deepseek/deepseek-v4.1-flash, run 2: reward **0**

| Item | Value |
|---|---|
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-agent-trace--codex--deepseek-v4.1-flash--x0.15--20260919-013123` |
| Agent phase | 2026-09-18T17:31Z to 18:05Z (34 min), no exception |
| Trajectory | 228 shell commands, 0 file-change items, 14 agent messages; 23.7M input tokens (23.4M cached), 200k output |
| Submission | 2159 added lines; `M packages/coding-agent/examples/extensions/README.md`, `?? packages/coding-agent/examples/extensions/agent-trace/README.md`, `?? packages/coding-agent/examples/extensions/agent-trace/index.ts`, `?? packages/coding-agent/test/agent-trace-extension.test.ts` |
| Layers | contract 14/15, lifecycle 2/2, PASS_TO_PASS pass (tolerated: 1 pinned environmental case), scope_exit_code 0 |

Failed cases:

- contract: `agent-trace contract > reload appends to the same file with the same trace id and no duplicate spans`: expected [ …(2) ] to deeply equal []

Genuine defect in the reload path: after `/reload` the spans written by the rebound extension reference a branch that misses its first entry (`chat: spans reference [7707113a, 81330dcc] but the branch has [17ed0ca1, 7707113a, 81330dcc]`; same for the steering run). Not root-caused in the code. Every other contract case and both lifecycle cases pass.

## openai/gpt-5.6-luna, run 1: reward **0**

| Item | Value |
|---|---|
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-agent-trace--codex--gpt-5.6-luna--x0.15--20260919-123525` |
| Agent phase | 2026-09-19T04:35Z to 04:49Z (13 min), no exception |
| Trajectory | 66 shell commands, 16 file-change items, 8 agent messages; 7.6M input tokens (7.4M cached), 44k output, $0.24 as reported by Harbor |
| Submission | 721 added lines; `?? packages/coding-agent/examples/extensions/agent-trace/README.md`, `?? packages/coding-agent/examples/extensions/agent-trace/index.ts`, `?? packages/coding-agent/test/agent-trace.test.ts` |
| Layers | contract 13/15, lifecycle 2/2, PASS_TO_PASS pass (tolerated: 1 pinned environmental case), scope_exit_code 0, candidate_tests_exit_code 0 |

Failed cases:

- contract: `agent-trace contract > runs started by an extension message are wakeups and runs queued at agent_end are continuations`: expected [ 'prompt', 'wakeup', 'prompt', …(1) ] to deeply equal [ 'prompt', 'wakeup', 'prompt', …(1) ]
- contract: `agent-trace contract > a quit while a run is streaming closes the open spans with status shutdown`: expected [ …(3) ] to deeply equal []

Genuine defects: the run-trigger sequence differs from the expected one in its fourth element (a run queued at `agent_end` is not classified as a continuation), and a quit while a run is streaming leaves three open spans without a `shutdown` end line. Not root-caused further. Shortest working session of the set (14 min, 66 commands).

## openai/gpt-5.6-luna, run 2: reward **0**

| Item | Value |
|---|---|
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-agent-trace--codex--gpt-5.6-luna--x0.15--20260919-130812` |
| Agent phase | 2026-09-19T05:08Z to 05:20Z (12 min), no exception |
| Trajectory | 36 shell commands, 17 file-change items, 7 agent messages; 7.8M input tokens (7.7M cached), 43k output, $0.24 as reported by Harbor |
| Submission | 767 added lines; `?? packages/coding-agent/examples/extensions/agent-trace/README.md`, `?? packages/coding-agent/examples/extensions/agent-trace/index.ts`, `?? packages/coding-agent/test/agent-trace-extension.test.ts` |
| Layers | contract 1/15, lifecycle 0/2, PASS_TO_PASS pass (tolerated: 1 pinned environmental case), scope_exit_code 0, candidate_tests_exit_code 0 |

Failed cases:

- contract: `agent-trace contract > a prompt with a tool call exports run, turn, chat and tool spans in OTLP/JSON tied to session entries`: expected [ 'line 1: bad traceId', …(12) ] to deeply equal []
- contract: `agent-trace contract > a failing tool and an error response mark tool, chat and turn spans ERROR while the run stays OK`: expected [ 'line 1: bad traceId', …(12) ] to deeply equal []
- contract: `agent-trace contract > runs started by an extension message are wakeups and runs queued at agent_end are continuations`: expected [ 'line 1: bad traceId', …(24) ] to deeply equal []
- contract: `agent-trace contract > manual and threshold compactions export root compaction spans tied to compaction entries`: expected [ 'line 1: bad traceId', …(7) ] to deeply equal []
- ... and 12 more with the same message

Format error that fails everything: the trace id is `createHash("sha256").update(id).digest("hex")`, 64 hex characters, while the instruction's export contract says `traceId`: 32 lowercase hex characters. Every exported line is rejected as `bad traceId`, hence contract 1/15 and lifecycle 0/2. The 12-minute session shows no step that checks the output against the stated format.

## z-ai/glm-5.3-flashx, run 1: reward **0**

| Item | Value |
|---|---|
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-agent-trace--codex--glm-5.3-flashx--x0.15--20260919-162356` |
| Agent phase | 2026-09-19T08:24Z to 08:44Z (21 min), no exception, no API error |
| Trajectory | 125 shell commands, 0 file-change items, 12 agent messages; 16.0M input tokens (15.8M cached), 71k output |
| Submission | 1027 added lines; `?? packages/coding-agent/examples/extensions/agent-trace/README.md`, `?? packages/coding-agent/examples/extensions/agent-trace/index.ts`, `?? packages/coding-agent/test/agent-trace-extension.test.ts` |
| Layers | contract 3/15, lifecycle 0/2, PASS_TO_PASS pass, scope_exit_code 0, candidate_tests_exit_code 0 |

Failed cases (first four):

- contract: `agent-trace contract > a prompt with a tool call exports run, turn, chat and tool spans in OTLP/JSON tied to session entries`: expected [ …(2) ] to deeply equal []
- contract: `agent-trace contract > a failing tool and an error response mark tool, chat and turn spans ERROR while the run stays OK`: expected [ …(2) ] to deeply equal []
- contract: `agent-trace contract > runs started by an extension message are wakeups and runs queued at agent_end are continuations`: expected [ …(6) ] to deeply equal []
- contract: `agent-trace contract > manual and threshold compactions export root compaction spans tied to compaction entries`: expected [ Array(1) ] to deeply equal []
- ... and 10 more

One structural error fails almost everything: chat spans are not children of the turn span (`chat <model> not nested in pi.turn` in every scenario), against the run > turn > chat/tool hierarchy the export contract lists. In addition wakeup runs do not carry the custom message's entry id (`entry undefined is not a custom message on the branch`), and a pi killed during a tool execution leaves the chat span `pending` instead of `toolUse`.

## z-ai/glm-5.3-flashx, run 2: reward **0**

| Item | Value |
|---|---|
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-agent-trace--codex--glm-5.3-flashx--x0.15--20260919-170825` |
| Agent phase | 2026-09-19T09:08Z to 09:18Z (9 min), no exception, no API error |
| Trajectory | 48 shell commands, 8 file-change items, 6 agent messages; 5.5M input tokens (5.3M cached), 37k output |
| Submission | 1089 added lines; `?? packages/coding-agent/examples/extensions/agent-trace/README.md`, `?? packages/coding-agent/examples/extensions/agent-trace/index.ts`, `?? packages/coding-agent/test/agent-trace-extension.test.ts` |
| Layers | contract 3/15, lifecycle 0/2, PASS_TO_PASS pass, scope_exit_code 0, candidate_tests_exit_code 1 |

Failed cases (first four):

- contract: `agent-trace contract > a prompt with a tool call exports run, turn, chat and tool spans in OTLP/JSON tied to session entries`: expected [ Array(1) ] to deeply equal []
- contract: `agent-trace contract > a failing tool and an error response mark tool, chat and turn spans ERROR while the run stays OK`: expected [ 'line 11: start after end', …(1) ] to deeply equal []
- contract: `agent-trace contract > runs started by an extension message are wakeups and runs queued at agent_end are continuations`: expected [ 'line 4: start after end', …(8) ] to deeply equal []
- contract: `agent-trace contract > manual and threshold compactions export root compaction spans tied to compaction entries`: expected [ 'line 22: start after end' ] to deeply equal []
- ... and 10 more

Different implementation, different structural errors: start lines are written after the matching end lines (`start after end`) in most scenarios, the live-update case sees `start:chat` where an `end:chat` should come first, an unwritable trace path throws into pi at `session_start` (`EEXIST ... mkdir`) instead of being reported once, and an aborted stream exits with code 2 instead of 1.

A first glm-5.3-flashx chain the same day was cut off by ZenMux (`402 Payment Required: subscription quota limit`) 14 minutes into its first run; Harbor still graded the half-finished work and reported `UnknownApiError`. Both of its jobs are marked `-INVALID-zenmux-quota-402` and are not counted. A run that ends with `exception_info` is not a verdict.
