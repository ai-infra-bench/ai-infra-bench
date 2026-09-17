# First Flash round: rewards audited, revised round running

One original reward was a false positive: GPU5 passed task 1.2.6 despite failing on legal contiguous tensors with nonzero storage offsets. Replaying all four complete saved repositories against the repaired 1.2.7 verifier gives **0/0/1/0**, versus original **0/1/1/0** in GPU4/5/6/7 order. GPU6 remains a valid passing candidate under the expanded suite. The other original zeros are supported by independent precision or large-group failures. No additional scoring change is justified by the remaining first-round evidence.

This is a completed first-round review, **not final campaign acceptance**. A fresh four-concurrent Flash round on frozen task 1.2.8 is running. The added offset cases are development evidence, not held-out model evaluation.

## Scope and reproducibility

The user authorized Oracle-based task/verifier repair, four concurrent Harbor/Flash attempts per round, full trajectory review, and repeated evaluation. Initial task review and Oracle/alternative controls precede this campaign. Model `deepseek-v4-flash[1m]` comes from the configured A100 `env.sh`; the gateway supplies no immutable model revision. Claude Code 2.1.238 / Harbor 0.22.0 were used. The launcher does not override effort; raw sessions record effective `high`. Each attempt has one A100-SXM4-40GB, eight CPUs, 32 GiB, and gateway-only egress. Image: `sha256:5dc453932b016a3b73fb9316cce43f251275197b7a6295bc970e3de7a2718593`; vLLM Base: `14bf19e39f601163265b7c7d58d972b8a83d8896`.

Original task 1.2.6 is preserved at campaign revision `524816e`; per-trial checksums and prepared-input manifests are inside the archives. Original canonical and all prepared inputs match their pre-run hashes. Replays use frozen 1.2.7 runtime from `64068f1`; its executable tests/Oracle/controls are byte-identical to 1.2.8. Each replay verifies every saved snapshot file, restores the full repository including untracked/ignored files and `.git`, invokes exact root `bash /tests/test.sh`, rebuilds native code, and checks input hashes afterward. All four replay input checks pass. Fresh 1.2.8 round revision: `08c99c4e3f8e5120ed0ebbffd689e2be366bf5f0`.

The rollout-review skill used here has SHA256 `767fe719670c4a10753d7643cddbbab9c73f111c025f2d09fe03a6cf72a22f1f`. [Evidence manifest](evidence/rollout-r01/manifest.json) binds the redacted review packages. Full native binaries/repository archives remain on the authorized A100 under `/data/codex-pr70-rollouts-20260918`. Package manifests distinguish original versus redacted hashes. This is a repository snapshot, not a complete root-filesystem capture.

## All requested attempts

| Trial | Original reward | Revised full replay | Actual cause / finding |
|---|---:|---:|---|
| `flash-r01-gpu4__ZbVPMiY` | 0 | 0 | Existing precision cases fail; independent offset probes also fail |
| `flash-r01-gpu5__6QnVnqG` | 1 | 0 | Confirmed old-verifier false positive on contiguous offset views |
| `flash-r01-gpu6__TmyqHmi` | 1 | 1 | Complete original and revised suites pass; independent probes pass |
| `flash-r01-gpu7__NtByA8r` | Not scored | N/A | Docker address pool exhausted before model execution |
| `flash-r01-network-retry-gpu7__a7fi7fc` | 0 | 0 | One oversized group exceeds launch budget; offset probes also fail |

The failed startup was replaced on the same GPU with an explicitly unused subnet. It is retained in the inventory, not counted as a model failure. All four actual model trials finish without Harbor exceptions. The original passing candidates finish all seven verifier stages: operator surface, public dispatch, four ordinary cases, two configurable-argument cases, 18 public and 18 native boundaries, 18 configured ranges, and five timings. GPU4 returns a precision mismatch before timing; replacement GPU7 errors during boundary observation, also before timing. Its asynchronous allocation error was not assumed to be the first cause: isolated cases establish the bad launch/output.

| Model attempt | Agent / total ATIF steps | Top-level tool calls | Final source/test files; +/− lines | Agent seconds | Verifier seconds | Total seconds |
|---|---:|---:|---:|---:|---:|---:|
| GPU4 | 184 / 185 | 203 | 6; +332/−2 | 13014.072 | 119.702 | 13153.948 |
| GPU5 | 82 / 83 | 104 | 6; +334/−5 | 3455.531 | 1501.895 | 4977.569 |
| GPU6 | 166 / 167 | 181 | 6; +273/−2 | 12028.728 | 538.811 | 12588.155 |
| GPU7 replacement | 115 / 116 | 129 | 5; +216/−1 | 3190.754 | 1459.436 | 4670.063 |

Counts use final Base-relative tracked patches plus untracked text, not cumulative edits. Ordinary binary/generated files are inventoried separately. No JUnit aggregate passed/failed/skipped total was recorded, so none is invented. The startup failure took 2.255 s; model-step and code-change metrics are not applicable. Exact IDs/checksums, timing fields, file-level counts and snapshots are in [metrics](evidence/rollout-r01/r01-completed-metrics.json) and original result files.

## Behavioral findings

**Contiguous pointer offset — confirmed coverage gap.** The statement permits contiguous FP16/BF16/FP32 inputs with a divisible last dimension. Contiguity does not imply an aligned base pointer. `torch.randn(513, device="cuda", dtype=torch.float16)[1:].view(4,128)`, group 64, is a legal example. The stable public API and task-specified native op must match frozen Triton values within one integer step and return equivalent scales. GPU4/5/7 select vectorization from group divisibility without checking pointer alignment; their full saved states fail all 12 offset-1/3 probes across three dtypes and both entrypoints, while passing six offset-zero controls. GPU6 independently noticed this issue, added a pointer guard/generic path during its own trajectory, and passes all 18. No curator feedback was supplied to it.

The old suite only constructed ordinary aligned inputs; GPU5 therefore received reward 1 incorrectly. Version 1.2.7 adds three public/native offset cases and repairs the Oracle with an alignment guard and generic fallback. These are behavioral checks with no dependency on new private helper names or algorithms. Oracle and a distinct alternative each pass the expanded cases, and the old-offset-defective control fails. GPU4/7 were already wrong for other reasons, so their unchanged zero rewards do not establish adequate old offset coverage.

**Oversized single group — confirmed candidate defect, existing coverage retained.** Replacement GPU7 reduces groups-per-block to one but never handles one group larger than its 48 KiB launch budget. Valid cases `(1,16384)` FP32 / group16384 and `(1,32768)` FP16 / group32768 need 64 KiB in that implementation. Independent full output comparison finds quantized differences of 127 and unwritten/garbage scales. Other candidates pass these two cases. GPU4 explicitly opts in to larger dynamic shared memory; GPU5/6 use a global-memory fallback. This supports keeping the existing tests; it does not require any particular implementation strategy.

**Tiny values and zero-scale underflow — confirmed candidate defect, existing coverage retained.** GPU4 uses `1/scale` followed by multiplication and a zero-scale branch. Existing FP32 cases with magnitudes `1e-38`, `7e-38`, `2e-38`, epsilon `1e-45`, and an all-zero underflow case violate the explicitly required frozen-Triton parity. Both original public/native checks identify quantized differences greater than one. Fresh independent processes reproduce those four failures; small-normal, epsilon-dominated and all three empty cases pass. GPU7's separate nine-case replay passes every case, so its division intrinsic is not labeled faulty from source inspection alone. GPU5/6 pass these precision cases through complete scoring.

| Independent behavior | GPU4 | GPU5 | GPU6 | GPU7 replacement |
|---|---|---|---|---|
| Aligned offset-zero controls (6) | 6 pass | 6 pass | 6 pass | 6 pass |
| Contiguous offset 1/3 (12) | 12 fail | 12 fail | 12 pass | 12 fail |
| Single large FP32/FP16 group (2) | 2 pass | 2 pass | 2 pass | 2 fail |
| Irregular group controls (3) | 3 pass | 3 pass | 3 pass | 3 pass |
| Tiny-value/zero-underflow cases (4) | 4 fail | Pass in original full score | Pass in revised full score | 4 pass |

Every independent probe uses the frozen baseline in a separate process with the same effective inputs. An initial diagnostic only observed output and returned zero despite unwritten output; its logs are preserved, and no correctness claim relies on that exit code. The repaired diagnostic compares complete outputs and is proven to accept GPU5/reject GPU7. Curator replay setup errors (root ownership and a wrong snapshot directory in an initial GPU6 invocation) are separately recorded and never treated as candidate failures.

## Trajectories, performance and integrity

Complete model-visible reasoning, messages, tool calls/results and final source/test states were reviewed for all four attempts. GPU5/GPU7 ATIF streams and GPU4/GPU6 raw sessions were read fully; raw final boundaries are GPU4 event831 and GPU6 event753, with corresponding final ATIF files archived. All final tracked/untracked files were read. Inventories cover ignored build/runtime files too. Generated CMake/Ninja differences are normal hostnames, temporary build paths, dependency-list regeneration and logs; pytest cache keys are ordinary kernel tests. GPU4/6 each installed six FlashAttention Python files identical to the immutable image dependency. With the same Python 3.12.11, all 53/33 ordinary bytecode files respectively match their source code. A preliminary host-interpreter comparison mismatched due to version differences; same-version evidence resolves that diagnostic false alarm. Pytest rewritten bytecode is accounted for by test source and trajectory. The grader rebuilds `_C` from source.

No grading manipulation or successful external answer acquisition was observed in this reviewed material. GPU4 attempted two upstream WebSearch queries; both returned empty results. Its external Git lookup failed. Other source/history reads were normal pinned-Base development. Outside-repository activity observed in trajectories consists of temporary builds/probes, editable-install/cache writes and agent memory/logs. Because the full root filesystem was not captured, this is not a claim of exhaustive system-wide isolation or absence of all possible tampering.

GPU5 original minimum speedup is 2.336×. GPU6 original speeds are 2.523/2.835/4.429/2.841/3.853×; revised full replay minimum is 2.544×. GPU6's self-reported 4.01–12.67× is inflated by entering a mock-patch context inside every baseline call and is not used as performance evidence. GPU5/7 self-timings also include mock overhead. GPU4's clean-fixture self-timings of 2.11–2.78× do not rescue its incorrect outputs; formal timing is not reached. No missing performance result is presented as zero or a pass.

All attempts initially raised compile concurrency and hit the 32 GiB memory limit. GPU5/7 eventually built `_C` with CMake without completing full pip; GPU4/6 completed full pip after hours building unrelated FlashAttention targets and revalidated the final installed `_C`. Version 1.2.8 clarifies that the existing `_C` build target is sufficient and states the already-enforced resource/default settings. No algorithm hint, threshold, image, Oracle or test changed from 1.2.7. Phase-gated ordinary ccache seeding happened only after final candidate capture and verifier start, with provenance records; no model-phase cache or resource intervention occurred.

## Acceptance state and next round

The 1.2.7 20-control matrix and independent Oracle/alternative checks pass, including native FP8 preservation checks rather than counting unsupported sm80 Triton FP8 tests as successes. Fresh actual Harbor Oracle acceptance passes at 1.2.8 with minimum 2.320× and unchanged inputs. Runtime-control reuse from 1.2.7 is explicitly distinguished from that fresh run.

Round two starts four clean Flash attempts on frozen 1.2.8 with explicit nonoverlapping networks and retained containers. Its full trajectories and final states still require review. First-round-derived tests are not a population pass-rate estimate, and a second-round outcome will not be tuned to force a desired distribution of rewards.
