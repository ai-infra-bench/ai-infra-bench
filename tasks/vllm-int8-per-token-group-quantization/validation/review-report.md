# PR70 task hardening — 1.2.6

The task can be retained after this repair. The three reviewed findings are closed; an independently discovered legal nonaligned-group failure is also fixed. The task statement, Base, cutoff, GPU resources and 1.5x threshold are unchanged.

- Oracle: halve groups per block until dynamic shared memory fits the current device's default limit. A scalar streaming CUDA kernel handles a group larger than that limit and groups that do not meet the vector path's alignment. The five 64/128-group performance shapes retain the fast path.
- Verifier: configure the stable platform capability in a fresh process before candidate import. Renamed imports and import-time cached dispatch pass; removing fallback fails. Eighteen precision/empty/resource/alignment cases run through native and public APIs against frozen Triton, alongside the existing configured-range checks.
- Environment: add hash-pinned pytest 8.4.1, pytest-asyncio 1.1.0 and dependencies. The complete recipe was rebuilt, image/Git isolation checks passed, and an offline agent ran two original INT8 tests. The 24 upstream FP8 cases collect successfully.

Gate 1 passes for the frozen public quantization contract. Gate 2 passes for the real source/runtime/compiler path and normal development tools. Gate 3 passes for the exercised semantic boundary: all 19 direct grading cases matched expectations; Oracle and the distinct native alternative each passed 54 independent INT8 and 24 FP8 checks; all five Harbor trials matched expectations with zero errored trials.

| Case | Expected | Observed | Behavioral result |
|---|---:|---:|---|
| base | 0 | 0 | native_operator_missing |
| oracle | 1 | 1 | PASS |
| alternate-native-kernel | 1 | 1 | PASS |
| wrong-public-operator-name | 0 | 0 | native_operator_missing |
| reciprocal-overflow | 0 | 0 | precision_boundary_mismatch |
| positive-lower-bound-rejected | 0 | 0 | worker_exit_nonzero |
| range-must-include-zero | 0 | 0 | worker_exit_nonzero |
| slow-candidate-occupancy | 0 | 0 | performance_below_threshold |
| compatible-operator-alias | 1 | 1 | PASS |
| renamed-private-triton-helper | 1 | 1 | PASS |
| empty-batch-launch | 0 | 0 | worker_exit_nonzero |
| large-group-shared-memory | 0 | 0 | worker_exit_nonzero |
| unaligned-group-native | 0 | 0 | worker_exit_nonzero |
| early-system-exit | 0 | 0 | worker_payload_frame_count |
| early-os-exit | 0 | 0 | worker_payload_frame_count |
| early-native-timing-exit | 0 | 0 | performance_check_failed |
| renamed-platform-import | 1 | 1 | PASS |
| cached-platform-dispatch | 1 | 1 | PASS |
| native-without-fallback | 0 | 0 | worker_exit_nonzero |

Final Harbor Oracle minimum speedup: **2.334x**. The earlier final-image direct Oracle minimum was **2.294x**. Each listed workload passed independently.

| Shape | Group | Native ms | Frozen Triton ms | Speedup |
|---|---:|---:|---:|---:|
| 1024 × 4096 | 128 | 0.017864 | 0.050171 | 2.809x |
| 4096 × 4096 | 128 | 0.055557 | 0.130099 | 2.342x |
| 2048 × 4096 | 64 | 0.048438 | 0.1293 | 2.669x |
| 16 × 256 × 4096 | 128 | 0.055744 | 0.130086 | 2.334x |
| 4096 × 4096 | 64 | 0.094477 | 0.25481 | 2.697x |

Image: `sha256:5dc453932b016a3b73fb9316cce43f251275197b7a6295bc970e3de7a2718593` (`codex-pr70:test-tools-126`). Final trial: `f945f330-9b4c-46bb-aad0-53698814edff`. Final task checksum: `ac9d08b7fc7c5545b33e3bf733ccd3d4449d429ce25336a9bb856c3d306aa1f7`.

The direct matrix uses the unchanged grading entrypoint with a Base reset for every case. Ccache is reused; native libraries and build directories are not injected. Harbor uses fresh final-image containers, with cache entries added only after agent completion. Every candidate still runs the project-owned build backend. All builds passed; negative results came from behavior. This is not a claim of cold builds.

The SystemExit and os._exit controls emitted their execution markers and were rejected for missing completion framing. The native timing control completed correctness, wrote its isolated timing-process marker, then exited before a timing record; Harbor still collected reward 0. These observations do not certify isolation from arbitrary native process compromise.

The first matrix exposed a regression-coverage gap: single-block shapes accepted the alignment-broken intermediate Oracle. Formal inputs were strengthened to multi-block shapes (2,3,33)/group 33 for FP16/BF16 and (2,3,17)/group 17 for FP32. The old run is archived as superseded; all 19 grading cases and five Harbor trials above use the strengthened frozen inputs.

Limitations: fallback is tested by capability simulation plus real CUDA Triton, not actual ROCm. The original FP8 Triton-reference test cannot run on sm80, including on Base; the separate real-native/PyTorch FP8 checks passed all 24 configurations. No fresh model rollout was performed or historical rollout completeness certified.

Final executable hashes, source/native identities, cache provenance and actual run records are in [e2e-evidence.json](e2e-evidence.json). [Raw logs and inputs](evidence/1.2.6/raw-runs.tar.gz) are preserved with a hash manifest. Historical 1.2.5 evidence and reports remain under history/. Only evidence and remediation documentation changed after the frozen execution snapshot.

Worktree: `/Users/yaoyaoyao/Documents/Codex/2026-09-17/qing-2/work/pr70-review`; HEAD `ee739ca0e3bb421f20ea6994beaefe9eecb44ded`; branch `pr70-review`. Changes are uncommitted. No push or GitHub comment was made.

Final strict artifact audit: 4 checks, 0 errors, 0 warnings. See [audit log](evidence/1.2.6/final-audit.log).
