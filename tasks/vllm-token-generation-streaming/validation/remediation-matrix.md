# Remediation matrix

| ID | Severity | Finding and evidence | Planned change | Validation | Status |
|---|---|---|---|---|---|
| C1 | blocking | The image predates the hardened cutoff-aware environment and installs Rust/nextest releases newer than the task cutoff. | Rebuild with snapshot packages, verified cutoff-compatible tools, conditional Cargo vendor/offline config, exact Python lock, deterministic extensions, and scoped caches. | Initial/warm digests match; cutoff tool versions, isolation, and dependency gates pass. | fixed and validated |
| C2 | blocking | The real HTTP matrix asserted the stream contract before issuing the non-streaming request, so Base never covered both response lifecycles. | Complete and measure both HTTP requests before target assertions. | Base and Oracle both cross SSE and JSON paths; only Oracle satisfies the streaming contract. | fixed and validated |
| C3 | blocking | Evidence references the old image and omits solve/helper hashes, review rounds, substitutions, limitations, and checksum scope. | Refresh hashes, measured results, limitations, build reproducibility, and Harbor identifiers. | Final evidence hash audit matches current artifacts. | fixed and validated |
