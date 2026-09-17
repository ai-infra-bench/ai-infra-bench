# 1.2.8 Oracle validated; model campaign in progress

The 1.2.8 repaired Oracle passes the actual Harbor verifier with reward 1 and a minimum speedup of 2.320× across all five required shapes (threshold 1.5×). The 20-case grading matrix produces every expected result. Final campaign acceptance is pending the remaining model attempts and a fresh four-attempt round.

The 1.2.6 Oracle and one completed Flash candidate accepted by its verifier mishandle legal contiguous views with nonzero storage offsets. Contiguity does not imply that the data pointer is vector-aligned. Version 1.2.7 checks input/output pointer alignment before entering the vectorized Oracle path and adds FP16/BF16/FP32 offset-input cases to both public and native checks. Version 1.2.7 left the instruction, image, performance protocol, and threshold unchanged. Version 1.2.8 clarifies only that rebuilding the existing `_C` target is sufficient and states the existing container limits/build defaults. All grader, solution, environment and control files remain byte-identical to validated 1.2.7; the fresh 1.2.8 Harbor Oracle run passes, with all prepared and canonical inputs unchanged.

Validation on the immutable A100 image:

- Actual Harbor 0.22.0 Oracle run on 1.2.8: reward 1, no exception; speedups 2.320, 2.340, 2.668, 2.339, 2.703×. All prepared inputs remained unchanged.
- Direct production-entrypoint matrix on identical 1.2.7 runtime inputs: 20/20 expected outcomes, including Base, Oracle, alternate implementation, legitimate aliases/refactors, and incomplete/adversarial controls. This matrix is not represented as 20 Harbor trials.
- Independent Oracle and alternate implementation probes: each passes 54 INT8, 24 native FP8, and 18 offset-input checks. These are development probes, separate from scored cases.
- Exact full-repository replays of two completed Flash candidates: original rewards 1 and 0 remain preserved; both receive 0 with 1.2.7. Offset views independently fail in both. Frozen-reference comparison also confirms oversized-group failures in the original zero-reward candidate.

See [machine-readable evidence](e2e-evidence.json) and the checksum-manifested archives under [evidence/1.2.7](evidence/1.2.7) and [evidence/1.2.8](evidence/1.2.8). Full native binaries and replay snapshots remain on A100. Round one retains frozen 1.2.6 inputs; its two other model attempts are still running. No final pass-rate or complete-task acceptance claim is made here.
