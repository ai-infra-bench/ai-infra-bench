# Workspace migration validation

Task v1.2.8 uses `/workspace/vllm` as the repository root and `PYTHONPATH`, with `/workspace/vllm/vllm` as the collected Python package artifact. The instruction, Dockerfile, task metadata, solution entrypoint, verifier import/working directory and challenge instructions were updated together. Task behavior and test assertions are unchanged.

The image was rebuilt from the updated Dockerfile: `ai-infra-bench/vllm-modular-moe-config-ownership:workspace-vllm-1.2.8`, ID `sha256:e794462b0e49f6c58ef94f69d01a09c9f2aa6b8fd71efa1330bb826ba006a712`. The repository image check passed; the agent user imported the checkout from the new path and allocated CUDA tensors on A100 with networking disabled. The old repository path is absent.

Repository validation, path consistency, Python/Shell syntax and diff whitespace checks passed. Six complete Harbor trials exercised artifact collection and the separate verifier at the new paths:

| Case | Expected reward | Actual reward | Harbor errors |
|---|---:|---:|---:|
| base | 0 | 0 | 0 |
| early-exit-system-exit | 0 | 0 | 0 |
| early-exit-os-exit | 0 | 0 | 0 |
| wrong-legacy-owner | 0 | 0 | 0 |
| alternate-consumer-full-pipeline | 1 | 1 | 0 |
| oracle | 1 | 1 | 0 |

Oracle and the correct alternative completed all seven behavioral groups. Both early-exit controls reached their explicit import markers and received reward 0. This validates the path migration; the complete historical control/challenge matrix and three-gate review were not rerun.

The local Harbor runner uses the existing NVIDIA Docker adapter with one explicit A100 UUID and a Compose plugin. Two initial runner setup failures (GPU capability declaration and missing Compose discovery) are preserved separately; neither executed task tests or counts as a behavioral result. The adapter only supplies hardware and selects the Compose execution path.

The previous v1.2.7 evidence is preserved byte-for-byte in `history/before-workspace-migration-20260917.json`. Historical logs and trajectories retain their original paths and results. Current executable hashes, commands, image identity, trial results and raw evidence archive are recorded in `e2e-evidence.json`.

Changes are local and uncommitted. No commit, push or PR update was performed.
