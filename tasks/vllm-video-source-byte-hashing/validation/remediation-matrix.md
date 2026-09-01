# Remediation matrix

| ID | Severity | Finding and evidence | Planned change | Validation | Status |
|---|---|---|---|---|---|
| C1 | blocking | The image predates the hardened cutoff-aware environment. | Rebuild with snapshot packages, verified cutoff-compatible tools, exact Python lock, conditional Cargo vendor/offline config, deterministic extensions, and scoped caches. | Initial/warm digests match; isolation and dependency gates pass. | fixed and validated |
| C2 | blocking | The real video I/O script asserted transport equality before loading the 2-frame and 8-frame sampling controls. | Complete bytes, file, base64, and both sampling paths before target assertions, and print measured booleans. | Base and Oracle both cross every I/O path; the report contains measured transport, shape, and sampling results. | fixed and validated |
| C3 | blocking | The instruction requires base64/JPEG frame-list compatibility, but the verifier only covered base64 MP4. | Add a real `video/jpeg` frame-list round trip through `VideoMediaIO`, the public parser, and the hasher. | Base, Oracle, and conforming alternatives preserve frame shape, metadata, tuple behavior, and stable hashing. | fixed and validated |
| C4 | blocking | Evidence references the old image and omits solve/helper hashes, review rounds, substitutions, limitations, and checksum scope. | Refresh hashes, measured results, limitations, build reproducibility, and Harbor identifiers. | Final evidence hash audit matches current artifacts. | fixed and validated |
