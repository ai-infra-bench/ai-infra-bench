# Remediation matrix

| ID | Severity | Finding and evidence | Planned change | Validation | Status |
|---|---|---|---|---|---|
| C1 | blocking | PR #49805 has no linked issue and the later cross-reference to #39663 must not be rewritten as its original trigger. | Start from the PR's online-FP8 CI failure and preserve the backend-specific surface symptom. | Source timeline, public reproduction, and final instruction agree. | fixed |
| C2 | blocking | Environment and cutoff lock are not materialized. | Build a hardened image at the squash merge parent with a CPU layerwise fixture. | Lock, warm digest, Git, dependency, layer, hidden-file, and network audits pass. | fixed |
| C3 | blocking | Verifier independence and controls require validation. | Observe processing timing and values through real production loaders while preserving meta and never-loaded behavior. | Base/Oracle five rounds, one alternative 1, and three partial fixes 0. | fixed |
| C4 | blocking | Evidence and Harbor identifiers are missing. | Record actual hashes, limitations, runs, image, and final Harbor result. | Evidence audit and Harbor Oracle pass. | fixed |
