We run pi as the harness in our infra evaluations and need to see what an agent run actually did, with timings and token accounting, without touching pi core. Export the agent loop as a distributed trace: one span per run, turn, provider request, tool execution and compaction, written to a local file in OpenTelemetry's OTLP/JSON encoding so a collector or any OTLP-aware viewer can load it, and usable while the session is still running.

Implement it as a pi extension at `packages/coding-agent/examples/extensions/agent-trace/index.ts` in this checkout of pi (`@earendil-works/pi-coding-agent` 0.85.1, Node 22). The file must `export default function (pi: ExtensionAPI)` and use only the public extension API; do not modify pi core and do not add dependencies (no OpenTelemetry SDK; the encoding is small enough to write by hand). Keep the layout conventions of the neighbouring examples so it loads with `pi -e` or through `DefaultResourceLoader`.

This document has two parts. **Requirements** say what must be true of the trace and are stated as outcomes; how you meet them inside pi's extension API is your design. **Export contract** fixes the file format, span names, attribute keys and status rules, because tools that consume the file depend on them.

## Requirements

- **Complete.** Every run of the agent loop, every turn, every provider request, every tool execution and every compaction of a session appears as a span, with the token, cache, timing and status information listed in the contract, and every span that corresponds to a session entry names that entry.
- **Live.** The file updates as the session runs: a span appears in the file when it starts and is completed when it ends. A reader tailing the file sees a run, a turn or a 30-second tool the moment it begins, and a reader that de-duplicates by span id, last line wins, always holds the current state of the trace.
- **Append-only and stable.** The file only grows; nothing is rewritten or exported twice; `/reload` and a later pi process resuming the session continue the same trace in the same file, with the same trace id.
- **Crash-safe.** A pi process that dies while a tool executes leaves on disk every span of that turn that had already ended (the provider request in particular) and the start records of what was open; the file stays valid for the next process.
- **Failure-safe.** A tool that fails, a provider response that fails or is aborted, and a compaction that fails are traced as ERROR spans with the reason, and the trace continues normally afterwards. A pi process that is shut down while a run is still streaming closes every open span with the status `shutdown` before it goes. A span closed by a shutdown carries every attribute whose value is known at that moment; an entry id is known only when pi has already persisted the entry. A trace file that cannot be written must not disturb the agent (no exception surfaces to pi, tools and later turns run normally) and must be reported once per process to the model, through a custom message, so the failure is visible.
- **Overflow recovery.** When a provider rejects a request as too large and pi recovers by compacting and retrying, the trace shows the rejected response, the compaction that recovered it, and the retry run, and the retry run is attributable to that compaction.
- **Concurrency.** When one assistant message calls several tools, each call is its own span with its own status and its own result entry, and the spans overlap in time as the executions did.
- **Steering.** A message that the agent loop consumes while a run is already active (a steering or follow-up prompt, or an extension message delivered for steering or follow-up) continues that run in a new turn; it never opens a run, and the run lists it. A message queued to run after the current run has ended opens a new run instead. A context-only message an extension delivers without starting a turn is referenced by no span.
- **Sub-agents.** pi's sub-agent extensions spawn child pi processes from a tool; a child inherits nothing from its parent but the environment and its command line. A pi process spawned by a traced tool must appear in the same trace: every span of the child session carries the parent's trace id and each root span of the child (its runs and compactions) is a child of the spawning tool's span, while the child still writes its own session's file. The spawning tool may cooperate by supplying its toolCallId to a documented integration provided by the tracing extension and using the returned child environment when spawning. This integration must use public extension APIs; it must not modify pi core or serialize concurrent tools. Its name and internal representation are your design. Tools that do not opt in still receive ordinary tool spans; automatic child-process attribution from unmodified tools is outside scope. Child-specific context must not leak: once no tool of a process is executing, the process environment is what the process started with.

Include a short `README.md` next to the extension describing the spans and the file, and add a unit test file for the extension under `packages/coding-agent/test/` that runs offline with `npm test -w packages/coding-agent`. The existing coding-agent test suite must keep passing unchanged; do not edit existing test files.

## Export contract

### File

Spans go to `<SessionManager.getSessionDir()>/traces/<session id>.otlp.jsonl`, created on demand together with its directory; `PI_AGENT_TRACE_FILE`, when set, replaces that path. The file is JSON Lines; every line is one OTLP/JSON `ExportTraceServiceRequest` holding exactly one span record:

```json
{"resourceSpans":[{"resource":{"attributes":[...]},"scopeSpans":[{"scope":{"name":"pi.agent-trace","version":"1"},"spans":[<span>]}]}]}
```

Resource attributes: `service.name` = `"pi"`, `service.version` = the coding-agent package version, `pi.session.id` = the session id, `process.pid` = the process id.

Every span is written twice, each time as one line terminated by `\n`:

- the **start line**, when the span starts: no `endTimeUnixNano`, no `status`, the attribute `pi.span.phase` = `"start"`, plus the attributes whose values are known at that time, at least the ones that identify the span (the run's `pi.run.trigger`, the turn's `pi.turn.index`, the chat's `gen_ai.operation.name` / `gen_ai.system` / `gen_ai.request.model`, the tool's `gen_ai.operation.name` / `gen_ai.tool.name` / `gen_ai.tool.call.id`, the compaction's `pi.compaction.reason` / `pi.compaction.will_retry`). A span's start line precedes the start line of any of its children.
- the **end line**, once the span has ended and its attributes are known: the same `traceId`, `spanId`, `parentSpanId`, `name`, `kind` and `startTimeUnixNano`, every attribute of the start line with the same value plus the rest, `endTimeUnixNano`, `status`, and no `pi.span.phase`. End lines appear in the order the spans ended: `endTimeUnixNano` never decreases from one end line to the next.

A span that has a start line and no end line is in progress (or was lost to a crash). Nothing else is ever written, rewritten or re-exported.

### Encoding

- `traceId`: 32 lowercase hex characters, the same for every span of a session across reloads and processes (derive it from the session id unless the session is a sub-agent's, see below); `spanId`: 16 lowercase hex characters, one span per id (one start line, one end line); `parentSpanId`: the parent's `spanId`, omitted for a root span.
- `name`, `kind` (`1` = INTERNAL, `3` = CLIENT), `startTimeUnixNano` and (end lines only) `endTimeUnixNano` as decimal strings of nanoseconds since the Unix epoch (`start <= end`). Timestamps come from the clock at the moment of the event, except that a turn starts at the `turn_start` event's own `timestamp`; sub-millisecond digits are yours.
- `attributes`: an array of `{ "key": ..., "value": { "stringValue" | "intValue" | "boolValue" | "arrayValue": ... } }`; integers are encoded as decimal strings (`{"intValue":"1234"}`), string arrays as `{"arrayValue":{"values":[{"stringValue":...}]}}`. A key appears at most once per line.
- `status` (end lines only): `{"code":1}` (OK) or `{"code":2,"message":<text>}` (ERROR).

### Spans

| name | kind | parent | attributes on the end line |
|---|---|---|---|
| `pi.run` | 1 | none, or the spawning tool span of a sub-agent | `pi.run.trigger` (`"prompt"` for a run started by a user prompt, `"wakeup"` for a run started by an extension message while pi was idle, `"continuation"` for a run that follows the previous run without a settle in between: a queued follow-up or an overflow retry), `pi.run.turn_count` (int), `pi.session.entry_id` (the entry id of the user message for `"prompt"` runs and of the custom message for `"wakeup"` runs, and of the queued user or custom message for a `"continuation"` run; absent on an overflow retry), `pi.run.after_compaction` (only on an overflow retry: the entry id of the compaction it follows), `pi.run.steer_count` (int) and `pi.run.steer_entry_ids` (string array: the entry ids of the messages that steered or followed up inside this run, in delivery order; present on every run, `0` and empty when none) |
| `pi.turn` | 1 | the run | `pi.turn.index` (int, pi's `turnIndex`), `pi.turn.stop_reason` (the assistant message's `stopReason`), `pi.turn.tool_call_count` (int, every tool call of the turn) |
| `chat <model>` | 3 | the turn | `gen_ai.operation.name` = `"chat"`, `gen_ai.system` (provider), `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `pi.usage.cache_read_tokens`, `pi.usage.cache_write_tokens` (ints from the message's `usage`), `gen_ai.response.finish_reasons` (string array with the `stopReason`), `pi.session.entry_id` (the assistant message's entry id) |
| `execute_tool <tool name>` | 1 | the turn | `gen_ai.operation.name` = `"execute_tool"`, `gen_ai.tool.name`, `gen_ai.tool.call.id`, `pi.tool.is_error` (bool), `pi.session.entry_id` (the tool result's entry id) |
| `pi.compaction` | 1 | none, or the spawning tool span of a sub-agent | `pi.compaction.reason` (`manual`, `threshold` or `overflow`), `pi.compaction.will_retry` (bool), and from the compaction entry (all absent when the compaction failed): `pi.compaction.tokens_before` (int), `pi.compaction.first_kept_entry_id`, `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` (ints from the entry's `usage`; absent only when the entry carries none), `pi.session.entry_id` (the compaction entry id). The summary requests of a compaction are not chat spans |

A run spans the agent loop from its start to its end; a turn from the turn's start to its end; a chat from the assistant message's start to its end; a tool from its execution's start to its end; a compaction from its preparation to its success or failure. Compactions happen between runs and are root spans (or hang under the spawning tool span in a sub-agent). Nesting is strict: a child starts no earlier and ends no later than its parent, the turns of a run do not overlap, and within a turn the tool spans start after the chat span ends.

### Status

ERROR with a message for: a tool result with `isError` (message = the result's text); an assistant message whose `stopReason` is `error` or `aborted` (message = its `errorMessage`, or `"aborted"` when there is none) and the turn that contains it; a failed compaction (message = the failure's `errorMessage`, or `"aborted"`); every span closed by a shutdown (message `shutdown`). Everything else is OK, including a run whose turns failed or were aborted.

### Session entries

Entry ids are the ids of the entries on the current branch (`SessionManager.getBranch()`) and appear on end lines only. Every `pi.session.entry_id` refers to an entry of the matching type on the branch, and the branch is covered exactly once: the user message entries are the `pi.session.entry_id`s of the `prompt` runs and user-message `continuation` runs plus every user entry id in any run's `pi.run.steer_entry_ids`; every assistant message (including aborted and failed ones, which pi persists), tool result and compaction entry is referenced by exactly one span of its kind; a custom message entry is referenced at most once, by a `wakeup`/`continuation` run's `pi.session.entry_id` or by a run's `pi.run.steer_entry_ids`, and the ones that started nothing (context-only messages, the write-failure report) by nothing. An overflow retry run references no message; its `pi.run.after_compaction` is a compaction entry whose span has `pi.compaction.will_retry` true. Spans closed by a shutdown may lack an entry id when pi never persisted the entry and are exempt.

### Write-failure report

The one report per process is a custom message with `customType: "agent-trace"`, delivered without starting a turn, whose text starts with `agent-trace: cannot write` followed by the path. It never goes into the system prompt.

### Sub-agent trace

A pi process spawned by a traced tool using the documented child-context integration uses the parent's trace id for every span of its session and makes each of its root spans a child of the spawning tool's span (`parentSpanId` = that tool's `spanId`).
