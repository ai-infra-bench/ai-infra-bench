# High-ID routing coverage — 1.3.5

The verifier now has 40 correctness cases. Eight new cases send valid top-k routes across 1023/1024/1025/2049 experts, including repeated routes to the final expert and several distant nonempty intervals. Previous large expert-count inputs only reached IDs 7 through 228. The new native checks compare public outputs and canonicalize valid within-expert permutations; no candidate helper, launch geometry, prefix buffer or unused payload value is prescribed. The separate 2049-expert challenge uses 193 tokens, extending its independently generated routing beyond the original 0–255 range.

Twenty-seven CPU tests validate the output checkers, including acceptance of two different legal row orders and rejection of incorrect high-ID offsets, inverse destinations, forward maps, payloads, ranges and sentinels. GPU validation and immutable identities for this version are recorded in e2e-evidence.json. It reuses the existing CI image built from the current Dockerfile; historical results below retain their original identities.

Ten Harbor grading runs matched their expected rewards under the non-root CI account, with one leased A100-SXM4-40GB, no network, 8 CPUs and 32 GiB RAM per trial. Oracle, the CUDA alternative, the storage-initializing alternative and all three archived Astra patches passed all 40 cases and the original performance gates. Oracle and the CUDA alternative each passed a second complete run. Base passed all 40 correctness cases and failed the original performance ratio; the existing expert-count-cap control failed its intended legal-input rejection. No new hack controls were constructed. The two changed 2049-expert curator correctness cases also passed on Base; a new full curator-challenge run is not claimed. Repository validation and the strict executable-hash audit passed. Raw local logs and concise run identities are referenced by e2e-evidence.json.

# Historical correctness policy update — 1.3.4

The eight expert-count cases now compare only valid payload rows, offsets, inverse/forward mappings and aligned m_indices. Forward sentinels and aligned tail sentinels remain checked. Unused payload storage and unaligned m_indices do not determine reward, consistently with the batch and partition cases. Parent digests cover the same outputs. The total remains 32 correctness cases and performance thresholds are unchanged.

The new `alternative-initialize-unused-storage` control applies after the Oracle, initializes payload storage before copying valid rows, and zeroes unaligned m_indices. It must receive reward 1. The existing CUDA scan alternative remains a separate algorithmic fairness control. The inactive scoring-integrity configuration was removed because this checkout's CI has no corresponding command; runtime scorer integrity checks remain in `tests/test.sh`.

The 1.3.3 runs below are historical and do not validate the changed 1.3.4 verifier.

## Final 1.3.4 validation — 2026-09-16

The final Dockerfile image was built and audited with the source at `/workspace/vllm`. Building exposed and fixed a Dockerfile ARG scope error: BASE_IMAGE now has its pinned default in global scope. The dependency records now describe Alpine Git 2.49.1 and the source-path .pth plus focused CMake installation. The mirror download of the CMake wheel passed the original SHA-256 lock.

All eleven grading runs used the actual `/tests/test.sh` entrypoint on A100 with 8 CPUs, 32 GiB memory and no network. Every outcome matched its expectation. The Oracle, algorithmic CUDA alternative and storage-initializing alternative also passed the independent challenge and two additional full-protocol performance measurements each. Seventeen CPU tests and the repository validator passed. Native early-exit controls reached their intended constructors, returned zero from the worker and still received reward zero because required observations were absent.

| Candidate | Expected reward | Observed reward |
| --- | --- | --- |
| base | 0 | 0 |
| oracle | 1 | 1 |
| alternate-cuda-scaling | 1 | 1 |
| diagnosis-only-linear-scan | 0 | 0 |
| early-native-exit | 0 | 0 |
| early-native-immediate-exit | 0 | 0 |
| root-python-startup | 0 | 0 |
| expert-count-cap | 0 | 0 |
| drop-fp8-sign-bit | 0 | 0 |
| reject-expert-map | 0 | 0 |
| alternative-initialize-unused-storage | 1 | 1 |

The new storage-initializing alternative passes all 32 cases. The original 1.3.3 correctness worker rejects the same staged native artifact on its unaligned m_indices initial-value assertion. This comparison reproduces the old assertion's false rejection; the old-worker probe is not recorded as a separate full-grading reward.

The final Harbor Oracle trial completed with reward 1 and zero errors. Image identity, executable hashes, native artifact hashes, timing repeats, control outcomes, job/trial identifiers and the Harbor input checksum are in [the concise 1.3.4 summary](evidence/tests-1.3.4/summary.json). The Harbor snapshot adds a local Docker GPU reservation adapter and an immutable image override; source, solution and verifier contents match the frozen task. The final executable hash check passed. Documentation and the result summary were written afterward, so they are not part of the pre-run input checksum. Raw logs and archives are kept outside the task directory. No commit, push or registry publication was performed.

## Historical correctness coverage update — 1.3.3

The task now requires 32 correctness cases: the existing 18 batch/mode cases, 8 expert-count boundary cases, and 6 new expert-partition cases. Performance dimensions, input generation, protocol and thresholds are unchanged.

The original correctness cases now generate bytes over the full 0–255 range and explicitly include every encoding in the first row. The three partition fixtures each use seven tokens, top-k two, width 256, seventeen global experts and five noncontiguous, reordered local experts. Mixed, all-local and all-remote routing run in both aligned and unaligned modes; every payload row contains all 256 byte encodings.

These are preservation checks at the native `torch.ops._moe_C.moe_permute` boundary. The Base's public wrapper and EP preprocessing support `expert_map` and fewer local than global experts. The verifier checks local windows, local forward/inverse consistency and payload bytes, skipped inverse destinations, forward sentinels and aligned expert ranges. It permits different ordering within an expert, and does not prescribe unused payload bytes or unaligned `m_indices`. Worker observations are canonicalized; the trusted parent independently derives expected digests from stdlib reference semantics. Deterministic digests alone are not proof of execution.

The six reviewed GPT-6-Astra attempts motivate covering these properties, but their old self-tests are not validation of this new verifier. No confirmed false-positive rollout is asserted. The new fixtures are development cases, not held-out model evaluation evidence.

## Validation performed locally

Seventeen CPU unittest methods pass: seven existing performance-scoring tests and ten new partition-scoring tests. The latter exercise two different valid within-expert orderings, full-byte coverage, corrupted sign bits, incorrect offsets, duplicated local destinations, broken nonlocal inverse mappings, erroneous remote copies, incorrect forward maps/ranges, unconstrained unused storage and complete 32-case registration. These tests validate observation checking, not GPU kernel execution.

The `drop-fp8-sign-bit` and `reject-expert-map` negative patches apply cleanly after the Oracle and are registered in `ci-cases.json` with expected reward zero. The former damages the top bit of one-byte payload copies; the latter rejects supported EP input. Both compiled successfully and returned reward zero through the A100 Docker grading entrypoint on 2026-09-15, failing at their intended behavioral checks.

## A100 Docker validation — 2026-09-15

The current verifier was executed through `bash /tests/test.sh` on a real NVIDIA A100-SXM4-40GB in the isolated, offline `pr72-tests-133` container. Each candidate was rebuilt as the unprivileged agent, staged by root, and checked by the unprivileged workers and trusted scorer. The input-to-native-CUDA-to-observed-output boundary ran for real. The final executable hashes, image identity, native artifact hashes and result summaries are recorded in [evidence/tests-1.3.3-docker/summary.json](evidence/tests-1.3.3-docker/summary.json).

| Candidate | Correctness | Performance | Reward |
| --- | --- | --- | --- |
| Base | 32/32; trusted digests match | Fails: 4096 tokens 661.18 us, ratio about 5.60 | 0 |
| Oracle | 32/32; trusted digests match | Passes: 137.18 us, ratio 2.86 | 1 |
| CUDA alternative | 32/32; trusted digests match | Passes: 127.12 us, ratio 2.78 | 1 |
| Oracle + drop-fp8-sign-bit | Fails byte-exact payload check; 6114/12288 bytes differ by 128 | Skipped after correctness failure | 0 |
| Oracle + reject-expert-map | Fails in the new partition case with `expert maps unsupported` | Skipped after correctness failure | 0 |

No test changes were needed after these GPU runs. The original host-side failure to query NVIDIA was an access limitation: Docker can access the A100 devices. This replaces the earlier statement that GPU verification could not run locally.

## Scope and remaining publication work

This validates the current tests in Docker, not a rebuilt final image or a Harbor trial. The existing image `sha256:6698c86f56f02fa0c16acb4da43776da59e9bf72abd276ce8cb58863d973e900` uses `/app`; this isolated container moved that source tree to `/workspace/vllm`, updated its Python source path, and regenerated build and dependency caches. An initial configure attempt failed because the old dependency cache still referenced `/app`; after replacing that cache, every recorded candidate compiled successfully. No Dockerfile change or image rebuild was performed in this validation.

Runs were sequential on GPU 0, reusing the build cache and applying/reversing only the declared control patches. The recorded outcomes were derived from per-run scoring manifests and stage logs; these raw records are no longer included in the task directory. Stale auxiliary failure-stage files from the shared log directory were excluded from the original results. Full orchestration logs, including the initial cache failure, remain at `/tmp/pr72-tests-133-docker`.

Each candidate received one grading run with the verifier's standard five timing samples per shape. Additional stability trials, the earlier negative-control matrix and final Harbor acceptance on the rebuilt image remain publication work. Historical evidence and the six-rollout rewards remain unchanged; these runs do not replay the six agent artifacts.

## DeepSeek Harbor trial — 2026-09-15

A subsequent Terminus-2 Harbor trial using requested model `openai/deepseek-v4-flash` completed with reward 1, 32/32 correctness cases and zero trial errors. The formal verifier rebuilt the candidate and measured 137.91 us at 4096 tokens and a 4096/512 ratio of 2.4721. Job `pr72-deepseek-v4-flash-20260915-162729` took about 48 minutes and 129 agent episodes. This is the model trial's formal score, separate from the agent's self-test claims. See [evidence/harbor-deepseek-v4-flash-1.3.3/summary.json](evidence/harbor-deepseek-v4-flash-1.3.3/summary.json).

The host-local runtime image migrates the frozen Base to `/workspace/vllm` and adds compatible tmux binaries from an existing Ubuntu 22.04 Harbor image. A local Docker adapter validates an explicit GPU 0 Compose reservation while retaining Harbor's network isolation. Neither the task tests nor solution are baked into this runtime image. This trial does not replace final image rebuild/Oracle publication acceptance. Earlier model-connection and GPU-backend startup failures occurred before this completed trial and are not scored model attempts. Full logs, trajectory and 279 final source artifact files are archived at `/tmp/pr72-harbor-133/pr72-deepseek-v4-flash-completed.zip`.
