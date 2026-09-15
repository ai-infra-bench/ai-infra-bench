# Oracle status: not implemented in this draft

This task is drafted without a reference implementation. The verifier was executed
against the unmodified Base and fails every case for the target reason (the
`bg_*` tools are not registered), but no candidate has yet received reward 1.

## Reference design (curator notes, not a specification)

An implementation that satisfies the contract needs roughly these parts, all
behind pi's public extension API:

- **Process manager singleton per pi OS process**, stored on `globalThis` under a
  `Symbol.for(...)` key so `/reload`, `/new`, `/fork`, and tree navigation reuse
  it. Each extension instance rebinds listeners on `session_start` and removes
  only its own listeners on `session_shutdown`; it must not `killAll()` there.
- **Spawn** via the configured shell with `detached: true`, `stdio: ["ignore",
  "pipe", "pipe"]`, so the child owns a process group and nothing inherits pi's
  stdio. Record `pid`, `pgid = pid`, `startedAt`.
- **Disk-backed logs**: stream stdout/stderr through a line splitter into
  `<sessionDir>/background-processes/<piPid>/<id>.log` plus a small line index
  (byte offset per N lines) so `bg_logs` can seek to `offset` without reading the
  whole file. Keep only a bounded tail in memory for the default page.
- **Wake scheduler**: per process, a pending set of reasons and the first matched
  line; a `ready` latch; an `exitDelivered` latch. Deliver through
  `pi.sendMessage({customType: "background-process", content, details},
  {deliverAs: "steer", triggerTurn: true})`. When the agent is streaming, pi
  queues the steer and delivers it after the tool batch; when idle,
  `triggerTurn` starts a turn. Coalesce by flushing the pending set at delivery
  time, and flush processes in first-fire order.
- **Active-session routing**: keep the most recent `ExtensionAPI` from
  `session_start` as the delivery target; the starting session's API is used
  while it is still current.
- **Kill**: `process.kill(-pgid, "SIGTERM")`, wait up to `timeoutSec`, then
  `process.kill(-pgid, "SIGKILL")`; then run the cleanup command and report
  `{ran, exitCode, failed}`.
- **Exit hooks**: `process.once("exit")` plus `SIGTERM`/`SIGINT` handlers that
  run the same terminate sequence synchronously enough to finish before pi dies
  (SIGKILL the groups when the grace period cannot be awaited).
- **Durable records**: write the final record JSON next to the log on exit; on
  `session_start` in a fresh pi process, scan the session's directory and expose
  finished records through `bg_list`/`bg_logs` with `state` never `running`.

## Known implementation traps the verifier exercises

- Killing only the direct child leaves SIGTERM-ignoring grandchildren alive.
- `killAll()` in `session_shutdown` breaks `/reload`, `/new`, and `/fork`.
- Delivering one message per matched line spams the agent; the flood and
  coalescing cases reject it.
- Keeping the whole log in memory fails the heap-growth case.
- Reporting `exit` before the process group is actually gone races the kill case.
