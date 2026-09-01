# Remediation matrix

| ID | Severity | Finding and evidence | Planned change | Validation | Status |
|---|---|---|---|---|---|
| C1 | blocking | The image predates the hardened shared environment and its cutoff-aware toolchain selection. | Regenerate and rebuild from the cutoff snapshot with verified tools, offline locks/Cargo vendor, deterministic extensions, and scoped caches. | Initial/warm digests match and isolation gates pass. | fixed and validated |
| C2 | blocking | E2E asserted the race scenario before running IPC, crash, and configured-timeout controls in Base. | Execute and report all four scenarios before target assertions. | Base and Oracle cross every E2E control in five rounds; only Oracle satisfies the race contract. | fixed and validated |
| C3 | blocking | A timed-out scenario killed only the Python parent and could leave spawned API children alive. | Run each scenario in a process group and terminate/kill the group on timeout. | Repeated rounds finish without residual processes or port conflicts. | fixed and validated |
| C4 | blocking | Evidence references the old image and omits solve/runner hashes, review rounds, substitutions, and checksum scope. | Refresh hashes, actual results, limitations, and Harbor identifiers. | Final evidence hash audit matches current artifacts and records checksum scope. | fixed and validated |
