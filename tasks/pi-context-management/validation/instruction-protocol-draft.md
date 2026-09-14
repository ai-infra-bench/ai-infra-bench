# Model-managed context windows in Pi

I want Pi to pursue a goal in one persistent session while the model manages its working context: save useful conclusions, start a fresh context, and retrieve earlier evidence when needed. Add an opt-in extension at `packages/coding-agent/examples/extensions/context-management/index.ts`, loaded with `pi -e <path>`. Support ordinary Pi providers, including API-key providers, without an external memory service.

Expose these tools, returning JSON text:

| Tool | Arguments | Result |
| --- | --- | --- |
| `notes_write` | `{ path, text }` | `{ path }` |
| `notes_read` | `{ path, offset?, limit? }` | `{ path, text, next_offset }` |
| `notes_list` | `{ prefix?, cursor?, limit? }` | `{ paths, next_cursor }` |
| `new_context` | `{}` | `{ window_id }` for the requested window |
| `history_search` | `{ query, window_id?, role?, tool_name?, cursor?, limit? }` | `{ items: [{ window_id, item_id, role, tool_name?, preview }], next_cursor }` |
| `history_read` | `{ window_id, item_id, offset?, limit? }` | `{ window_id, item_id, role, tool_name?, text, next_offset }` |

Notes are durable session-local logical files. Writes create or replace the entire text exactly, including Unicode and newlines. Allow 64 KiB of UTF-8 per note, except `summary.md` (8 KiB); oversized writes must preserve the previous value. Paths must be nonempty relative slash-separated names, excluding backslashes and empty, `.` or `..` components. Listing uses a case-sensitive prefix and ascending path order.

`new_context` changes the working context without changing the session or workspace files. Finish the entire current assistant tool batch exactly once before switching; requests within one batch may coalesce. Continue automatically without another user prompt or a summarization model call. The next request retains effective system instructions, all user messages (including corrections), and the latest `summary.md` if present. Exclude earlier assistant/tool messages, including the switching batch. Advertise the window ID and how to retrieve notes/history; other notes remain available on demand. Subsequent requests carry the new conversation normally, preserving tool-call/result pairing.

Archive original user/assistant text, assistant tool names and arguments, and tool-result text across transitions. History IDs are opaque, session-scoped, and stable on reopening. Search matches literal case-sensitive substrings, oldest first; filters combine conjunctively. `role` is `user`, `assistant`, or `tool`; `tool_name` filters tool results. Previews contain at most 256 Unicode characters. Unknown windows yield no matches; unknown or mismatched item/window reads are errors. Another session's IDs must never expose its content.

List/search limits are integers 1–100, default 20. Opaque cursors must traverse unchanged matching data without omissions or duplicates, ending with `next_cursor: null`. Reads use Unicode code-point offsets (nonnegative integers, default 0) and limits (integers 1–8000, default 2000). Paged reads must reconstruct the full original text exactly; return `next_offset: null` at the end and empty text beyond it. Missing notes and invalid arguments, including invalid cursors, produce tool errors.

Successful writes and completed transitions must survive normal process restart and `--session` resume: retain the active window and access to history without automatically restoring discarded messages. Sessions sharing a working directory must have independent notes and histories. Without this extension, ordinary Pi behavior must remain unchanged.

Document usage and the session/window distinction. Storage, indexing, and extension/core integration are your choice. Automatic budget policy, cross-session memory sharing, concurrent writers to one session, multimodal history, a new UI, and Codex storage migration are outside scope.

Work in `/workspace/pi` using installed dependencies; deliver code and documentation changes. Pi runs from TypeScript source. Existing provider/catalog errors in `npm run check` are unrelated and excluded from acceptance.
