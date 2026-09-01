# Remediation matrix

| ID | Severity | Finding and evidence | Planned change | Validation | Status |
|---|---|---|---|---|---|
| C1 | blocking | The image predates the hardened cutoff-aware environment. | Regenerate and rebuild with snapshot packages, verified tools, offline dependencies/Cargo vendor, deterministic extensions, and scoped caches. | Initial/warm digests match and isolation gates pass. | fixed and validated |
| C2 | blocking | HTTP E2E parsed and asserted the single tool before sending the parallel-tool request in Base. | Complete both real TCP/SSE requests before target assertions. | Base and Oracle cross both HTTP scenarios in five rounds; only Oracle preserves valid per-tool arguments. | fixed and validated |
| C3 | blocking | HTTP E2E reported `completed_calls: 3` as a constant rather than measured output. | Compute call count and single/parallel validity from emitted SSE items. | Base reports two calls and false validity; Oracle reports three calls and both validity flags true. | fixed and validated |
| C4 | blocking | Evidence references the old image and omits solve/helper hashes, review rounds, substitutions, and checksum scope. | Refresh hashes, actual results, limitations, and Harbor identifiers. | Final evidence hash audit matches current artifacts and records checksum scope. | fixed and validated |
