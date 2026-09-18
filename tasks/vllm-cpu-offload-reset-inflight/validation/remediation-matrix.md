# Remediation matrix for 0.0.2

| Finding | Artifact change | Executed evidence |
|---|---|---|
| Store/load fixtures omitted the request-finished event named by the task workflow | `start_store()` and `start_load()` now call the real connector `request_finished()` after transfer metadata is created and before completion | Historical Attempt 5 changes from 12/26 reward 0 to 30/30 reward 1 |
| Tests bypassed the final-request EngineCore liveness path by directly delivering completion | Added eager/lazy store/load cases requiring both `has_pending_push_work()` and `Scheduler.has_requests()` while work is pending; composed lifecycle checks the same boundary before every completion | Attempts 2/6 fail two load-liveness cases; Attempts 3/4 fail all four liveness cases |
| Oracle and claimed correct alternatives did not keep store/load completion polling alive | Oracle now reports every active or abandoned transfer/pin through the standard pending-work hook; former alternatives are retained as negative legacy controls | Oracle and two new liveness-complete alternatives receive reward 1; both legacy alternatives receive 0 |
| Lifecycle grading trusted a candidate process exit code of zero | A verifier-owned parent requires one exact final lifecycle record and kills the entire child process group on incomplete termination | Reachable `SystemExit(0)` and `os._exit(0)` controls both receive reward 0 in Docker and Harbor |
| No control distinguished store-only liveness from complete store/load liveness | Added `store-only-liveness.patch` | Store phase passes, load-only liveness fails, final reward 0 |
| Existing evidence described incomplete alternatives as correct | Archived 0.0.1 evidence under `validation/history/` and replaced it with executed 0.0.2 results | Final strict artifact audit checks the new executable hashes |
