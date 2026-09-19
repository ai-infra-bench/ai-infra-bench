# Current remediation matrix — v1.8.6

| Concern | Remediation / evidence | Status |
|---|---|---|
| Declared A100 environment selects FA2 while prior calibration used H20/FA3 | Add zero-context bypass, mixed-row FA2 handling, stable graph outputs, and nonzero DCP capture metadata; run the official verifier on A100 ×2 | Oracle reward 1, 24/24, worker exit 0 |
| Local real-backend fixture sends an unsupported FA2 mixed batch directly to the kernel | Evaluate FA2 mixed-prefill rows separately in the component fixture; retain full production batching in fourteen engine combinations | Component eager/graph and all full-engine cases pass |
| Asynchronous CUDA assertions surfaced later in sampling | Log FA version, block size, rank, graph mode and lifecycle step; synchronize immediately after model execution | Failures are attributed to the launching case |
| Validation scope | Record direct official-verifier runs for Oracle and unmodified Base in the pinned image; preserve historical evidence by version | Oracle 24/24 and Base 2/24; other controls, model answers, security probes and full control matrix were not rerun |

## Historical v1.8.4 calibration

| Concern | Remediation / evidence | Status |
|---|---|---|
| Partial-prefill FI logprob corruption missing from v1.8.3 | Real NHD/HND eager/graph, maxbatch32; independent CPU full-vocabulary comparison; Oracle LSE-unit conversion | Historical full Harbor status in e2e-evidence.json |
| FA interleave-1 graph startup reused stale dummy metadata | Real NHD/HND graph interleave-1; Oracle honors skip-attention dummy; alternative refreshes dummy metadata | Two semantically distinct fixes, no internal signature assertion |
| Old reward 1 does not imply all newly examined behaviors correct | Preserve original GPT-6 r01 and old Oracle; identify the old Oracle negative and curated positive explicitly | No rewritten score or curated patch counted as a model attempt |
| Version and reproducibility | Freeze executable bytes/image, 24 checkpoints and 14 complete engine combinations | Historical results remain attached to their benchmark revisions |

## Historical v1.8.3 calibration

| Concern | Remediation / evidence | Status |
|---|---|---|
| Eagle fixture freezes internal `prepare_inputs` signature | Normal execution, sampling and draft output transport; no signature introspection or candidate adapter | Oracle/r01 21/21; r02 passes all three Eagle groups |
| Irrelevant batch-order assumptions | Match request IDs; add reversed-length requests | Three Eagle input groups |
| Interface fix must not hide a real defect | Preserve independent FA/FI NHD/HND eager/graph generation | r02 scores 0 at 19/21 for an HND numeric error; Base scores 0 at 2/21 |
| Non-DCP Eagle preservation | Unchanged known regression as negative control | Scores 0 at 13/21 for wrong draft tokens, not an API error |
| Historical scores versus rescoring | Preserve original r01/r02 scores, sources and traces | No new model attempts |
| Reproducibility | Frozen inputs, exact image, GPU binding, saved tracked/untracked source comparison | Two GPU lanes on shared H20 |
| Eagle fixture scope | Deterministic target/draft models, known cache, permissive scheduler grammar mask | Runner integration, not grammar compiler or real-weight Eagle E2E |
| Security and dependency boundary | Existing grading-trust and native-donor/cutoff limitations | Not newly certified |

See [a100-fa2-validation.md](a100-fa2-validation.md), [review-report.md](review-report.md), and [e2e-evidence.json](e2e-evidence.json). Functional validation is not unconditional merge approval.
