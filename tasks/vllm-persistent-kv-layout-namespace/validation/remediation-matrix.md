# Remediation matrix for 0.0.2

| Finding | Artifact change | Executed evidence |
|---|---|---|
| Legacy portable V1 compatibility was rewarded but not explicit in the statement | State that compatible V1 files written before the fix must remain readable across supported parallel configurations | Attempts 2–5 and 8 now fail one explicit legacy case rather than an unstated requirement |
| “Safe sharing” could be read as requiring every byte-compatible V1/V2 combination to share | Limit the contract to portable V1 sharing; V1 and V2 need not share a namespace | Oracle and runner/cache-format alternatives now match the written scope |
| V1 runner fixtures omitted the HND backend's block-stride indexing signal | Set `indexes_kv_by_block_stride=True` before `build_offloading_config` | Attempt 8 changes from 10/19 to 18/19; only its legacy namespace migration remains wrong |
| Synthetic cases bypassed the real runner config boundary | Build varied incompatible layouts through `build_offloading_config` | Attempts 1 and 7 change from 15/19 reward 0 to 19/19 reward 1 |
| Direct `OffloadingConfig(...)` construction rejected candidate-added normalized fields | Derive manual parallel variants with `dataclasses.replace()` from a real candidate config | Attempt 6 changes from 6/19 reward 0 to 19/19 reward 1 |
| Existing positive alternatives all reused Oracle's classification field | Add runner cache-format, required runner-version, and physical-layout alternatives | All three receive 19/19, attested lifecycle, reward 1 in Docker and Harbor |
| Lifecycle trusted a candidate process exit code of zero | Add a verifier-owned parent, exact completion record, timeout, and process-group cleanup | Reachable `SystemExit(0)` and `os._exit(0)` controls both receive reward 0 after pytest passes 19/19 |
| Stale verifier output and arbitrary 19-case JUnit files could satisfy weak integrity checks | Clear verifier outputs before execution and require the exact test-name set | Base and all negative controls remain reward 0; Oracle remains reward 1 |
| Candidate artifacts were not guaranteed to be captured before verifier execution | Add a pre-verifier collect hook and patch whitespace attributes | Harbor snapshots contain tracked and untracked candidate artifacts |

## Frozen semantic boundary

```text
V1 or V2 runner configuration plus a persistent cache root
-> real offloading configuration classification and filesystem namespace selection
-> an incompatible cross-runner lookup misses, while compatible restart data hits and loads intact
-> pre-fix portable V1 files remain readable under compatible parallel configurations
```

Model execution is a substitutable producer/consumer for this task. The real
configuration builder, `FileSystemTierManager`, asynchronous filesystem I/O,
block files, shutdown/reopen lifecycle, and cross-process persistence are the
behavior-determining components.
