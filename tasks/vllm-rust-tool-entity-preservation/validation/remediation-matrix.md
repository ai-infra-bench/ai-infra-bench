# Remediation matrix

| ID | Severity | Finding and evidence | Planned change | Validation | Status |
|---|---|---|---|---|---|
| C1 | blocking | The image predates the hardened cutoff-aware environment and evidence says Cargo fetches during verification. | Rebuild with snapshot packages, verified tools, Cargo vendor/offline config, exact Python lock, deterministic extensions, and scoped caches. | Initial/warm digests match; verifier Cargo build runs offline; isolation gates pass. | fixed and validated |
| C2 | blocking | E2E asserted the first parser/mode before running the remaining seven matrix cells in Base. | Collect and report all four parsers in complete and streaming modes before asserting preservation. | Base and Oracle both cross all eight cells; only Oracle preserves every literal value. | fixed and validated |
| C3 | blocking | Evidence references the old image and omits solve/helper hashes, review rounds, substitutions, and checksum scope. | Refresh hashes, actual results, limitations, and Harbor identifiers. | Final evidence hash audit matches current artifacts. | fixed and validated |
