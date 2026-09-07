# Remediation matrix for 0.0.2

| Finding | Artifact change | Executed evidence |
|---|---|---|
| Synthetic cases populated the old `async_tokens_to_discard` representation | Removed direct request/scheduler state construction; every scored case now admits requests with `schedule()` and returns output with `update_from_output()` | All eight historical Agent patches now receive reward 1 in the local full grader |
| Speculative drafts were inserted after candidate scheduling hooks ran | Draft IDs are supplied before `schedule()` so the real scheduler creates `scheduled_spec_decode_tokens`, scheduled widths and placeholders | Frame-width ledger alternative: 16/16 and lifecycle pass, reward 1 in Docker and Harbor |
| One batch was manually split into stale/current requests although reset invalidates a whole queued scheduler output | Replaced it with a stale multi-request batch followed by a separately scheduled current batch | Base fails on stale mutation; Oracle and all correct alternatives preserve the resumed batch |
| Consecutive reset test injected speculative drafts into resumed waiting frames | The first stale frame is speculative; ten queued frames produced immediately after reset are non-speculative, matching the FIFO schedule/reset lifecycle | 24 requests, 11 resets, 264 stale request frames and 384 stale placeholder slots |
| Lifecycle grading trusted a child process exit code of zero | A verifier-owned parent process requires one exact final completion record after all assertions | Reachable `SystemExit(0)` and `os._exit(0)` controls both receive reward 0 in Docker and Harbor |
| The only positive alternative retained the Oracle's private request state | Added reset-generation, callback-ledger and per-frame-width alternatives | Four semantically different alternatives plus Oracle receive reward 1 in Docker and Harbor |
| Evidence claimed the verifier did not depend on a private field although the tests assigned it | Replaced the 0.0.1 evidence and retained it under `validation/history/` | Final strict artifact audit checks the 0.0.2 executable hashes |
