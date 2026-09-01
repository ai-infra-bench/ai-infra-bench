# Remediation matrix

| ID | Severity | Finding and evidence | Planned change | Validation | Status |
|---|---|---|---|---|---|
| C1 | blocking | The torch cutoff override has no reason in task metadata or the lock manifest. | Record that the pinned base requirements need torch 2.11 CPU wheels uploaded after the source cutoff. | Task metadata, regenerated lock, and evidence contain the same reason. | fixed and validated |
| C2 | blocking | The image predates the hardened environment and installs Rust 1.95/nextest 0.9.133 after the April 13 cutoff. | Rebuild with the cutoff snapshot, Rust 1.94.1, nextest 0.9.132, protoc 34.1, exact lock, deterministic extensions, and scoped caches. | Initial/warm digests, tool versions, isolation, and dependency gates pass. | fixed and validated |
| C3 | blocking | HTTP E2E raised on the first missing reason series, so Base did not emit a complete two-engine observation. | Measure both totals and both reason series for both engines, print the observation, then assert the contract. | Base reports totals with null reason values; Oracle reports the complete 2×3 matrix. | fixed and validated |
| C4 | blocking | The verifier did not explicitly protect request ordering despite the observability-only scope. | Add a real Scheduler FCFS selection check that does not read new stats fields. | Base, Oracle, and conforming alternatives schedule the first two capacity requests in arrival order. | fixed and validated |
| C5 | blocking | Evidence references the old image and omits solve/helper hashes, review rounds, substitutions, limitations, and checksum scope. | Refresh hashes, measured results, limitations, reproducibility, and Harbor identifiers. | Final evidence hash audit matches current artifacts. | fixed and validated |
