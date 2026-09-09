# Review contract

Active layer plus conflicting ambient/legacy configuration -> production modular, FlashInfer and LoRA factory consumers and real CUDA profile -> owner-dependent workspace behavior and unchanged numerical output; unowned functional construction stays non-DP+EP.

Factory config resolution, modular construction, profile allocation and CUDA MoE are semantic and real. FlashInfer/CUTLASS expert selectors are replaced by compatible production TritonExperts and NoEP preparation: this tests config flow through their real call sites, not FP8 backend arithmetic. LoRA construction executes the actual injection entrypoint until its modular kernel has been constructed and profiled; later adapter tensor setup is outside ownership. No config keyword, object identity, or storage field is required by scoring.

Compatibility, two conflicting owners, real FlashInfer consumer kernels, LoRA-owned kernels, unowned functional CUTLASS call site, and eight independently checked numerical forwards. Workspace checks compare owner-dependent behavior rather than a fixed private call count. The stale quant-method decoy implements the real config forwarding properties. Alternative stores the active owner and derives DP+EP lazily; Oracle stores a derived flag. Challenge independently varies geometry and legacy/ambient ownership.

## Scoring integrity

The separate grading parent owns the current workload and keeps it in memory before candidate imports. Its read-only workload file provides actual matrix operands or continuation records to the unprivileged worker. Numerical references and expected state come from the parent's inputs, not input descriptions returned by the worker. The child still executes the real production paths described above.

The preserved observation-replay negative control executes no target checks and previously received reward 1. It is retained byte-for-byte in `validation/replay-observations.patch`. Current validation must reject it with reward 0, together with both Python early-success exits and attempted direct report writes. Additional scorer regressions replace input descriptions while retaining stale outputs, to distinguish behavioral checking from a freshness marker alone. Those are unit regressions and are reported separately from full Harbor trials.

Process isolation alone is not treated as evidence that target behavior ran; the recorded controls and behavioral assertions define the validated coverage.

## Evidence discipline

Old snapshots and direct Docker diagnostics are not final Harbor results. `e2e-evidence.json` records the actual image identity, executable hashes, raw run locations and final full-path outcomes.

Warning collection attaches to vllm.config.vllm, whose diagnostics need not propagate to the root logger. A direct missing-config access first proves the handler sees the real diagnostic; its message is cleared before compatibility construction. compatibility-global-warning is an otherwise correct implementation with an unnecessary global read, expected to fail.

Workspace ownership is measured as the peak logical byte size of tensors returned by the production allocation interface, not the number of workspace_shapes queries. The observation delegates to the real allocator and retains all numerical checks. PyTorch dispatch observes real CUDA temporary tensors/views, excluding storage owned by input operands; it does not name or replace candidate cache classes or allocation helpers. Extra shape queries for diagnostic logging are a correct control and must pass. The recorded extent is the largest logical CUDA temporary/view, not retained allocator-cache capacity, and no shape-query count is required.

The parent independently derives the minimum worst-case workspace bytes from the frozen Standard Triton shapes and the public 16,384-row bound. Ordinary requests must stay below that worst-case reservation. The undersized-profile-workspace control reserves 64 rows, producing correct small-input numerics while violating the profiling requirement; it must fail.

Numerical comparison accounts for FP32 accumulation uncertainty at the final weighted GEMM before each FP16/BF16 store. A float64 reference and the standard gamma_(2K+1) forward-error bound produce representable per-expert intervals, which are summed before comparison. The existing rtol=0.03 and atol=0.5 coefficients remain; this avoids treating cancellation of adjacent BF16 contributions as an implementation error. The preserved failing workload and actual Base-compatible CUDA outputs are replayed without changing their inputs.

## Production layer configuration view

The factory and LoRA fixtures expose a real FusedMoEConfig whose
moe_parallel_config is the same owner object as the layer's direct
moe_parallel_config attribute, matching FusedMoE construction. Reading the
full config object is as valid as reading its parallel-config view. The
independent challenge constructs the same production relationship with a
different workload geometry.

alternate-layer-config-view and alternate-full-config-owner exercise this
valid interface. The latter preserves a control formerly mislabeled as
wrong-legacy-owner. The replacement wrong-legacy-owner patch explicitly reads
the stale quant-method owner, while missing-flashinfer-owner preserves the
revised solver's independent consumer omission. Original rewards and the
misclassification evidence remain in the validation history.
