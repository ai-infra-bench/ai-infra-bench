# Remediation matrix

| ID | Severity | Finding and evidence | Planned change | Validation | Status |
|---|---|---|---|---|---|
| C1 | blocking | The instruction invented a deployment-profile user; PR #45196 describes the loader/config failures directly. | Replace the persona with the source-backed `DefaultModelLoader` and `LoadConfig` behavior. | Every factual statement maps to PR #45196, follow-up #46220, or executable reproduction. | fixed and validated |
| C2 | blocking | The image predates the hardened shared environment template. | Regenerate and rebuild with cutoff snapshots, verified tools, offline dependency closure, deterministic extensions, and template-scoped caches. | Initial/warm image digests match and all isolation gates pass. | fixed and validated |
| C3 | blocking | Real service tests terminate only the CLI parent and can leave engine children running. | Start each CLI in a process group and terminate or kill the group in cleanup paths. | Base and Oracle finish all five CLI scenarios in five rounds without leaked processes. | fixed and validated |
| C4 | blocking | The 180-second E2E wrapper is too close to five sequential CPU engine attempts. | Raise the wrapper to 360 seconds while retaining 45/60-second per-scenario bounds. | Five repeated rounds finish without masking a hung scenario. | fixed and validated |
| C5 | blocking | Evidence references the old image and omits solve/helper hashes, substitutions, review rounds, and checksum scope. | Refresh complete hashes, actual results, limitations, and Harbor identifiers. | Final evidence hash audit matches current artifacts and records checksum scope. | fixed and validated |
