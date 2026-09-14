# Model-managed context windows in Pi

We use one persistent Pi session to pursue a goal over many model calls. Repeatedly summarizing the whole conversation loses details, while retaining every tool output fills the context window. Let the model keep working notes, explicitly start a fresh working context, and retrieve original evidence when it needs it.

Add an opt-in extension at `packages/coding-agent/examples/extensions/context-management/index.ts`, loaded with `pi -e packages/coding-agent/examples/extensions/context-management/index.ts`. It must work with ordinary Pi providers, including API-key providers, without an external memory service. Implement these model-facing tools; return their results as JSON text:

| Tool | Arguments | Result |
| --- | --- | --- |
| `new_context` | `{}` | `{ window_id }`, identifying the requested new window |
| `notes_write` | `{ path, text }` | `{ path }`; create or completely replace a note |
| `notes_read` | `{ path, offset?, limit? }` | `{ path, text, next_offset }` |
| `notes_list` | `{ prefix?, cursor?, limit? }` | `{ paths, next_cursor }` |
| `history_search` | `{ query, window_id?, role?, tool_name?, cursor?, limit? }` | `{ items: [{ window_id, item_id, role, tool_name?, preview }], next_cursor }` |
| `history_read` | `{ window_id, item_id, offset?, limit? }` | `{ window_id, item_id, role, tool_name?, text, next_offset }` |

Notes are session-local logical files backed by durable local storage. Paths are nonempty relative slash-separated names; reject absolute paths, backslashes, and empty, `.` or `..` components. Preserve text exactly, including Unicode and newlines. Support up to 64 KiB of UTF-8 per note; the special `summary.md` note has an 8 KiB limit. Reject larger writes without changing the previous note. Missing notes and invalid arguments must produce tool errors. `notes_list` uses a case-sensitive path prefix and ascending path order.

`new_context` changes the working context, not the session or workspace. Complete the current assistant's entire tool batch before installing the new window, without aborting or rerunning those tools. Multiple requests in one batch may coalesce into one window. Continue the agent loop automatically without another user prompt and without a model-generated summarization call. The next model request must retain the effective system instructions, user messages (including the goal and later corrections), and the latest `summary.md`, if present. Earlier assistant messages and tool outputs must no longer be included automatically, including the batch that requested the transition. Other notes remain available through the note tools. Advertise the current window ID and how to retrieve notes and history in the new working context. Subsequent calls must include the new window's conversation normally, with valid tool-call/result pairing.

Archive the original conversation locally. History tools must retrieve user and assistant text, assistant tool-call names and arguments, and tool-result text, even after several window transitions. IDs are opaque, stable across reopening the session, and scoped to that session. Search is a case-sensitive literal substring search, oldest first. Optional filters are conjunctive; `role` is `user`, `assistant`, or `tool`, and `tool_name` selects tool-result messages. Each preview contains at most 256 Unicode characters. An unknown window returns no search matches; reading an unknown or mismatched item/window pair is a tool error. Searching or reading another session's IDs must never return that session's content.

List/search `limit` defaults to 20 and accepts integers from 1 to 100. Their opaque continuation cursors must allow traversal without omissions or duplicates while the matching data is unchanged; no more results means `next_cursor: null`. Read `offset` defaults to zero and `limit` to 2000; accept a nonnegative integer offset and limits from 1 to 8000, measured in Unicode code points. Return `next_offset: null` at the end, and empty text for an offset beyond the end. Invalid cursors are tool errors. Read results must permit reconstruction of the complete original text without truncation or duplication.

Successful note writes and completed window transitions must survive a normal process restart and `--session` resume. Reopening must not reintroduce discarded context or lose access to old evidence. Different sessions in the same working directory must have independent notes and histories. Context changes must leave workspace files intact. When the extension is not loaded, ordinary Pi execution remains unchanged.

Document usage and the distinction between a context window and a session. Internal storage, indexing, and the use of Pi's existing extension/core interfaces are your choice. Automatic budget policy, cross-session memory sharing, concurrent writers to one session, multimodal history, a new UI, and migration from Codex storage are outside scope.

Work in `/workspace/pi` with the installed dependencies. Deliver implementation and documentation as repository changes. `pi` runs directly from TypeScript source. The pinned repository has pre-existing provider/catalog type errors in `npm run check`; those unrelated errors are not acceptance criteria.
