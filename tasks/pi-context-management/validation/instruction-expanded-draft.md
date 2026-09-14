# Model-managed context windows in Pi

We use Pi to pursue a goal in one persistent session. As the agent explores possible approaches, intermediate reasoning and tool output accumulate. The model needs a way to carry useful conclusions forward without keeping all of that material in its working context, while still being able to consult the original evidence later.

Add model-managed context windows: the model can save working notes, request a fresh context, and continue the same goal. A context window is the conversation supplied to the model for its current work; the session is the persistent record across those windows. Switching windows must preserve the session and workspace, and earlier evidence must remain retrievable after switching or restarting Pi.

Provide this as an opt-in extension at `packages/coding-agent/examples/extensions/context-management/index.ts`, loaded with `pi -e packages/coding-agent/examples/extensions/context-management/index.ts`. It must work locally with ordinary Pi providers, including API-key providers, without an external memory service.

## Save working notes

The model uses `notes_write` to record conclusions and `notes_read` and `notes_list` to consult its notes. Notes are session-local logical files backed by durable local storage. Writing creates or completely replaces a note, preserving its text exactly, including Unicode and newlines. The latest `summary.md`, if present, is carried into a fresh context automatically; other notes are available on demand.

Support up to 64 KiB of UTF-8 per note, with an 8 KiB limit for `summary.md`. Reject larger writes without changing the previous note. Paths are nonempty relative slash-separated names; reject absolute paths, backslashes, and empty, `.` or `..` components. Missing notes and invalid arguments produce tool errors. Listing uses a case-sensitive path prefix and ascending path order.

## Start a fresh context and continue

`new_context` requests a new window. Complete the current assistant's entire tool batch before installing it, without aborting or rerunning those tools. Multiple requests in one batch may coalesce into one window. The agent loop must continue automatically, without another user prompt or a model-generated summarization call.

In the next model request, retain the effective system instructions, user messages (including the goal and later corrections), and the latest `summary.md`, if present. Earlier assistant messages and tool outputs must no longer be included automatically, including the batch that requested the transition. Advertise the current window ID and how to retrieve notes and history. Subsequent requests include the new window's conversation normally, with valid tool-call/result pairing.

## Retrieve original evidence

Archive the original conversation locally so that the model can use `history_search` and `history_read` to revisit details omitted from its notes. Preserve user and assistant text, assistant tool-call names and arguments, and tool-result text across multiple window transitions. Window and item IDs are opaque, scoped to the session, and stable across reopening it.

Search uses case-sensitive literal substrings and returns matches oldest first. Optional filters are conjunctive: `role` is `user`, `assistant`, or `tool`, and `tool_name` selects tool-result messages. Each preview contains at most 256 Unicode characters. An unknown window returns no matches; reading an unknown or mismatched item/window pair is a tool error. Searching or reading another session's IDs must never return that session's content.

## Resume the same goal

Successful note writes and completed window transitions must survive a normal process restart and `--session` resume. Reopening must preserve the active window: previously removed messages must not reappear automatically, and old evidence must remain accessible through history tools. Different sessions in the same working directory have independent notes and histories. Workspace files remain intact across context changes. When the extension is not loaded, ordinary Pi execution remains unchanged.

## Tool interface

Expose these model-facing tools and return their results as JSON text:

| Tool | Arguments | Result |
| --- | --- | --- |
| `notes_write` | `{ path, text }` | `{ path }` |
| `notes_read` | `{ path, offset?, limit? }` | `{ path, text, next_offset }` |
| `notes_list` | `{ prefix?, cursor?, limit? }` | `{ paths, next_cursor }` |
| `new_context` | `{}` | `{ window_id }`, identifying the requested new window |
| `history_search` | `{ query, window_id?, role?, tool_name?, cursor?, limit? }` | `{ items: [{ window_id, item_id, role, tool_name?, preview }], next_cursor }` |
| `history_read` | `{ window_id, item_id, offset?, limit? }` | `{ window_id, item_id, role, tool_name?, text, next_offset }` |

List/search `limit` defaults to 20 and accepts integers from 1 to 100. Their opaque continuation cursors must allow traversal without omissions or duplicates while the matching data is unchanged; no more results means `next_cursor: null`. Invalid cursors are tool errors.

Read `offset` defaults to zero and `limit` to 2000. Accept a nonnegative integer offset and limits from 1 to 8000, measured in Unicode code points. Return `next_offset: null` at the end, and empty text for an offset beyond the end. Paged reads must permit reconstruction of the complete original text without truncation or duplication.

## Delivery and scope

Document usage and the distinction between a context window and a session. Internal storage, indexing, and the use of Pi's existing extension/core interfaces are your choice. Automatic budget policy, cross-session memory sharing, concurrent writers to one session, multimodal history, a new UI, and migration from Codex storage are outside scope.

Work in `/workspace/pi` with the installed dependencies. Deliver implementation and documentation as repository changes. `pi` runs directly from TypeScript source. The pinned repository has pre-existing provider/catalog type errors in `npm run check`; those unrelated errors are not acceptance criteria.
