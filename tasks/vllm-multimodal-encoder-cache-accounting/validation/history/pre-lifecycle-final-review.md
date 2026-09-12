PR8 can be retained after the producer/consumer fixture repair. Local task-review skill check passed at the declared semantic boundary.

Gate 1: The original public embedding-row accounting, full-item encoding budget, prompt-space mapping and representation freedom are unchanged.

Gate 2: The same frozen CPU image contains the exact Base and normal dependencies. Fresh image/user/import/history/isolation and patch checks pass. Encoder inference and media grouping supply valid tensors; all cache-layout and accounting transitions execute production code. No task-specific helpers were added to the image.

Gate 3: The verifier and independent challenge no longer inject compact caches. They execute real _execute_mm_encoder writes and real _gather_mm_embeddings reads. Sparse partial windows (15) and mixed sparse/dense/all-false multi-item windows (136) check values, masks and order, including gaps. Parent completeness checks retain all seven required stages and compare the updated observation shape. The interpreter/scoring wrapper and Oracle are unchanged.

The same complete correct dense-cache candidate scored 0 under the old fixture (two mapping failures) and 1 under the repaired fixture in full Harbor. The compact Oracle and independent mask-count implementation also pass. Reversing encoder output rows fails through mapping behavior. Accounting, profiler and budget requirements remain enforced.

The latest Opus edits were reconstructed from successful tool calls and replayed through full Harbor, using unchanged repaired scoring inputs. Both mapping groups now pass; registry_capacity and scheduler_partial_budget still fail. The historical original reward remains 0. This is a preserved candidate replay, not a new paid solver session or a byte-verified final source export.

| Case | Expected | Actual | Harbor errors |
|---|---:|---:|---:|
| alternate-dense-cache | 1 | 1.0 | 0 |
| alternate-direct-mask-count | 1 | 1.0 | 0 |
| base | 0 | 0.0 | 0 |
| early-os-exit | 0 | 0.0 | 0 |
| early-system-exit | 0 | 0.0 | 0 |
| oracle | 1 | 1.0 | 0 |
| partial-budget-omission | 0 | 0.0 | 0 |
| root-python-startup | 0 | 0.0 | 0 |
| wrong-encoder-cache-order | 0 | 0.0 | 0 |
| oracle (final frozen) | 1 | 1.0 | 0 |

Ten final-version Harbor validation runs passed their expected outcomes. Two additional old/new-fixture and solver-replay diagnostic Harbor runs are recorded separately; all have zero Harbor errors. Six final-version independent direct-container challenge states matched expectations. Earlier preflight runs remain outside the accepted matrix.

Current executable hashes, frozen image identity, exact job/trial IDs and portable raw logs are in e2e-evidence.json. The task remains locally modified and unsubmitted. No external reviewer/CI approval is claimed. Historical local-regressions.json and earlier validation records are preserved, not counted as current runs.
