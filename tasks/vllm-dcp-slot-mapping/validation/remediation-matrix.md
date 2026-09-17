# Current remediation matrix — v1.8.2

| Concern | Current remediation / evidence | Status |
|---|---|---|
| Two-GPU instruction but one-GPU environment | Two GPUs, shm2GiB, ordinary offline model/tokenizer retained from v1.8.1 | Environment unchanged this revision; no public reproducer |
| Layout coverage depended on defaults | Explicit FA/FI × NHD/HND × eager/graph, normal TP2/DCP2 engine, independent CPU full-vocabulary reference | Eight combinations, twenty-one required checkpoints |
| Historical Oracle accepted despite HND output corruption | Separate paged-cache layout from token-major uncached K/V layout; old Oracle retained unchanged as a negative control | Repaired Oracle21/21, saved GPT21/21; historical Oracle0 at19/21 due real FI HND logprob corruption |
| Implementation-dependent local-length check | Keep v1.8.1 removal of optional runner-populated metadata from synthetic consumers; real numerical checks retained | Saved GPT backend-local implementation used as complete alternative control |
| New coverage must reject real defects | Base, unchanged historical HND Oracle, stale FA graph, missing FI repair, non-DCP Eagle regression | All five score0 for actual behavior defects; all seven Harbor trials complete without harness error |
| Historical positives not validated on layout matrix | Three patches and original case identities moved to history/v181-positive-controls | Preserved, not represented as current positives |
| Experimental provenance | Frozen inputs before execution; prepared-input hashes after execution; saved GPT tracked/untracked files compared | No new model calls; original rewards unchanged |
| FA3 graph fixture startup incompatibility | Single-split supported setting already disclosed in instruction | Real graph remains enabled; unrelated kernel fix not required |
| Hardware / dependency scope | Shared H20 x2, same pinned image and cutoff disclosure | A100 and dependency limitations remain open |
| Grading integrity | Security controls retained but not rerun or newly certified | Separate trust review remains open |
| Publication | Calibrated v1.8.2 revision and attributable evidence; subsequently authorized for existing PR60 | Calibration itself made no commit/push; publication identity is in Git history |

See [review-report.md](review-report.md) and [e2e-evidence.json](e2e-evidence.json). Documentation and image checks do not replace executed behavioral calibration or constitute unconditional merge approval.
