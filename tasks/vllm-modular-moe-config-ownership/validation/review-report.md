modular: retain after recorded repairs. Local skill review completed.

The fixture omitted the production layer.moe_config view while exposing only moe_parallel_config, rejecting valid implementations. The old wrong-legacy-owner control was itself a valid layer-first implementation. The revised Opus implementation additionally has an independent FlashInfer ownership defect.

Construct a real FusedMoEConfig and preserve its alias to the active layer parallel configuration in verifier and independent challenge fixtures. Keep all scoring assertions and workspace/numerical thresholds. Add a correct full-config implementation, preserve the original solver as a consumer-omission negative, reclassify the old layer-first control, and add an explicit stale-owner negative.

Semantic boundary: Active layer config and conflicting ambient/legacy state -> real modular factory, kernel profiling/allocation and FlashInfer/LoRA/functional consumer boundaries -> owner-dependent workspace capacity and real single-rank Triton results. NoEP transport and hardware selector boundaries are replaced; configuration ownership and numerical execution remain production paths.

Behavior coverage: Compatibility construction without global state; current layer vs ambient/legacy conflicts; ownership after construction; FlashInfer, LoRA and functional consumers; 16,384-row DP+EP capacity and ordinary workspace; eight numerical cases. Alternative constructors and full-config storage are accepted; stale owners, omitted consumers, undersized workspace and incomplete execution are rejected.

| Case | Expected | Actual | Harbor errors |
|---|---:|---:|---:|
| alternate-consumer-boundary-ownership | 1 | 1 | 0 |
| alternate-full-config-owner | 1 | 1 | 0 |
| alternate-layer-config-view | 1 | 1 | 0 |
| alternate-workspace-diagnostic | 1 | 1 | 0 |
| base | 0 | 0 | 0 |
| compatibility-global-warning | 0 | 0 | 0 |
| constant-numerical-output | 0 | 0 | 0 |
| early-exit-os-exit | 0 | 0 | 0 |
| early-exit-system-exit | 0 | 0 | 0 |
| forged-report-exit | 0 | 0 | 0 |
| missing-flashinfer-owner | 0 | 0 | 0 |
| oracle | 1 | 1 | 0 |
| replay-observations | 0 | 0 | 0 |
| undersized-profile-workspace | 0 | 0 | 0 |
| wrong-legacy-owner | 0 | 0 | 0 |
| oracle (final frozen) | 1 | 1 | 0 |

9 independent direct-container challenge states reached the expected outcome. These are not counted as Harbor trials.
Original Opus reward remains 0. Task validation uses Base, Oracle and implementation controls; no new Opus session was run.
Full current hashes, image identity, raw job/trial IDs, regression comparisons and portable logs are in e2e-evidence.json.
Earlier unsuccessful patch-preparation attempts, GPU-lock preflight failures and superseded control inventories remain in the external run root and are excluded from the accepted matrix.
Local changes remain uncommitted and unpushed. This report does not represent GitHub CI or external reviewer approval.
