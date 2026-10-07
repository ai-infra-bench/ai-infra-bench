# Local validation

All 27 final Harbor trials matched their expected rewards, with zero errored trials. Base and 20 incorrect controls received 0. The revised Oracle, its repeat, and four correct alternatives received 1. Every successful trial completed all seven real-model cases without skips: Mamba1 FULL-CG/eager with padding lifecycle, Mamba2 ordinary FULL-CG/eager, hybrid Mamba2 speculative FULL-CG/eager, and hybrid all-cache speculative decoding. Each successful trial checked 832 generated tokens and their complete vocabulary distributions against a private eager reference.

The image is `ai-infra-bench/vllm-mamba-full-cg-decoding:base-737bfa3a43ce-r3`, ID `sha256:a3f919b1b68a25af5b1947dd8e089d90b3503992f14c50ae98351bf885bfcfa4`. Each trial used one A100-SXM4-40GB, four CPUs, 24 GiB RAM and no network. Four trials ran concurrently on separate GPUs. Correct implementations took 482.8–494.3 seconds through the full Harbor path, including startup, artifact transfer and separate verification; these durations are observations, not scoring thresholds.

The verifier enters through `LLM.generate`, including real scheduling, model layers, recurrent kernels, graph replay and subsequent output collection. A fresh trusted eager reference is built from immutable Base source in the verifier image before candidate code runs. Reference source, results and logs are root-only; submitted code runs as the unprivileged agent. A separate non-dumpable observer uses hardware breakpoints on the root-owned CUDA driver and checks successful graph-call returns after engine initialization. Candidate Python cannot change the observer statistics or open its report pipe. Speculative metrics remain workload observations; numeric outputs are compared against non-speculative eager serving. Local chunked prefill supplies the prior-state continuation; actual NIXL transport and multi-GPU hybrid accuracy benchmarks are outside these local trials.

The incoming PR Oracle did not pass the new mixed fresh/stateful-request challenge. The revised patch also prevents fresh prompt initialization from replaying a decode-only graph. The historical Oracle and the previous v1.2 reference patch are retained as negative controls. This revision additionally excludes padding rows from prefill work, avoids decode graphs for multi-token prompt chunks, and retains Mamba2 accepted-state offsets on zero-draft steps. Correct controls place the repair in the production builders, runner inputs, or shared splitting logic; another uses a host read during metadata preparation. All pass, so scoring does not require an Oracle helper, repair location, metadata representation or unstated no-sync rule.

| Trial | Expected reward | Observed reward | Harbor seconds |
| --- | --- | --- | --- |
| alternative-agent-implementation | 1 | 1 | 492.6 |
| alternative-host-preparation | 1 | 1 | 493.1 |
| alternative-production-builders | 1 | 1 | 494.3 |
| alternative-runner-inputs | 1 | 1 | 492.1 |
| base | 0 | 0 | 129.2 |
| broken-eager | 0 | 0 | 146.2 |
| broken-spec-decode | 0 | 0 | 417.9 |
| copy-private-reference | 0 | 0 | 88.8 |
| disable-cuda-graphs | 0 | 0 | 128.2 |
| early-exit-os-exit | 0 | 0 | 90.5 |
| early-exit-systemexit | 0 | 0 | 90.4 |
| forged-complete-results | 0 | 0 | 92.4 |
| forged-graph-observation | 0 | 0 | 126.3 |
| forged-success-report | 0 | 0 | 90.9 |
| historical-oracle | 0 | 0 | 128.3 |
| incomplete-agent-implementation | 0 | 0 | 128.3 |
| invalid-driver-graph-launch | 0 | 0 | 124.7 |
| mamba1-only-fix | 0 | 0 | 328.5 |
| metadata-counts-only | 0 | 0 | 128.5 |
| missing-multitoken-prefill-guard | 0 | 0 | 422.5 |
| missing-padding-cleanup | 0 | 0 | 127.4 |
| missing-zero-draft-offset | 0 | 0 | 426.3 |
| oracle | 1 | 1 | 493.9 |
| oracle-repeat | 1 | 1 | 482.8 |
| previous-oracle | 0 | 0 | 129.2 |
| zero-mamba2-state-addresses | 0 | 0 | 330.9 |
| zero-state-addresses | 0 | 0 | 128.1 |

Raw job/trial results, verifier logs, generated challenge seeds and image provenance are in `results/harbor-matrix-r6.zip`. `results/matrix-results.json` records each exact job/trial ID, input checksum, output error, graph/draft observation and artifact transfer. Failed controls were inspected for the intended behavior: early exits reached candidate imports, the valid fabricated report executed a harmless CUDA graph but failed numeric output comparison, reference copying was denied, forcing eager with a forged profiler failed independent graph observation, and invalid graph calls did not count as successful launches.

Reproduce an Oracle trial from this task directory with `PYTHONPATH="$PWD/validation" PR64_GPU_UUID=<one-A100-UUID> harbor run -p "$PWD" -a oracle -e local_harbor:LocalGpuDocker -o /tmp/pr64-validation --job-name oracle --yes`. The tested tool versions are Harbor 0.22.0 and Docker Compose 5.5.1. `validation/local_harbor.py` binds one GPU, enforces network none, and mirrors each phase's source/cache to the data disk with image-equivalent ownership; artifact transfer, separate verifier containers and reward collection remain Harbor's. Controls use the same command after replacing a copied task's solution with the corresponding validation patch; Base uses agent `nop`. The exact matrix launcher and commands are also included in the raw bundle.

Harbor input checksums identify each snapshot before this final evidence write. Only evidence and curator documentation changed afterward; executable file hashes were compared against all 27 snapshots. Historical diagnostics (the reward JSON schema fix, missing test mount, and host load interruption) are not included in the passing matrix. Earlier v1.1/v1.2 records remain under `archive/` and are superseded. R5 is diagnostic only: a storage-adapter permission error prevented patches from being applied; r6 restores image agent ownership and verifies transferred patches. Fresh model-agent solve rates were not measured, so earlier leaked-environment success rates do not describe this revision.

Validation completed locally before committing and pushing this revision. The local image has not been published by this work. The final strict artifact audit is recorded in `e2e-evidence.json`; delivery commits are recorded by PR #64 history.
