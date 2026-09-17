# Current remediation matrix — v1.5.0

| Concern | Current evidence / remediation | Status |
|---|---|---|
| Idle-only checks miss lifecycle defects | Production Scheduler admission, ready events, streaming, outputs, cleanup and FCFS reset/backlogs | 11 ordinary Harbor controls match expected rewards |
| Object-retention assertions reject reasonable caches | Weakrefs diagnostic only; public 32 MiB additional retained-Python-memory budget | Versioned contract, not retroactive scoring |
| Resource-check fairness | Different queue implementation, bounded cache and batched reclamation | Oracle and three positives each 18/18 |
| Historical regrading versus new model results | Historical answers regrade 1/0/0; three subsequent fresh v1.5.0 answers score 1/1/1 | Separate summaries and trajectory reviews |
| Offline upstream tests | Pinned OPT/LLaVA config and tokenizer metadata remain required | Environment inputs unchanged |
| Publication clutter | One review/index, current evidence ZIP, historical ZIP and immutable old Opus archive link | Executable and control bytes preserved |
| Grading integrity | Five prior security controls retained but not rerun | Separate trust review remains open |
| Scope limits | Scheduler subsystem with deterministic model/transport, finite Python-allocation workload | No HTTP/RDMA/full-model or unlimited-lifetime proof |

See [review-report.md](review-report.md) and [e2e-evidence.json](e2e-evidence.json). The publication cleanup itself adds no model calls or behavioral runs.
