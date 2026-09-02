# Remediation matrix

| ID | Severity | Finding and evidence | Planned change | Validation | Status |
|---|---|---|---|---|---|
| C1 | blocking | PR #47007 has no linked user issue; the instruction must not invent an incident. | Start from the PR-supported unbounded-work symptom and disclose the deterministic renderer reduction. | Source timeline and public Base/Oracle outputs align. | fixed |
| C2 | blocking | Environment and exact cutoff lock are not materialized. | Build a hardened canonical image with the self-contained renderer fixture. | Lock, image reproducibility, Git, dependency, hidden-artifact, and network gates pass. | fixed |
| C3 | blocking | Verifier independence and error boundaries require validation. | Cover both sides, sync/async, tokenizer ratios, unbounded configs, validation, and token inputs. | Five Base/Oracle rounds, alternative 1, and partial fixes 0. | fixed |
| C4 | blocking | Evidence and Harbor identifiers are missing. | Record actual hashes, results, limitations, image, and final Harbor run. | Evidence audit and Harbor Oracle pass. | fixed |
| C5 | blocking | The initial draft used the PR creation-time base `81bcced4…`, not squash merge `c231d1f…`'s unique parent `db808b3…`. | Pin the unique merge parent and its commit-time dependency cutoff, then regenerate the lock and Dockerfile. | All Oracle/control patches apply to `db808b3…`; image HEAD and evidence source match it. | fixed |
| C6 | blocking | The first tokenizer-default regression used 90 characters under a 100-character bound, so an overbroad pre-truncation patch never executed and scored 1. | Raise that default-side input to 150 characters and require the tokenizer to receive it intact. | Oracle and the alternative pass; pre-trimming without an explicit side scores 0. | fixed |
