> v1.2.10 FlashAttention import and offline Ruff follow-up: see `flashattn-ruff.md` and current `e2e-evidence.json`. Earlier results below retain their original revision.

# Test tooling and stage reporting validation

Task v1.2.9 can be retained. This follow-up adds reproducible pytest tooling and preserves partial trusted grading progress; the instruction, ownership contract, numerical tolerances, workload generators, Oracle and reward requirement are unchanged. Changes remain local and uncommitted.

The semantic boundary remains: current layer plus conflicting configuration → real factories and backend configuration resolution → correct profiling capacity, communication payloads, expert parameters and local result. Existing single-device CUDA substitutions remain as documented in semantic-boundary.md.

The image adds pytest 8.3.5, pluggy 1.5.0, iniconfig 2.0.0 and tblib 3.1.0 using exact wheel hashes and --no-deps. tblib is needed by upstream tests/conftest.py. The pinned base still supplies packaging 25.0 and torch 2.9.0+cu129. General test infrastructure is cutoff-exempt and pinned; semantic dependencies are unchanged.

Final image: `ai-infra-bench/vllm-modular-moe-config-ownership:test-tooling-1.2.9`, ID `sha256:a7c730319d4bb54e50119c23376906632ce2339179addcb89660d16a396353b4`. Repository image checks passed. As agent, with networking disabled and one A100, pytest collected 402 cases from test_modular_kernel_combinations.py and test_cutlass_moe.py. This is collection evidence, not a claim that 402 tests passed. CUDA/import checks also passed.

The trusted checker now yields each stage only after its assertions complete. The parent retains stages_passed, reports failed_stage and stages_not_run, and grants reward 1 only after all seven expected stages complete. It still stops at the first failure. Missing worker observations or worker failure do not mark any trusted parent stage as passed. The report schema remains v1 with additive fields.

Three reporting unit tests cover complete success, all seven failure positions, and missing observations. Nine actual Harbor trials then exercised artifact collection, separate verification and final reward:

| Case | Expected / actual reward | Trusted stages passed | Failed stage |
|---|---|---:|---|
| base | 0 / 0.0 | 0 | worker observation failure |
| early-exit-system-exit | 0 / 0.0 | 0 | worker observation failure |
| early-exit-os-exit | 0 / 0.0 | 0 | worker observation failure |
| alternate-consumer-full-pipeline | 1 / 1.0 | 7 | none |
| rollout-r1 | 0 / 0.0 | 6 | flashinfer_prepare_expert_finalize |
| rollout-r2 | 0 / 0.0 | 6 | flashinfer_prepare_expert_finalize |
| rollout-r3 | 1 / 1.0 | 7 | none |
| wrong-legacy-owner | 0 / 0.0 | 0 | worker observation failure |
| oracle | 1 / 1.0 | 7 | none |

All nine Harbor jobs completed without harness exceptions and with expected rewards. Both early-exit controls reached their import markers; neither received credit. r1/r2 now retain six passed groups and identify only the final FlashInfer lifecycle failure, while their original reward remains 0. r3, the distinct alternative and the final Oracle complete all seven groups. Base still fails for the target unwanted global-config access, not a pytest/setup failure.

Executable inputs were frozen before runs and rehashed afterward with no changes. Each prepared case has an independent hash inventory; final Harbor task checksums refer to those snapshots before evidence documentation was written. Existing v1.2.8 evidence is preserved byte-for-byte in history/before-test-tooling-reporting-20260917.json. Current identities, commands, reports, scores, input hashes and raw archive are indexed in e2e-evidence.json.

No fresh model rollout, commit, push or PR update was performed. This is a scoped regression validation, not a repeat of every historical qualification challenge.
