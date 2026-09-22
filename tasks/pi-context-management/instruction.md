# Let the model manage its working context in Pi

I use Pi for long-running tasks that involve exploring several approaches. I want the model to decide when to save its progress, important conclusions, and remaining work, then clear accumulated reasoning and tool output and continue from those notes. It should be able to do this before the context fills up, rather than relying only on automatic compaction.

After a reset, the next model request must include the task goal, system instructions, the user's instructions and corrections, and the latest working notes. Earlier assistant messages and tool results must leave the active context; new messages and tool results should accumulate normally. Earlier messages and tool results must remain searchable and readable so the model can check original evidence that it did not copy into its notes. Let it retrieve the relevant material without loading the entire history back into context.

Continue automatically in the same session, preserving workspace files and completing any tools already requested before switching contexts. The model writes its own working notes; switching must not require another model call to generate a summary or another user prompt to resume. Closing Pi and reopening that session should preserve the notes, the current working context, and access to earlier records. Separate sessions should keep their notes and histories independent.

Saving notes before switching is recommended, not a prerequisite. `new_context()` must also work when no notes have ever been written, or after `notes_write("")` explicitly clears them. In either case, preserve the task goal and system/user instructions, discard earlier assistant messages and tool results from active context, and keep the originals retrievable. An empty write replaces the previous notes and stays empty after reopening the session; it must not revive an old conclusion.

Implement this as an optional Pi extension that works with ordinary API-key providers and local persistent storage. Keep normal behavior unchanged when it is disabled. Document how to enable it and how the model uses the new capabilities.

Put the extension at `packages/coding-agent/examples/extensions/context-management/index.ts`. Expose `notes_write(text)`, `notes_read()`, `new_context()`, `history_search(query)`, and `history_read(window_id, item_id)` as model tools. Writes replace the working notes. Return JSON text: note/history reads include the complete `text`; search returns `items` with opaque, stable, session-scoped `window_id` and `item_id` values for reading matching original records. Other fields and optional arguments are your choice.

For a history read, `text` may contain the original text directly or valid JSON from which the complete original record can be recovered without loss (for example, a serialized message with text content). JSON escaping is allowed; summaries, truncated records, or rewritten evidence are not substitutes for the original.

Work in `/workspace/pi` with the installed dependencies and deliver code and documentation changes. Pi runs directly from TypeScript source. Existing provider/catalog errors in `npm run check` are unrelated to this task.
