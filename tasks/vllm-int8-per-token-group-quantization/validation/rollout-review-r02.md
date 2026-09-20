# Task 1.2.8 accepted after two Flash rounds

Retain the repaired task and verifier. Round two yields **0/0/0/0**, and all four complete saved-repository replays agree. Independent valid-input probes establish candidate defects behind every zero. No new wrong reward or invalid scored assertion was found in this round, so no further scoring change or model round is justified. This is acceptance within the documented review scope, not proof that every possible input or bypass has been exhausted.

Round one originally yielded **0/1/1/0**. The added contiguous-offset coverage in 1.2.7 changes its full-replay result to **0/0/1/0**, closing one demonstrated false positive. The remaining passing Flash candidate, a distinct alternative solution, and the fresh actual Harbor Oracle acceptance provide full-solution evidence. The 1.2.8 Oracle minimum is **2.320×**, above the unchanged 1.5× requirement. [Round-one review](rollout-review-r01.md) preserves those original observations separately.

## Experiment and evidence

Four Flash attempts started concurrently on A100 GPUs4/5/6/7 using frozen task 1.2.8 at `08c99c4e3f8e5120ed0ebbffd689e2be366bf5f0`. Model `deepseek-v4-flash[1m]` was selected from the user's configured A100 `env.sh`. The gateway reports no immutable model revision; all four raw sessions record effective `high` effort, without a launcher override. Harbor 0.22.0 and Claude Code 2.1.238 ran with one A100-SXM4-40GB, eight CPUs and 32 GiB per attempt, with gateway-only egress. Explicit nonoverlapping subnets avoided the address-pool startup problem observed in R01. No startup or Harbor exception occurred in R02.

Image: `sha256:5dc453932b016a3b73fb9316cce43f251275197b7a6295bc970e3de7a2718593`. vLLM Base: `14bf19e39f601163265b7c7d58d972b8a83d8896`. All canonical and per-trial prepared inputs match their pre-run hashes. Each saved-state replay verifies the captured archive, restores the entire repository including `.git`, untracked and ignored files, invokes root `bash /tests/test.sh`, rebuilds the native extension, and confirms frozen inputs remain unchanged. Candidate binaries are not substituted for the verifier's rebuild.

The rollout-review skill SHA256 is `767fe719670c4a10753d7643cddbbab9c73f111c025f2d09fe03a6cf72a22f1f`. The [evidence manifest](evidence/rollout-r02/manifest.json) binds the final original package, four replay packages, generated-file audits, FP8 probes, metrics and review coverage. All 166 original-package file hashes and 35 files in each replay package were verified. Large full-repository archives and native libraries remain under `/data/codex-pr70-rollouts-20260918` on the authorized A100, with SHA identities in the evidence. Package manifests distinguish original and redacted hashes. The snapshot covers the repository, not the whole root filesystem.

## Results and attribution

| Trial | Original | Full replay | Independent finding |
|---|---:|---:|---|
| `flash-r02-gpu4__AeVyun5` | 0 | 0 | Oversized single groups, pointer offsets and irregular groups fail |
| `flash-r02-gpu5__5dazumT` | 0 | 0 | Oversized single groups and pointer offsets fail; irregular groups pass |
| `flash-r02-gpu6__qWJQGEE` | 0 | 0 | Oversized single groups and pointer offsets fail; irregular groups pass |
| `flash-r02-gpu7__L54rXMy` | 0 | 0 | Oversized single groups, pointer offsets and irregular groups fail |

All four original trials pass operator-surface/public-dispatch checks, four ordinary cases and two configurable-argument cases, then fail during boundary evaluation before formal performance. GPU4's explicit launch check identifies `single-large-fp32`; other asynchronous launch errors surface at a later tensor allocation. Those allocation locations are not assumed to identify the first fault: each targeted replay case executes in a separate process, computes the frozen reference first, and compares complete candidate outputs.

| Attempt | Agent / total steps | Tool calls | Source files; +/− | Agent s | Verifier s | Trial total s |
|---|---:|---:|---:|---:|---:|---:|
| GPU4 | 107 / 108 | 133 | 5; +186/−1 | 2745.591 | 501.562 | 3266.347 |
| GPU5 | 80 / 81 | 101 | 5; +217/−1 | 10438.520 | 51.999 | 10509.320 |
| GPU6 | 107 / 108 | 134 | 4; +105/−26 | 4080.082 | 496.636 | 4595.547 |
| GPU7 | 61 / 62 | 88 | 4; +104/−12 | 2175.225 | 505.077 | 2699.473 |

Times above are Harbor trial timestamps; launcher totals additionally include launch overhead. Counts use final Base-relative patches and untracked text, not accumulated edits or generated objects. Original result files and [metrics](evidence/rollout-r02/r02-completed-metrics.json) retain IDs, checksums, precise timings, source counts, native hashes, snapshots and replay records. No aggregate JUnit result is invented.

| Independent input behavior | GPU4 | GPU5 | GPU6 | GPU7 |
|---|---|---|---|---|
| Aligned offset-zero controls, 6 | 6 pass | 6 pass / 0 fail | 6 pass | 6 pass |
| Contiguous offsets 1/3, 12 | 12 fail | 0 pass / 12 fail | 12 fail | 12 fail |
| Single large FP32/FP16 group, 2 | 2 fail | 0 pass / 2 fail | 2 fail | 2 fail |
| Irregular groups 33/17, 3 | 3 fail | 3 pass / 0 fail | 3 pass | 3 fail |

These are contract checks, not prescribed implementation strategies. A contiguous tensor may have an unaligned data pointer; group divisibility alone is insufficient. A single legal group can require more shared memory than the chosen launch budget; reducing groups-per-block to one does not solve that case. GPU4/5 cap group packing but omit a single-group fallback; GPU6/7 omit the resource cap. GPU5/6 have a scalar path for irregular group lengths; GPU4/7 do not. The observed matrix separates these behaviors even though all full-task rewards are zero. Failing large-group comparisons include wrong quantized values and scales or unwritten output; a successful return alone is not counted as a pass.

## Complete trajectory and final-state review

All recorded model-visible reasoning, messages, tool calls/results and final responses were read. Final raw-session boundaries are GPU4=536, GPU5=409, GPU6=540, GPU7=345. All final tracked/untracked text was inspected. Full inventories also cover ignored state. Ordinary Python bytecode matches its source with the image’s Python 3.12.11: 35/53/35/4 files for GPU4/5/6/7. Pytest-rewritten bytecode is accounted for by unchanged test sources and recorded pytest commands. Generated CMake/Ninja differences are normal hostnames, build paths, dependency-list regeneration and build logs. The six FlashAttention Python files installed by GPU5's full build are byte-identical to immutable-image dependency sources; its additional native libraries are retained in the full replay.

No grading manipulation or successful external answer acquisition was observed. GPU4's GitHub curl attempts and GPU7's WebFetch attempts failed. Other reads were normal pinned-Base development. Recorded outside-repository writes are temporary builds/probes, package/cache activity and agent logs/memory. This bounded review is not a claim of exhaustive system-wide isolation or immunity to arbitrary native process compromise.

GPU4/6/7 build only `_C`; GPU5 chooses full `setup.py build_ext` despite the clarified guidance, spending most of its 10438.5-second agent phase compiling unrelated targets. It completes the build and revalidates the installed extension. Two additional broad quantization test files time out after 900 seconds without diagnostic output; the cause is unproven, and this is not recorded as a pass. No model-phase cache, prompt, source, time-limit or resource intervention occurred. Ordinary compiler cache was seeded only after final capture and verifier start for GPU4/6/7 original scoring and the saved replays. GPU5 original scoring reused its own full-build cache, without curator seeding. Early replay seed attempts were correctly rejected before the verification gate; no cache was injected then.

## Numerical tests and performance reporting

GPU4 and GPU7 independently notice and correct a self-benchmark that enters a mock-patch context inside every baseline call. Their final clean self-timings are 2.22–3.12× and 2.34–2.89×; GPU6 reports clean 2.26–2.71×. These self-tests do not override incorrect outputs, and none is labeled formal scoring performance. GPU5 retains the mock overhead and reports 2.64–13.66×; those ratios are invalid performance evidence. The trusted verifier's frozen baseline avoids candidate self-timing distortions.

GPU6 temporarily forces the Triton route to compare MoE behavior, then restores native routing before its final snapshot and rebuilds. Its final native MoE run passes 220/224; the forced-Triton comparison passes 221/224, with partly different failing configurations. Repeated selected native failures are deterministic, so the model's speculation about flakiness is not established. Its final statement that four native failures are 'at or below' three baseline failures is incorrect. These integration results are recorded without claiming parity; they do not by themselves justify replacing the explicit per-operator one-integer-step tolerance with a stricter hidden MoE assertion.

The upstream FP8 Triton reference cannot compile `fp8e4nv` on sm80, including on Base. Such failures are not counted as successful tests. GPU6/7 modify shared FP8 code, so curator checks separately exercise 24 native FP8/PyTorch-reference combinations each, covering shape, group size, column-major scales and UE8M0; both pass. GPU7's first diagnostic invocation found the original Harbor container stopped and executed no candidate; its successful retry on the completed replay container is preserved separately. GPU4/5 leave FP8 source unchanged. Their limited self-checks do not establish exact full-range FP8 parity.

## Task and verifier decisions

1. Keep the 1.2.6 resource/irregular-group repairs and platform-capability fallback test. The valid single-large and multigroup irregular inputs must remain supported. Fallback simulation happens before candidate import, allowing legitimate renamed imports and import-time cached capability decisions.
2. Keep the 1.2.7 Oracle pointer guard and three new public/native contiguous-offset cases. R01 proves their necessity through a former reward 1 candidate that violates the contract; a separate full Flash candidate and the Oracle/alternative pass them.
3. Keep the 1.2.8 build clarification. It changes only instruction/version metadata; executable grader, Oracle, controls, image and 1.5× threshold remain byte-identical to 1.2.7.
4. Do not add rank-one inputs: the statement explicitly requires at least two dimensions. Do not add stricter MoE integration tolerances merely because a candidate investigated them. No existing valid-input test is removed to manufacture a passing distribution.

The 20-control production-entrypoint matrix and independent Oracle/alternative checks from the identical 1.2.7 runtime remain applicable; they are not mislabeled as fresh 1.2.8 model trials. Fresh actual 1.2.8 Harbor Oracle acceptance has reward 1, zero exceptions, all seven stages complete and minimum 2.320×. With complete two-round evidence, no further executable repair is warranted. Final documentation/evidence checks suffice; another model round or full Oracle rerun after documentation-only edits would add no required validation.

Limitations remain: actual ROCm hardware was not tested; gateway model revision is unavailable; the whole root filesystem was not captured; development-derived cases and these eight attempts are not held-out estimates of model capability. See [current validation summary](review-report.md) and [machine-readable evidence](e2e-evidence.json).
