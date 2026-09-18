# Task 1.2.8 accepted after iterative rollout review

The repaired task and verifier can be retained. Two rounds of four concurrent Harbor/Flash attempts are complete; all eight full saved-state replays and trajectory reviews are complete. One original false positive was identified and repaired. The second round exposes no further scoring defect within the reviewed scope.

| Round | Task version | Original rewards, GPU4/5/6/7 | Full saved-state replay |
|---|---|---|---|
| R01 | 1.2.6 | 0 / 1 / 1 / 0 | 0 / 0 / 1 / 0 on repaired 1.2.7 |
| R02 | 1.2.8 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 on unchanged 1.2.8 |

R01's unscored Docker-network startup failure is preserved separately; its replacement supplies the fourth actual model attempt. Every scored model trial finishes without a Harbor exception. R02 zeros are supported by independently reproduced oversized-group and contiguous-offset failures, with irregular-group behavior differing across candidates. No formal performance result is claimed for candidates that fail correctness first.

Changes made during this work:

- **1.2.6:** repair Oracle shared-memory budgeting, add a CUDA fallback for one oversized group and irregular vector alignment, strengthen valid resource/alignment cases, and test fallback capability before candidate import so legitimate aliases and cached dispatch are accepted. Add hash-pinned pytest tools to the rebuilt image.
- **1.2.7:** repair Oracle pointer alignment for legal contiguous views with storage offsets; add FP16/BF16/FP32 offset cases through both public and native entrypoints. This rejects R01 GPU5's previously accepted but incorrect answer. A different complete Flash answer still passes.
- **1.2.8:** clarify that rebuilding `_C` with the existing project build system is sufficient and state the existing eight-CPU/32-GiB build limits. No executable grader, Oracle, control, image, performance protocol or threshold changes from 1.2.7.
- **Evidence tooling:** capture complete repositories before grading, retain original scores separately from exact saved-state replay, compare isolated outputs with a frozen reference, and audit ignored/generated files and bytecode. These changes do not introduce new solution-specific scoring requirements.

No valid-input case was removed to improve pass rates. Rank-one inputs and stricter MoE integration tolerances were considered and excluded because they exceed the explicit task contract. Second-round evidence did not justify another executable change or another model round.

Validation on the immutable A100 image:

- Actual Harbor 0.22.0 Oracle at 1.2.8: reward 1, no exception; all seven stages complete. Speedups **2.320, 2.340, 2.668, 2.339, 2.703×**, each above 1.5×.
- Direct production-entrypoint matrix on byte-identical 1.2.7 runtime: **20/20 expected outcomes**, including Base, Oracle, a distinct alternative, legitimate refactors and incomplete/adversarial controls. These are not 20 Harbor trials.
- Independent Oracle and alternative probes: each passes **54 INT8, 24 native FP8 and 18 offset checks**. R02 candidates that modify shared FP8 code each pass a separate 24-case native FP8 probe.
- All model canonical/prepared inputs and all replay inputs remain unchanged. All final recorded trajectories and complete repository snapshots were reviewed; native code is rebuilt by the verifier.

Detailed attribution, timings, file counts and integrity limits are in [R01 review](rollout-review-r01.md), [R02 review](rollout-review-r02.md), and [machine-readable evidence](e2e-evidence.json). Original model rewards and revised replays remain distinct. Evidence archives have SHA manifests; full binary/repository archives remain on the authorized A100.

Limits: these are development rounds, not held-out capability estimates; the gateway supplies no immutable model revision; actual ROCm hardware was not exercised; upstream Triton FP8 tests cannot compile on sm80; full root-filesystem capture and exhaustive native-code isolation are not claimed. The independent native FP8 checks are recorded separately from those unsupported upstream tests.
