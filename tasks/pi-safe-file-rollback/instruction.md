# Safe rollback after an interrupted coding task

Pi can change a project over many model turns. When a task stops unexpectedly, users need to return both the project files and the conversation to an earlier request boundary before continuing. Add an opt-in safe rollback feature to Pi.

## User workflow

Enable the feature with `--safe-rollback` or `createAgentSession({ safeRollback: true, ... })`. The setting belongs to the session and remains enabled when that session is resumed without repeating the option. Existing sessions and sessions that never enabled it keep their current behavior. Enabling the feature requires a file-backed session; reject an in-memory-only session with a descriptive error.

Before each top-level user request starts executing from an idle session, create a checkpoint representing the files and effective conversation immediately before that request. All model turns, retries, steering messages and queued follow-ups within that execution belong to that request; they do not create additional checkpoints. Checkpoint IDs must be unique across sessions and remain stable across restarts.

After an unexpected termination, resuming the session must preserve the interrupted work and offer its checkpoints. Do not start another model request or a file-changing operation until the user has selected a checkpoint and rollback has completed. Session navigation, forking or compaction must not change that session's effective conversation while recovery is unresolved. Read-only inspection remains available. While awaiting checkpoint selection or blocked by a recovery error, attempts to start a request, run Bash, navigate, fork or compact must reject with a descriptive error. During automatic recovery, an attempted request may reject or wait until recovery finishes; it must not execute early. Do not automatically discard the interrupted request. If an already-started rollback is interrupted, resume that rollback on the next startup before allowing ordinary execution.

A successful rollback restores the eligible files and the effective conversation to the chosen checkpoint. The removed request and its later messages must not appear in subsequent model requests. The result must survive an immediate restart. A repeated rollback to the current checkpoint is a successful no-op. Users can continue from a restored checkpoint to form a new branch; abandoned branches must not affect later rollback. Only checkpoints on the current session's ancestor path are valid targets.

## File behavior and operating conditions

The workspace is a local Linux Git working tree. Eligible paths are tracked regular files and untracked, non-ignored regular files under its root. Restore their contents, existence and Unix permission bits, including changes made through built-in `edit`, `write` and `bash`. Creating, deleting and renaming files must work. Changes made before a Bash command fails, is cancelled or is interrupted are still covered. Preserve pre-existing uncommitted content. Git HEAD, branches and index entries must not be changed by checkpointing or rollback.

The session has exclusive write access while a request executes and through any downtime and initial recovery following its interruption. All processes belonging to that execution, including Bash descendants, stop before recovery. Other writers may edit files while the session is idle. If rollback would discard such an edit, reject the entire operation, identify the conflicting paths, and leave both files and the effective conversation unchanged. This also applies to edits made between two requests. Unrelated files must remain unchanged.

The guarantee covers process termination, including termination while a tool or rollback is running. It does not require protection against power loss or disk corruption. The files need not change simultaneously, but normal execution must never proceed with an unfinished rollback. Ordinary filesystem failures must not be reported as successful rollback; retain the ability to finish once the failure is resolved.

Ignored untracked files, special files, symbolic/hard-link aliases, Git metadata, changes outside the workspace and external service effects are outside the rollback scope. Commands do not modify Git metadata, ignore rules, the recovery configuration, or leave independent background services. Multiple active writers, cross-session checkpoint transfer, arbitrary sibling-branch switching, redo and conversation summarization are not required.

## Public interfaces

Add these SDK operations to `AgentSession`, available through the package's normal SDK exports:

- `listCheckpoints()`: returns a promise of checkpoint records with `id: string`, `sessionId: string`, and `entryId: string | null`. The entry identifies the conversation boundary; `null` denotes the beginning. Additional display fields are allowed. Return eligible checkpoints from oldest to newest.
- `getRollbackState()`: returns the state below, directly or through a promise.
- `rollbackCheckpoint(checkpointId: string)`: resolves only when rollback has completed, or rejects with a descriptive error.

State contains `enabled: boolean` and `status: "ready" | "interrupted" | "restoring" | "blocked"`. When relevant, include `checkpointId: string` and `conflicts: string[]` using workspace-relative paths. `ready` means there is no unresolved interruption or rollback; it does not imply the agent is idle. When disabled, state is `{ enabled: false, status: "ready" }`, the checkpoint list is empty, and rollback rejects without side effects. A preflight conflict preserves the prior ready/interrupted status; it does not create an unfinished rollback.

Extend the existing JSON-lines RPC protocol with `list_checkpoints`, `get_rollback_state`, and `rollback_checkpoint` (input field `checkpointId`). Use the existing response envelope. Successful response data is respectively `{ checkpoints: [...] }`, the state object, and `{ checkpointId: "..." }`. Failed requests use the existing error response.

In interactive mode, `/rollback` displays checkpoints, including their stable IDs, and `/rollback <id>` restores one. Running requests must reject rollback as busy. Invalid, foreign-session and non-ancestor targets must produce an error without changing files or conversation. A blocked recovery must remain inspectable; retrying the same rollback after the underlying problem is removed must complete it.

Keep normal tool outputs, Bash exit/cancellation behavior and existing operation with the feature disabled intact. Implement the feature in Pi's production code and add appropriate tests. Do not change existing tests to suppress regressions, dependency manifests or lockfiles, generated model data, or build/test configuration.
