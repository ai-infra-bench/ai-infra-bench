# Current remediation matrix — v1.8.4

| Concern | Remediation / evidence | Status |
|---|---|---|
| Partial-prefill FI logprob corruption missing from v183 | Real NHD/HND eager/graph, maxbatch32; independent CPU full-vocabulary comparison; Oracle LSE-unit conversion | Current full Harbor status in e2e-evidence.json |
| FA interleave1 graph startup stale dummy metadata | Real NHD/HND graph interleave1; Oracle honors skip-attention dummy; alternative refreshes dummy metadata | Two semantically distinct fixes, no internal signature assertion |
| Old reward1 does not imply all newly examined behaviors correct | Preserve original GPT6 r01 and old Oracle; old Oracle negative and curated positive are explicitly identified | No rewriting or counting a curated patch as a model attempt |
| Version and reproducibility | Freeze executable bytes/image, 24 checkpoints / 14 complete engine combinations | Changed benchmark revision; remaining serial attempts not same-version pass@k |

## Historical v1.8.3 calibration (not inherited as v1.8.4 scores)

| Concern | Remediation / evidence | Status |
|---|---|---|
| Eagle fixture freezes internal prepare_inputs signature | Normal execution, sampling and draft output transport; no signature introspection or candidate adapter | Oracle/r01 21/21; r02 passes all three Eagle groups |
| Irrelevant batch-order assumptions | Match request IDs; add reversed-length requests | Three Eagle input groups |
| Interface fix must not hide a real defect | Preserve independent FA/FI NHD/HND eager/graph generation | r02 scores0 at19/21 for actual HND numeric error; Base scores0 at2/21 |
| Non-DCP Eagle preservation | Unchanged known regression as negative control | Scores0 at13/21 for wrong draft tokens, not an API error |
| Historical scores versus rescoring | Preserve original r01/r02 scores, sources and traces | No new model attempts |
| Reproducibility | Frozen inputs, exact image, GPU binding, saved tracked/untracked source comparison | Two GPU lanes on shared H20 |
| Historical controls | Archive old manifests; unexecuted cases pending-v183 | Do not inherit v1.8.2 validation |
| Eagle fixture scope | Deterministic target/draft models, known cache, permissive scheduler grammar mask | Runner integration, not grammar compiler or real-weight Eagle E2E |
| Environment and Oracle | Same dual-GPU offline image, fixed HND Oracle, single-split FA graph setting | Unchanged; no new public tests |
| Security and hardware | Existing grading-trust, dependency/cutoff and A100 limitations | Not newly certified |
| Publication | Local authorized verifier repair | No commit/push |

See [review-report.md](review-report.md) and [e2e-evidence.json](e2e-evidence.json). Functional calibration is not unconditional merge approval.
