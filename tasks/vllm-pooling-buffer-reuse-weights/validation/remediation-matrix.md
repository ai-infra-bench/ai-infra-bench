# Remediation matrix

| ID | Severity | Finding and evidence | Planned change | Validation | Status |
|---|---|---|---|---|---|
| C1 | blocking | New task provenance and symptom boundary require validation against PR #39650 and later mapper follow-up #50890. | Keep the contract on buffer reuse and packed remapping without importing later mapper functionality. | Public Base corrupts weights/output; Oracle matches the ordinary reference. | fixed |
| C2 | blocking | Environment and cutoff lock are not materialized. | Generate the hardened image and complete isolation/reproducibility audits. | Lock dry-run, image digest stability, dependency, Git, hidden-file, and network gates pass. | fixed |
| C3 | blocking | Verifier controls are missing. | Cover ordinary and reusing iterators, prefix variants, packed shards, streaming consumption, and output equivalence. | Five Base/Oracle rounds, positive alternative, and distinct partial fixes behave as expected. | fixed |
| C4 | blocking | Final evidence and Harbor records are missing. | Record actual hashes, runs, substitutions, limitations, and Harbor identifiers. | Evidence audit and Harbor Oracle pass. | fixed |
| C5 | blocking | The first Oracle verifier compared the intentionally absent pooling `lm_head` against a full-model reference and could not construct the reference for relative checkpoint names. | Compare only retained pooling parameters and normalize both supported checkpoint prefix forms in the independent reference loader; keep the separate missing-head assertion. | Oracle passes all simple, packed, ordinary, relative-prefix, and missing-head cases; Base still fails only buffer-reuse behavior. | fixed |
