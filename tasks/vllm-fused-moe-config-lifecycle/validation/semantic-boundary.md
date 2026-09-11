# Review contract

Configured layer construction and changing/absent ambient context -> production modular factory, profile allocation and CUDA Triton forward -> no spurious warning, active-owner workspace behavior and numerical MoE result.

Layer/config lifecycle and production modular kernel are semantic and real. The input layer view carries consistent VllmConfig, FusedMoEConfig and FusedMoEParallelConfig. UnquantizedFusedMoEMethod runs its production constructor under the normal model-init context, which ends before the factory under test. Its real select_gemm_impl selects the production Triton expert. The factory constructs and returns the real FusedMoEModularMethod wrapper. Its constructor, configuration binding and initialization side effects all execute; the fixture then calls the production apply interface. It supplies loaded weights and deterministic router output but never reads the wrapper kernel storage. No factory class or return wrapper is replaced. An input snapshot permits the production in-place output path without corrupting the recorded numerical operands. Weight loading is outside this profile slice. NoEP prepare/finalize supplies local activations; distributed transport is outside this configuration ownership problem. CUDA matmuls, activation and expert reduction run for real. A trusted CPU reference independently computes routed MoE results.

Configured construction/profile, missing ambient lifecycle, conflicting DP+EP/ordinary owners, genuine missing-config diagnostic, and four numerical forwards. Challenge uses fresh 6/96/160/8/3 geometry and DP size 4. Alternative retains the owning VllmConfig and resolves parallel state lazily instead of the Oracle cached boolean.

## Scoring integrity

The separate grading parent owns the current workload and keeps it in memory before candidate imports. Its read-only workload file provides actual matrix operands or continuation records to the unprivileged worker. Numerical references and expected state come from the parent's inputs, not input descriptions returned by the worker. The child still executes the real production paths described above.

The preserved observation-replay negative control executes no target checks and previously received reward 1. It is retained byte-for-byte in `validation/replay-observations.patch`. Current validation must reject it with reward 0, together with both Python early-success exits and attempted direct report writes. Additional scorer regressions replace input descriptions while retaining stale outputs, to distinguish behavioral checking from a freshness marker alone. Those are unit regressions and are reported separately from full Harbor trials.

Process isolation alone is not treated as evidence that target behavior ran; the recorded controls and behavioral assertions define the validated coverage.

## Evidence discipline

Old snapshots and direct Docker diagnostics are not final Harbor results. `e2e-evidence.json` records the actual image identity, executable hashes, raw run locations and final full-path outcomes.

Workspace ownership is measured as the peak logical byte size of tensors returned by the production allocation interface, not the number of workspace_shapes queries. The observation delegates to the real allocator and retains all numerical checks. PyTorch dispatch observes real CUDA temporary tensors/views, excluding storage owned by input operands; it does not name or replace candidate cache classes or allocation helpers. Extra shape queries for diagnostic logging are a correct control and must pass. The recorded extent is the largest logical CUDA temporary/view, not retained allocator-cache capacity, and no shape-query count is required.

The parent independently derives the minimum worst-case workspace bytes from the frozen Standard Triton shapes and the public 16,384-row bound. Ordinary requests must stay below that worst-case reservation. The undersized-profile-workspace control reserves 64 rows, producing correct small-input numerics while violating the profiling requirement; it must fail.

Numerical comparison accounts for FP32 accumulation uncertainty at the final weighted GEMM before each FP16/BF16 store. A float64 reference and the standard gamma_(2K+1) forward-error bound produce representable per-expert intervals, which are summed before comparison. The existing rtol=0.03 and atol=0.5 coefficients remain; this avoids treating cancellation of adjacent BF16 contributions as an implementation error. The preserved failing workload and actual Base-compatible CUDA outputs are replayed without changing their inputs.
