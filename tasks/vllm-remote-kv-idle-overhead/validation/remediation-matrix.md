# Remediation matrix — v1.6.0

| Review finding | Changed behavior / verification | Control |
|---|---|---|
| Candidate replaces measurement globals and receives full credit | Root-owned scorer does not import candidate code; parent reads process CPU clock and checks actual response contents | `forged-measurement-globals`, `forged-success-response` |
| Child can report invented resource success | Native allocator counter has no reset API; parent verifies a fresh nonce and authentic byte-count packet | `forged-allocation-observation`, independent allocation/reclamation calibration |
| Root startup could process candidate `.pth` imports | Supervisor and compiler include lookup use `-I -S`; site processing occurs only after the child drops UID | Root/child process separation in the actual grading entrypoint |
| Engine stops polling with only remote work | Real `EngineCore.step()` drives completion events, generation, terminal outputs and subsequent admission; unfinished counts are checked | `missing-unfinished-remote`, all-remote backpressure lifecycle |
| Cheap O(N) snapshots pass small timing tests | 64/1,024/8,192 waiters, pure and mixed waits, repeated parent-owned CPU measurements | `linear-idle-snapshot`, Base, mixed-only shortcut |
| Mapping order mistaken for FCFS | Observe admission with one available slot; compare token maps by request identity | `reordered-token-map` positive, mixed grammar/remote/streaming waits |
| Oracle inherits block-ID retention | Drain recorded attention block IDs on every scheduling step; preserve use when zeroing is required | `undrained-kv-block-ids` negative |
| Heap positive retains completed versions | Remove obsolete version entries; globally increasing version still distinguishes stale heap entries | `unbounded-ready-versions` negative, repaired heap positive |
| Long-run resource check misses small per-request leaks | Real sequential lifecycle to 1,310,720 requests per local/remote mode; public 32 MiB budget, idle/GC cleanup opportunities | Both leak negatives; bounded-cache and batched-reclamation positives |
| Completion can be faked by exit/PASS | Parent must finish every required behavior group and observe normal worker shutdown | `SystemExit(0)`, `os._exit(0)`, printed success |
| Reference solution could encode only existing examples | Separate challenge varies prompt lengths, local/remote mode, identity reuse, Unicode IDs and repeated drained workloads | Oracle and repaired heap run separately from final grading |

Actual rewards, first failures, timings, executable hashes and Harbor trial IDs are in [e2e-evidence.json](e2e-evidence.json). Development runs and superseded results are not presented as final-snapshot runs. Historical callback/packet controls are archived because their old in-process protocol no longer exists; the new forged-response and authenticated-resource controls exercise the replacement boundary.
