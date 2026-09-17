# Behavior-to-test map (curator-only), pi-agent-trace 0.0.6

Semantic boundary:

```text
pi agent loop events (agent_start/end, turn_start/end, message_start/end,
tool_execution_start/end, session_before_compact/compact/compact_failed,
session_shutdown, reload, a second pi process on the same session)
  -> the candidate extension's span bookkeeping and file writes
  -> lines of <session dir>/traces/<session id>.otlp.jsonl (or PI_AGENT_TRACE_FILE),
     checked against the session branch (SessionManager.getBranch()) and the
     verifier's own event recorder
```

Real components: pi's AgentSession, extension runner, tool execution, steering and
follow-up delivery, compaction (manual, threshold, overflow retry), SessionManager
(file-backed), reload, separate child pi processes (lifecycle suite, sub-agent case).
Substituted: the model (pi's first-party faux provider, scripted per case) and the tools
(verifier-registered `echo`, `boom`, `spawn_child`). Neither determines span structure,
timing class, entry persistence order or lifecycle; they only choose which events occur.

| Instruction requirement | Scored case(s) |
|---|---|
| Live: a span appears when it starts and is completed when it ends; a tailing reader sees a long tool while it runs | the file updates live (start lines appear while a 1.5 s tool runs; end lines complete them) |
| Append-only and stable; reload and a later process continue the same trace and trace id | reload appends…; lifecycle: a later pi process appends… |
| Crash-safe: a process killed mid-tool leaves the ended spans and the open start lines | lifecycle: a pi process killed during a tool execution… |
| Failure-safe: failing tool, failed/aborted response, failed compaction are ERROR with the reason, trace continues | a failing tool and an error response…; an aborted stream…; a failed compaction… |
| Failure-safe: shutdown while streaming closes every open span with status `shutdown`, carrying the attributes known at that moment | a quit while a run is streaming… |
| Failure-safe: an unwritable file never disturbs the agent and is reported once via a custom message | an unwritable trace path never reaches the agent and is reported once |
| Overflow recovery: rejected response, will_retry compaction, retry run attributable via pi.run.after_compaction | overflow recovery persists the failed chat… |
| Concurrency: one span per call with its own status and result entry, overlapping as executed | concurrent tool calls of one assistant message… |
| Steering: steer/follow-up continue the run in new turns and are listed; queued-after-run opens a new run; context-only messages referenced by nothing | steering and follow-up messages start turns inside the run…; runs started by an extension message are wakeups and runs queued at agent_end are continuations |
| Run triggers prompt / wakeup / continuation | runs started by an extension message…; overflow recovery… |
| Span kinds, names, parent structure (turn under run, chat and tool under turn, compaction root) | a prompt with a tool call exports run, turn, chat and tool spans…; manual and threshold compactions export root compaction spans… |
| Start and end lines: required start attributes, end line repeats them, end order never decreases, one start and one end per span | every case via `liveProblems` and `traceProblems` (shared invariants) |
| Encoding: trace id derived from the session id, hex id formats, decimal-string timestamps, attribute value encoding, status shape, one key per line | every case via `readTrace` |
| Attribute tables per span kind (run, turn, chat, tool, compaction) | a prompt with a tool call…; manual and threshold compactions…; a failed compaction…; concurrent tool calls… |
| Entry ids: on end lines only, bijection with the branch (user entries to prompt runs or steer lists, assistant to chats, tool results to tools, compaction entries to compactions, custom messages at most once), shutdown exemption for never-persisted entries | `traceProblems` in every case; the steering, triggers, compaction and quit cases assert the specific mappings |
| Resource attributes (service.name, service.version, pi.session.id, process.pid) | `traceProblems` in every case; lifecycle: its own process id |
| Trace file path and PI_AGENT_TRACE_FILE override | PI_AGENT_TRACE_FILE replaces the trace file path; default path in every other case |
| Sub-agent: a child pi joins the parent's trace under the spawning tool span | a child pi spawned by a tool joins the parent's trace… |
| Write-failure report text and delivery (custom message, never in the system prompt) | an unwritable trace path never reaches the agent… |
| Deliverables: README, offline unit test, existing suite unchanged | PASS_TO_PASS (baseline pins; modified existing tests rejected) |

Every scored assertion traces to a row above; the two verifier-clock windows and the
mixed-clock comparisons are made with 1 ms slack or at millisecond granularity (see
README, revisions of 2026-09-16). Curator-side independent challenge:
`validation/at.independent.test.ts` via `independent_challenge.py` (composition of
failing tool + manual compaction + parallel batch with one failure; override path +
reload + wakeup in one session).
