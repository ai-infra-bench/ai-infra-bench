Task v1.2.10 can be retained. The two rollout-visible development problems are fixed: the checkout now contains the real FlashAttention Python package from the existing digest-pinned v0.12.0 image, and Ruff 0.14.0 is available offline. Instruction, Oracle, behavioral assertions, workloads and numerical tolerances are unchanged. No fresh model rollout, commit or push was performed.

Gate 1 is unchanged: current layer plus conflicting ambient/legacy configuration → real factories and backend configuration resolution → correct profiling capacity, communication payloads, expert arguments and local result. Gate 2 now restores normal import/tool paths without preinstalling task-specific fixtures. Gate 3 retains the seven trusted behavior groups, the documented single-device CUDA substitutions and original reward requirement.

The Base CMake external-project rules install the FlashAttention Python package next to native modules. The former image copied only native .so files, leaving the checkout package without __init__.py or its interface. The new build verifies and installs seven existing base-image Python files listed in environment/lock/flash-attn-python.sha256. No Python is copied from the newer native donor, no new semantic dependency version is introduced, and all seven donor native binaries remain unchanged. Ruff matches the Base pre-commit pin (0.14.0); its x86_64 wheel is SHA-256 locked and installed with --no-deps --require-hashes. General test tooling is cutoff-exempt.

Final image: `ai-infra-bench/vllm-modular-moe-config-ownership:flashattn-ruff-1.2.10`, ID `sha256:e4d6a3b7dc9bbd19ddc0586b0f9d75b715895386e11f16369c73c80884a66d69`. Full Dockerfile build, image inspection/history and repository image checks passed. The build uses an exact Base-only loopback Git source; no tests, solution or evidence enter image layers. Build logs and image metadata are archived.

Under user agent, network none, one A100, 8 CPU and 32 GB memory: direct FlashAttention imports resolve inside /workspace/vllm; real FA2 CUDA results for unequal sequence lengths match an independent Torch reference. Offline Ruff accepts valid input, reports F821 for an undefined name, and runs formatting checks. The exact tool/runtime versions are in agent-smoke.log.

Direct pytest collection succeeds for 3909 cases across test_moe.py, test_modular_kernel_combinations.py and test_cutlass_moe.py (collection only, not 3909 executed tests). Five unmodified test_moe.py GPU numerical cases pass without temporary import setup or path monkeypatching: single-token and 33-token cases plus 32768/40000-token chunked cases. Collection counts and actual executed-case counts are separate in e2e-evidence.json and raw logs.

| Case | Expected / actual reward | Trusted stages | Failed stage |
|---|---|---:|---|
| base | 0 / 0.0 | 0/7 | worker observation failure |
| early-exit-system-exit | 0 / 0.0 | 0/7 | worker observation failure |
| early-exit-os-exit | 0 / 0.0 | 0/7 | worker observation failure |
| alternate-consumer-full-pipeline | 1 / 1.0 | 7/7 | none |
| rollout-r1 | 1 / 1.0 | 7/7 | none |
| rollout-r2 | 0 / 0.0 | 6/7 | flashinfer_prepare_expert_finalize |
| rollout-r3 | 1 / 1.0 | 7/7 | none |
| wrong-legacy-owner | 0 / 0.0 | 0/7 | worker observation failure |
| oracle | 1 / 1.0 | 7/7 | none |

rollout-r1/r2/r3 refer to the saved Codex gpt-6-astra campaign codex-gpt-6-astra-20260917-200534, not the earlier DeepSeek attempts. Complete tracked patches and untracked test archives were restored. Original rewards are preserved; the new-image replays remain 1/0/1. r2 still fails its stale-owner FlashInfer lifecycle, demonstrating that this tooling repair does not mask its implementation defect. Base, both early-success-exit controls and wrong-legacy-owner receive 0; the distinct alternative and final Oracle receive 1. All nine actual Harbor trials complete with zero harness errors and expected rewards.

Inputs were frozen before execution and checked afterward with no changes. Final acceptance ends with an actual Harbor Oracle trial. Prior v1.2.9 evidence is preserved byte-for-byte in history/before-flashattn-ruff-20260917.json; new input hashes, commands, case IDs, reports and raw archive identity are in e2e-evidence.json. Documentation written afterward is not falsely presented as part of the original Harbor checksum.

Limits: these checks do not claim every upstream test executes, FA3/FA4 works on A100, or real distributed NCCL/full FlashInfer FP8 arithmetic was exercised. This follow-up does not repeat the historical complete challenge matrix; the unchanged behavioral verifier and controls retain that separately identified evidence.

Final repository checks: strict artifact/evidence audit passed all four checks with 0 errors and 0 warnings; git diff --check passed. Instruction, verifier and Oracle files match their pre-change hashes (12 files).
