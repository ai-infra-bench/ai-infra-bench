# Review contract

3-D CUDA operands and optional output -> actual batch-aware Triton execution -> bitwise batch/single equality, numeric result, errors, launch count and paired latency.

A100 execution, tensor dtype/shape/strides, reduction order, launch scaling and timings are semantic. Input values may vary. The comparison kernel is the exact Base matrix implementation retained in tests/legacy_bmm.py, rather than a candidate-editable baseline. No CUDA component is simulated.

Eight dtype/shape cases; seven invalid-input cases and 32 output-copy cases (dtype conversion, CPU destination, and broadcast-compatible destination); launches at batches 1/7/29; three prescribed shapes with five warmups, twenty iterations and five timing rounds. Independent challenge adds empty and singleton dimensions, noncontiguous inputs/output and new geometry. Base is already batch-invariant: its target failure is launch scaling/performance, not loss of determinism.

## Scoring integrity

The separate grading parent owns the current workload and keeps it in memory before candidate imports. Its read-only workload file provides actual matrix operands or continuation records to the unprivileged worker. Numerical references and expected state come from the parent's inputs, not input descriptions returned by the worker. The child still executes the real production paths described above. BMM launch and latency gates are unchanged.

The preserved observation-replay negative control executes no target checks and previously received reward 1. It is retained byte-for-byte in `validation/replay-observations.patch`. Current validation must reject it with reward 0, together with both Python early-success exits and attempted direct report writes. Additional scorer regressions replace input descriptions while retaining stale outputs, to distinguish behavioral checking from a freshness marker alone. Those are unit regressions and are reported separately from full Harbor trials.

Process isolation alone is not treated as evidence that target behavior ran; the recorded controls and behavioral assertions define the validated coverage.

## Evidence discipline

Old snapshots and direct Docker diagnostics are not final Harbor results. `e2e-evidence.json` records the actual image identity, executable hashes, raw run locations and final full-path outcomes.

The `out=` contract checks tensor object identity as well as storage and values. The `out-view-return` control keeps correct values and storage but returns a distinct view; it must receive reward 0.

Output-copy compatibility follows the frozen baseline. The old strict Oracle is retained as the incorrect strict-out-rejection control. The archived solver implementation is a correct alternative, evaluated afresh under this contract. Performance thresholds are unchanged.

Long FP32 reductions at K=1536 and K=2560 use parent-owned operands and a CPU float64 reference cast to FP32. Determinism never replaces the numerical tolerance. The performance cases still use BF16 with the original three speedup gates. The independent challenge adds K=2048/3072. Batch=0 is not asserted as supported: the frozen Base rejects torch.stack([]). The prior TF32 Oracle is retained as the long-k-tf32-loss negative control.
