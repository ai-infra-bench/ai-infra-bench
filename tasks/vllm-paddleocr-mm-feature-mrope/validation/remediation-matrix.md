# Remediation matrix

| ID | Severity | Finding and evidence | Planned change | Validation | Status |
|---|---|---|---|---|---|
| C1 | blocking | The instruction presented two requests and a concrete trace as source facts, but the tracker/PR only state that token search is inefficient and can disagree with `mm_features`. | Describe the mismatch as the attached executable reproduction rather than an upstream user report. | Every factual statement maps to issue #32656, PR #39888, or the public reproduction. | fixed and validated |
| C2 | blocking | Torch cutoff overrides had no reason in task metadata or the lock manifest. | Record that the pinned base requirements need torch 2.11 CPU wheels uploaded after the source cutoff. | Task metadata, lock manifest, and evidence contain the same reason. | fixed and validated |
| C3 | blocking | The image predates the hardened cutoff-aware environment. | Regenerate and rebuild with snapshot packages, cutoff-compatible tools, offline dependencies/Cargo vendor, deterministic extensions, and scoped caches. | Initial/warm digests match and isolation gates pass. | fixed and validated |
| C4 | blocking | E2E asserted sentinel invariance before executing the video temporal control in Base. | Compute and report both image and video cases before target assertions. | Base and Oracle cross the video control in five rounds; only Oracle satisfies sentinel invariance. | fixed and validated |
| C5 | blocking | Evidence references the old image and omits solve/helper hashes, review rounds, substitutions, and checksum scope. | Refresh hashes, actual results, limitations, and Harbor identifiers. | Final evidence hash audit matches current artifacts and records checksum scope. | fixed and validated |
