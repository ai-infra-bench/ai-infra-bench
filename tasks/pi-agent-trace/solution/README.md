# Oracle: agent-trace extension

Reference implementation for `pi-agent-trace`, applied by `solve.sh` with
`git apply`. It adds:

- `packages/coding-agent/examples/extensions/agent-trace/index.ts`: the
  extension. Spans are built from the extension events (`agent_start`/`agent_end`,
  `turn_start`/`turn_end`, assistant `message_start`/`message_end`,
  `tool_execution_start`/`end`, `session_before_compact`/`session_compact`/
  `session_compact_failed`) and written as OTLP/JSON lines. Because pi persists
  a message only after extensions have seen its `message_end`, chat and tool
  spans are held until `turn_end`, where the assistant and tool-result entry ids
  are read from `sessionManager.getBranch()`: the chat span is written at the
  turn's first `tool_execution_start` (or at `turn_end` without tools) so a
  crash during a long tool keeps it; the run's entry id (the user message, or
  the custom message that started a wakeup or continuation) is resolved at the
  first `turn_end` of the run, or at `session_shutdown`. On `session_shutdown`
  every open span is closed with status ERROR "shutdown". Writes are wrapped:
  the first failure is reported once as an `agent-trace` custom message and
  nothing is thrown into pi. Every span is written twice (a start line with
  `pi.span.phase = start`, then the end line) so the file updates live.
  Steering: the first user/custom `message_start` of a run is its trigger,
  later ones are steering messages counted per turn and resolved at `turn_end`
  as the last such entries between the previous and the current assistant
  entry (context-only custom messages pi flushed at `turn_end` come before
  them). Concurrent tool calls are tracked in a map by `toolCallId` and
  written in end order; compaction spans copy `usage` and `firstKeptEntryId`
  from the compaction entry. Overflow recovery: a `session_compact` with
  `willRetry` marks the next run as a retry (`pi.run.after_compaction`, no
  entry id resolution). Sub-agents: `PI_AGENT_TRACE_PARENT` is read once at
  bind (trace id and root parent for every root span) and published while
  tools run (a stack of running tool spans; the most recently started one
  wins; the inherited value is restored when none runs). The run trigger is classified from
  `before_agent_start` (prompt) and `agent_settled` (a start before the previous
  run settled is a continuation). The trace id is a SHA-256 prefix of the
  session id; binding happens lazily from `ctx.sessionManager` because pi does
  not send `session_start` to a reloaded runtime without host bindings.
- `README.md` next to it.
- `packages/coding-agent/test/agent-trace-extension.test.ts`: an offline unit
  test with the faux provider covering the file shape and span tree.
