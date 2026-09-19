# Behavior-to-test map (curator-only)

Semantic boundary:

```text
bg_run tool call from the agent loop
  -> extension spawns a detached process group, streams its output to disk,
     evaluates wake rules, and routes wakes through pi's steering queue
  -> tool results, custom messages in the session, OS process state, files under
     the session directory
```

Real components: pi's AgentSession, extension runner, tool execution, steering
queue, SessionManager (file-backed), SessionRuntime replacement, the OS process
tree. Substituted: the LLM (pi's first-party faux provider, scripted). The faux
provider only chooses which tool to call; every behavior under test happens in
real pi code and real processes.

| Instruction clause | Case (contract suite unless noted) |
|---|---|
| Tool names and parameters registered | registers bg_run, bg_logs, bg_list, bg_kill and bg_watch |
| Process record fields; bg_logs pages in order; bg_kill returns `killed` | bg_run returns a running record and bg_logs pages output in order |
| 64 KB page bound; default page = newest lines | bg_logs bounds a page to 64 KB and serves the newest lines by default |
| Exit wakes once; idle wake starts a turn; record becomes `exited` with exit code | exit wakes an idle agent exactly once with the exit code |
| `ready` wakes once; streaming wake delivered after the tool batch and before the next LLM call; `matchedLine` | ready wakes once and is delivered after the running tool batch |
| `error` at most once per window; combining reasons into one message is allowed, not required | not scored (the former "error and exit in one window coalesce into a single wake" case was removed on 2026-09-14: it demanded one merged message, which regulates the implementation rather than an observable outcome; two back-to-back messages in the same turn carry the same information) |
| SIGTERM then SIGKILL after `timeoutSec`; grandchildren removed; kill produces exactly one exit wake | bg_kill escalates to SIGKILL, removes grandchildren and wakes once |
| `bg_watch` silences `exit`, removes patterns | bg_watch silences the exit wake and drops patterns |
| Cleanup runs after the group is gone; failure reported; output appended to log | cleanup runs after the group is gone and a failing cleanup is reported |
| `/reload` does not stop processes | processes survive extension reload |
| `/new` and `/fork` do not stop processes; any session can list and kill | processes survive new session and fork and remain killable |
| Wake routes to the current active session | wake goes to the active session after the starting session was replaced |
| One message per process, first-fire order | two processes firing in one window wake in first-fire order |
| Logs on disk, heap does not grow with output, paging deep into a large log | log flood is paged from disk without growing the heap |
| pi exit stops every managed group incl. grandchildren | lifecycle: pi process exit stops managed processes and their grandchildren |
| SIGTERM to pi stops managed groups | lifecycle: SIGTERM to the pi process stops managed processes |
| Durable records readable by a later pi process; never `running` | lifecycle: a later pi process resumes the session and reads finished records |

Not covered by a scored case (documented limitation): `SIGINT` to pi (same
handler path as `SIGTERM`, not separately exercised); tree navigation without
fork (`navigateTree`) is covered by the same manager-lifetime rule as `/new`
but not exercised; `cleanup.timeoutSec` expiry.

### `bash` override (added 2026-09-14)

| Instruction clause | Case (contract suite unless noted) |
|---|---|
| Commands that finish before the silence threshold return what the built-in tool returns: output text, `Command exited with code <n>`, `Command timed out after <timeout> seconds`; a shorter `timeout` wins; no record, no wake | bash keeps the built-in contract for commands that finish before the silence threshold |
| No output for `stalledSec` seconds while running: return within one second with the record as JSON + `details`, `backgrounded: true`, `stalledSec`; earlier output is the head of the log; listed like a `bg_run` process | a silent bash command moves to the background and its next output and exit wake the agent |
| `output` wakes once, on the first complete line after the switch, with that line as `matchedLine`; `exit` still wakes once; a second output line does not wake again | same case (two wakes, `["output"]` then `["exit"]`, nothing after) |

On Base both cases fail on behavior, not on harness errors: the built-in `bash`
rejects the contract's `stalledSec` parameter, so the first `bash` result is a
tool error (`isError` true) and the timing assertion never sees a backgrounded
record. FAIL_TO_PASS is carried by the stall case; the normal-path case is the
guard that an override must not break ordinary `bash` behavior.

## Clauses covered only by the curator-side independent challenge

| Clause | Where checked |
|---|---|
| `bg_run`: a relative `cwd` resolves against the session's working directory and the record's `cwd` is the absolute path | `validation/independent_probe.mjs` `relative_cwd_resolved` (not in the verifier suites; the contract case uses absolute `cwd` values) |
| `bg_logs` with an offset past the end returns an empty page; `bg_kill` on a finished process returns the final record with `cleanup: null` and no extra wake | `validation/independent_probe.mjs` `logs_offset_past_end`, `kill_finished_process_is_noop` |
