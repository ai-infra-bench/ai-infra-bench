# Contract clause → verifier case

Contract clauses from `instruction.md` and the case that observes each one.
Cases are named exactly as in `tests/case_contract.py`. `traceProblems` in
`tests/at_support.ts` runs in every case: OTLP/JSON shape (one request, one
scope `pi.agent-trace`/`1`, one span per line; id formats; decimal-string
times; typed attribute values, each key once; status codes and messages),
resource attributes, a single trace id, non-decreasing `endTimeUnixNano`,
parents present in the file, strict nesting, non-overlapping turns, tools after
the chat of their turn, `pi.run.turn_count`, and the bijection between spans
and branch entries (assistant ↔ chat, tool result ↔ execute_tool, compaction ↔
pi.compaction, user message ↔ prompt run, custom message ↔ wakeup/continuation
run, each at most once).

| Clause | Case |
|---|---|
| File path under `getSessionDir()/traces/<session id>.otlp.jsonl`, created on demand; no file before the first span | a prompt with a tool call exports run, turn, chat and tool spans … |
| Live update: every span written twice, a start line (`pi.span.phase = start`, no end time, no status, the attributes known at start) at the starting event and before any child's start line, then an end line that repeats the start line's identity and attributes; end lines first when one event writes both; `liveProblems` in `tests/at_support.ts` checks the pairing on every trace the suites read | a prompt with a tool call … (line order of all twelve lines), the file updates live: start lines appear while a tool is still running and end lines complete them (file read mid-execution of a 1.5-second tool), lifecycle kill case (start lines of the run, turn and tool survive) |
| Span names, kinds, parents; run attributes (`prompt` trigger, turn count, user entry id); turn attributes (index, stop reason, tool call count); turn start = `turn_start` timestamp at millisecond precision; start lines carry at least the identifying attributes (checked as a subset); chat attributes (operation, system, model, usage ints, finish reasons, assistant entry id); tool attributes (operation, name, call id, is_error, tool-result entry id); tool spans after the chat; timestamps inside the prompt's wall-clock window (with a one-millisecond allowance for sub-millisecond clocks); `service.version`, `process.pid` | a prompt with a tool call exports run, turn, chat and tool spans in OTLP/JSON tied to session entries |
| Append-only: a later prompt appends, earlier lines unchanged | same case (second prompt) and reload case |
| ERROR status and message for a failing tool result (message = result text); error assistant message → chat and turn ERROR with `errorMessage`, finish reason `error`; the run stays OK | a failing tool and an error response mark tool, chat and turn spans ERROR while the run stays OK |
| `pi.run.trigger`: `wakeup` for `triggerTurn` messages while idle, `continuation` for a run queued at `agent_end` (before `agent_settled`), entry ids of the custom messages; a `triggerTurn: false` message is referenced by no span | runs started by an extension message are wakeups and runs queued at agent_end are continuations |
| `pi.compaction` root spans for manual and threshold compaction: reason, `will_retry`, `tokens_before`, entry id, OK status, written at their end; summary requests are not chat spans; a threshold compaction starts after the run ended | manual and threshold compactions export root compaction spans tied to compaction entries |
| `/reload` appends to the same file with the same trace id, no re-export, no duplicate span ids | reload appends to the same file with the same trace id and no duplicate spans |
| Concurrent tool calls of one assistant message: one span per call, all children of the turn, overlapping, written in end order, each tied to its own tool result by `toolCallId`, per-span status (a failing `boom` beside a succeeding `echo`), `pi.turn.tool_call_count` counts all | concurrent tool calls of one assistant message get one overlapping span each with its own status and entry |
| Steering: a `streamingBehavior: "steer"` prompt and a `deliverAs: "followUp"` custom message consumed mid-run start turns 1 and 2 of the same run; `pi.run.steer_count` 2 and `pi.run.steer_entry_ids` in delivery order; a `triggerTurn: false` note flushed mid-run is referenced by nothing; the bijection counts steering ids as user/custom references | steering and follow-up messages start turns inside the run and are listed on it, never as new runs |
| Overflow recovery: a `prompt is too long` error response leaves a persisted error assistant message (chat and turn ERROR with its `errorMessage`), a root `pi.compaction` span with reason `overflow` and `will_retry: true` between the runs, and a third run with trigger `continuation`, no entry id, `pi.run.after_compaction` = the compaction entry; a context-only custom message sent earlier is not claimed by the retry run | overflow recovery persists the failed chat, compacts with will_retry and continues in a run without a message |
| Sub-agents: the verifier's `spawn_child` tool spawns a child pi with the inherited environment (the mechanism is the solver's); the child (a separate process, its own session) writes its own trace file with the parent's trace id, its run's `parentSpanId` = the tool span, its own `pi.session.id`, times inside the tool span, a valid bijection against its own branch; after the tool ends `process.env` equals its snapshot from before the prompt (no leaked context) | a child pi spawned by a tool joins the parent's trace under that tool span through PI_AGENT_TRACE_PARENT |
| Compaction accounting: `pi.compaction.first_kept_entry_id`, `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` equal the compaction entry's fields on manual and threshold spans | manual and threshold compactions export root compaction spans tied to compaction entries |
| An aborted stream: pi persists the assistant message with `stopReason: "aborted"`; chat and turn ERROR with its `errorMessage`, finish reason `aborted`, entry id set; the run OK; the next prompt traced normally | an aborted stream marks its chat and turn ERROR and the trace stays consistent afterwards |
| A failed compaction: root `pi.compaction` span ERROR with the event's `errorMessage`, only `reason` and `will_retry` attributes, no compaction entry on the branch, written at the failure; a later successful compaction traced normally | a failed compaction exports an ERROR compaction span without an entry id |
| `session_shutdown` while a run streams (pi's quit path): open chat, turn and run closed with ERROR `shutdown`, child-first, end times inside the verifier's dispose window, chat without entry id, run with the user entry id and `turn_count` counting the open turn | a quit while a run is streaming closes the open spans with status shutdown |
| An unwritable path: no exception reaches pi's extension error listener, tools and runs proceed, no file appears, exactly one `agent-trace` custom message starting with `agent-trace: cannot write <path>` delivered without starting a turn, system prompt untouched | an unwritable trace path never reaches the agent and is reported once |
| `PI_AGENT_TRACE_FILE` replaces the path (directory created on demand); the default path is not written | PI_AGENT_TRACE_FILE replaces the trace file path |
| A later pi process resumes the session: same trace id, earlier spans untouched, its own `process.pid`, bijection over the whole branch | lifecycle: a later pi process appends to the same trace with the same trace id and its own process id |
| Crash safety: the chat span is written at the turn's first `tool_execution_start`, so a process killed with SIGKILL during a 20-second tool leaves exactly that chat span (with the assistant entry id from the session file, finish reason `toolUse`, a parent that never got written) and nothing else of that turn; the file stays valid and a later process appends normally | lifecycle: a pi process killed during a tool execution leaves that turn's chat span on disk |

## Clauses observed only indirectly

- Disk-full and permission-denied writes are represented by the one
  deterministic write failure the verifier can create (a regular file where
  the directory should be); recovery after the path becomes writable again is
  not driven.
- A SIGKILL during a chat stream (before the assistant entry exists) is not
  driven; the contract allows that span to be lost.

## Base behaviour

On Base no trace file exists: every contract case fails on `trace file … does
not exist` and the lifecycle case the same way. PASS_TO_PASS passes on Base.
