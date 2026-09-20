# Behavioral verifier coverage

These are verifier scenarios, not claims that any implementation has passed.
The coordinator holds expectations outside the candidate process and compares
real files, Git state, public results and captured local provider requests.

| Case | Public requirement checked |
| --- | --- |
| sdk_public_contract | Opt-in SDK, public state, one stable checkpoint per request and actual rollback to the preceding effective conversation |
| runtime_fork_contract | Real public runtime fork succeeds in ready state, creates the expected session/conversation boundary, and makes no provider request or file/Git mutation |
| disabled_regression | Disabled behavior, empty list and side-effect-free rejection |
| in_memory_rejected | Persistent sessions required when enabled |
| normal_files_and_conversation | Actual edit/write/bash; bytes, permissions, create/delete/rename; pre-existing dirty files; effective context; immediate restart |
| checkpoint_branch_and_idempotence | Actual second-request rollback preserves the first request's files and effective conversation; direct rollback across multiple requests restores the selected earlier boundary; repeat success; new branch after rollback; abandoned target rejected |
| invalid_and_foreign_targets | Invalid and another session's actual checkpoint IDs rejected; normal navigation to an ancestor excludes later checkpoints and rejects their IDs without side effects |
| idle_external_conflict | Complete preflight rejection; explicit path; no partial files or context changes; successful retry after the conflicting edit is resolved preserves unrelated human work |
| idle_unrelated_changes_preserved | Successful rollback preserves unrelated idle modification and newly created human file |
| file_becomes_nested_directory | Real Bash replaces a tracked file with nested directories/files and another original directory with a regular file; rollback restores both original shapes and survives restart |
| idle_descendant_conflict | Restoring an original file over a directory cannot discard a human-added descendant; whole operation rejects |
| between_requests_external_conflict | Human edits between requests cannot be silently discarded by an earlier rollback |
| failed_bash_changes | Nonzero exit code preserved; preceding mutations remain reversible |
| cancelled_bash_changes | Actual cancellation after Bash mutation; settled state and recovery |
| running_request_busy | Rollback rejects while a real model request is outstanding |
| interrupted_request_recovery | Kill after tool result is sent to next real provider request; preserve work on resume; block model, bash, changed-target navigation, real runtime fork and compaction; user-selected recovery |
| first_request_interruption | Kill the first request before any assistant response; checkpoint and recovery gate survive |
| repeated_interrupted_resume | Restart and kill repeatedly while awaiting user selection; preserve checkpoint identity and interrupted files |
| inflight_bash_recovery | Kill process tree while Bash waits on an external FIFO after partial filesystem changes |
| rollback_process_interruption | Kill at the first observed restoration mutation, and again during startup if another file mutation is needed; asynchronous startup is allowed, and real provider requests must observe complete recovery |
| rollback_concurrent_prompt | Prompt submitted alongside rollback either rejects or reaches the real provider only after files and conversation have been restored |
| filesystem_failure_retry | Ordinary filesystem access failure without Git ownership changes cannot report success; complete preflight refusal is allowed, while a pending restore remains inspectable and gated after restart; retry after access restored |
| steering_followup_single_checkpoint | A real retry after a transient HTTP provider error, steering and queued follow-up all stay within the initial request boundary |
| rpc_cli_contract | Real CLI flag and JSON-lines RPC operations, existing success/error envelope, actual restoration and subsequent provider context |
| rpc_cli_resume_recovery | CLI opt-in persists across restarts; unfinished execution gate and durable RPC recovery |
| tui_rollback_command | Real interactive checkpoint listing and rollback command (separate PTY scenario) |

Version `0.0.3` keeps all 25 scenarios while matching the shorter, first-person
statement. Checkpoints need stable IDs, but need not expose `sessionId` or
`entryId`, and their list order is unrestricted. Multi-request cases identify a
new checkpoint by comparing ID sets. Conversation boundaries are checked by
performing rollback and comparing effective message content, rather than
reconstructing a boundary from checkpoint metadata. Both restoration of the
immediately preceding boundary and direct rollback across multiple completed
requests are exercised.

The existing RPC envelope and the documented list payload remain required;
successful rollback may return an empty acknowledgement. A preflight conflict's
diagnostic status does not determine its score: complete refusal, a useful path,
unchanged files and conversation, and successful retry after conflict resolution
do. The documented state vocabulary and execution gates remain in force.
These changes remove representation requirements without removing crash,
concurrency, branch, permission, Git-state or manual-edit protection checks.

The loopback provider supplies only model tool calls and text. It never performs
file mutations, checkpoints, session rewinds or crash recovery. The peer is a
transport wrapper around the normal built SDK. No case reads or edits private
candidate journal files, patches candidate methods or matches source text.
Git invariants cover HEAD, branch refs and index entries; private checkpoint
refs are allowed. Regular-file names are not restricted to language-safe keys.

Failure injection assumes the full execution process tree stops, as stated in
the task. The Linux supervisor is exercised separately with direct writes,
rename replacement, concurrent workers and Bash descendants. The reward writer
must also require the fixed case inventory, scope checks, a fresh build and the
independent existing-suite regression result; this runner alone is not a reward.

Version `0.0.4` adds a ready-state public runtime fork calibration and fixes
the recovery gate to call that same real runtime. Recovery navigation/fork may
throw an explained error or return the documented `{ cancelled: true }`; the
checks then observe the actual runtime session, effective messages, protected
fixture files, and provider requests. State must remain enabled and unresolved,
without imposing a particular unresolved status transition. Same-leaf navigation
is a documented no-op, so recovery navigation checks choose a different target.
An exception caused by a missing method or receiver is not a valid gate result.
