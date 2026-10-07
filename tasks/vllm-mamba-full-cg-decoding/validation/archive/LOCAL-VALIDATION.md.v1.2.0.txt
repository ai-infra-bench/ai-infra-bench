# Local validation

All 21 final Harbor trials matched their expected rewards, with zero errored trials. Base and 14 incorrect controls received 0. The revised Oracle, its repeat, and four correct alternatives received 1. Every successful trial completed all four real-model cases without skips: Mamba1 FULL-CG, Mamba1 eager, Mamba2 FULL-CG, and Mamba2 speculative decoding with accepted draft tokens. Each successful trial checked 28 requests, 224 generated tokens and their complete vocabulary distributions against a private eager reference.

The image is `ai-infra-bench/vllm-mamba-full-cg-decoding:base-737bfa3a43ce-r2`, ID `sha256:6f1c2df7f633dc7dce80cb8e858726fa29fe28b51162ebd2a4b3b7ff33cd550c`. Each trial used one A100-SXM4-40GB, four CPUs, 24 GiB RAM and no network. Four trials ran concurrently on separate GPUs. Correct implementations took 406.7–412.6 seconds through the full Harbor path, including startup, artifact transfer and separate verification; these durations are observations, not scoring thresholds.

The verifier enters through `LLM.generate`, including real scheduling, model layers, recurrent kernels, graph replay and subsequent output collection. A fresh trusted eager reference is built from immutable Base source in the verifier image before candidate code runs. Reference source, results and logs are root-only; submitted code runs as the unprivileged agent. CUDA graph launches are observed after engine initialization, and speculative runs must actually accept draft tokens. Local chunked prefill supplies the prior-state continuation; actual NIXL transport and multi-GPU hybrid accuracy benchmarks are outside these local trials.

The incoming PR Oracle did not pass the new mixed fresh/stateful-request challenge. The revised patch also prevents fresh prompt initialization from replaying a decode-only graph. The historical Oracle is retained as a negative control. Correct controls place the repair in the production builders, runner inputs, or shared splitting logic; another uses a host read during metadata preparation. All pass, so scoring does not require an Oracle helper, repair location, metadata representation or unstated no-sync rule.

| Trial | Expected reward | Observed reward | Harbor seconds |
| --- | --- | --- | --- |
| alternative-agent-implementation | 1 | 1 | 408.5 |
| alternative-host-preparation | 1 | 1 | 412.6 |
| alternative-production-builders | 1 | 1 | 411.1 |
| alternative-runner-inputs | 1 | 1 | 406.7 |
| base | 0 | 0 | 129.5 |
| broken-eager | 0 | 0 | 236.9 |
| broken-spec-decode | 0 | 0 | 399.6 |
| copy-private-reference | 0 | 0 | 90.5 |
| disable-cuda-graphs | 0 | 0 | 130.5 |
| early-exit-os-exit | 0 | 0 | 91.9 |
| early-exit-systemexit | 0 | 0 | 93.5 |
| forged-complete-results | 0 | 0 | 91.9 |
| forged-success-report | 0 | 0 | 92.1 |
| historical-oracle | 0 | 0 | 129.8 |
| incomplete-agent-implementation | 0 | 0 | 130.8 |
| mamba1-only-fix | 0 | 0 | 357.3 |
| metadata-counts-only | 0 | 0 | 129.2 |
| oracle | 1 | 1 | 409.0 |
| oracle-repeat | 1 | 1 | 407.2 |
| zero-mamba2-state-addresses | 0 | 0 | 359.7 |
| zero-state-addresses | 0 | 0 | 130.7 |

Raw job/trial results, verifier logs, generated challenge seeds and image provenance are in `results/harbor-matrix-r4.zip`. `results/matrix-results.json` records each exact job/trial ID, input checksum, output error, graph/draft observation and artifact transfer. Failed controls were inspected for the intended behavior: early exits reached candidate imports, the valid fabricated report failed numeric output comparison, reference copying was denied by permissions, and disabling graphs failed the graph-execution check.

Reproduce an Oracle trial from this task directory with `PYTHONPATH="$PWD/validation" PR64_GPU_UUID=<one-A100-UUID> harbor run -p "$PWD" -a oracle -e local_harbor:LocalGpuDocker -o /tmp/pr64-validation --job-name oracle --yes`. The tested tool versions are Harbor 0.22.0 and Docker Compose 5.5.1. `validation/local_harbor.py` only binds the requested GPU and enforces network none; artifact transfer, separate verifier containers and reward collection remain Harbor's. Controls use the same command after replacing a copied task's solution with the corresponding validation patch; Base uses agent `nop`. The exact matrix launcher and commands are also included in the raw bundle.

Harbor input checksums identify each snapshot before this final evidence write. Only evidence and curator documentation changed afterward; executable file hashes were compared against all 21 snapshots. Historical diagnostics (the reward JSON schema fix, missing test mount, and host load interruption) are not included in the passing matrix. The incoming v1.1.0 evidence remains under `archive/` and is superseded. Fresh model-agent solve rates were not measured, so earlier leaked-environment success rates do not describe this revision.

Validation completed locally before the commit and push to PR #64. The rebuilt image has not been published by this work. The final strict artifact audit is recorded separately in `e2e-evidence.json`; commit and branch delivery are recorded by the PR history.

Coverage limits: candidate Mamba2 ordinary eager execution was not tested as a separate case; running the trusted reference in eager mode does not certify that candidate path. Speculative coverage is Mamba2 with ngram proposals. These trials establish the recorded local behaviors, not all supported model, cache, speculative or distributed-serving combinations.

The subsequent CI build failed while fetching Ubuntu HTTP sources through the runner proxy (502). The Dockerfile now uses HTTPS for archive.ubuntu.com and security.ubuntu.com. On the same pinned donor with the same proxy endpoint, the exact APT phase completed successfully and installed the unchanged pinned versions: git and git-man 1:2.34.1-1ubuntu1.17, liberror-perl 0.17029-1. No retry behavior or signature validation changed. `results/https-apt-check.txt` records this targeted build-step check. The 21-case matrix above belongs to the earlier r2 image; it is not evidence of a complete rebuild of this updated recipe, which remains for CI.
