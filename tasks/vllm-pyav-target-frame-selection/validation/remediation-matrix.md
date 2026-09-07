# Remediation matrix (v0.0.2)

| ID | Severity | Finding | Change | Executed validation | Status |
|---|---|---|---|---|---|
| V4 | blocking | All generated verifier videos began at PTS 0, so implementations that treated timestamps as zero-origin received reward 1 even when `stream.start_time` was nonzero. | Add real H.264 cases with a nonzero stream start for uniform, dynamic, and Nemotron public loaders; update the Oracle to seek relative to `stream.start_time`. | The legacy Oracle and two affected historical patches receive 0; the updated Oracle, independent correct alternative, and six start-time-aware historical patches receive 1. | fixed |
| V5 | blocking | Counting 20 JUnit cases did not prove that the intended tests ran, and a zero-status process exit could leave stale output. | Require the exact 23-test node set, delete prior outputs before execution, and add `SystemExit(0)` plus `os._exit(0)` controls. | Both early-exit controls receive 0 in direct Docker and Harbor runs; Oracle reports exactly 23 passed. | fixed |
| C1 | project rule | Agent timeout was 18 hours instead of the repository-standard 10 hours. | Set `[agent].timeout_sec = 36000`. | Repository validator and strict artifact audit. | fixed |
| E2 | evidence | v0.0.1 evidence described the pre-hardening verifier. | Preserve it under `validation/history/` and record fresh v0.0.2 hashes and run identifiers. | Hash audit against the final task tree. | fixed |
