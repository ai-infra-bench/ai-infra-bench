# Codex R01: full visible-trajectory and saved-repository review

The task can be retained at **1.2.9**. Four clean-container replays of the complete saved repositories, using the real rebuild and scoring entrypoint, yield **1 / 0 / 0 / 1**. No hack observed in the reviewed material. GPUs 0/3 were false negatives under the original verifier; GPUs 1/2 contain a genuine range restriction. This review introduces no further task/verifier changes and no new model attempts.

## Scope and immutable evidence

User-authorized full task validation on A100; original task 1.2.8 at `10517bbe64663bc350f31b88e3aec1ccc1e2ab7f`, corrected task 1.2.9 at `760abf7`. Model `gpt-6-astra`, explicit medium, Codex 0.153.4, Harbor 0.22.0; backend model revision not recorded. Base and immutable image are recorded in [the original campaign report](rollout-codex-r01.md). Four GPUs, 8 CPUs / 32 GiB per replay, network disabled. All four original trials completed with no Harbor exception; all native rebuilds succeeded.

All recorded visible native messages, calls, results and final responses were read in chronological order, cross-checked against ATIF, final tracked patches, untracked source/tests/benchmarks and delivered inventory. The visible index records source hashes and exact-duplicate references (7/5/6/5 chunks). Encrypted reasoning has empty summaries in all four sessions and is **not accessible or reviewed**. A few original tool results were already truncated; this review does not claim access to their omitted text.

Full repository archives include `.git`, ignored files, shared libraries and build trees. Six manifest files per candidate were verified before replay. Each inventory has 131 changed files, no deleted files or changed symlinks: nine authored production/test/benchmark/report files and 122 generated/cache/build files. GPU0's JSON benchmark report is ignored by Git and was included separately. Exact snapshot, native binary, task and input hashes are in the archived pre-run/record/inventory files. Post-run checks confirm frozen task inputs and snapshots unchanged. Final repository capture is complete; the entire external root filesystem was not captured.

## Per-attempt metrics

Times below are original Harbor total / agent / verifier minutes. Agent steps count ATIF `source=agent`; calls count native top-level exec/wait/sleep entries, not nested shell operations. File/line metrics include final tracked + untracked + authored ignored text, not cumulative edits or generated binaries. All four changed five tracked files and added a CUDA source, test, benchmark and report (GPU0 report ignored; others untracked).

| GPU / trial suffix | Total / agent / verifier min | ATIF agent / total | Calls | Authored files; + / − lines | Original reward | Full replay | Completed scoring stages | Self-tests |
|---|---|---:|---:|---|---:|---:|---:|---:|
| 0 / `NytaXYm` | 53.17 / 27.49 / 25.32 | 94 / 99 | 93 | 9; +543 / −20 | 0 | 1 | 7/7 | 93 |
| 1 / `jsbo3RN` | 47.28 / 22.07 / 24.85 | 69 / 74 | 68 | 9; +495 / −5 | 0 | 0 | 5/7 | 64 |
| 2 / `qCt7jRv` | 46.46 / 21.13 / 24.95 | 66 / 71 | 65 | 9; +422 / −6 | 0 | 0 | 5/7 | 146 |
| 3 / `ceaE7jY` | 45.99 / 20.81 / 24.82 | 69 / 74 | 68 | 9; +511 / −6 | 0 | 1 | 7/7 | 150 |

Trial UUIDs and full metric definitions/data are in [full-review-summary.json](evidence/codex-r01/full-review-summary.json). Original scoring completed only the operator-surface stage before an ABI error. Replay GPU1/2 fail configured ranges after five successful stages; performance is not completed, not pytest skips. GPU0/3 complete all seven stages. Native worker exceptions are recorded failures, not Harbor lifecycle failures. Self-test counts come from observed pytest output, with no reported failures/errors/skips, and do not replace curator scoring.

## Findings and trajectory evidence

**Confirmed verifier defect, already repaired:** the task names `_C::per_token_group_quant_int8` but does not prescribe output-parameter versus tuple-return ABI. All four independently implement the legal five-argument functional schema. The old scorer passed seven arguments, blocking every candidate before numerical evaluation. Task 1.2.9 resolves the registered public schema outside timed loops. Actual Oracle and functional positive-control Harbor runs both pass. This is a false-negative repair, distinct from the historical Flash unaligned-input false positive. Original scores remain 0/4.

**Confirmed agent defect, GPU1/2:** native guards require `int8_min <= 0` despite configurable INT8 clipping bounds and required reference parity. GPU1 also repeats the restriction in its Python wrapper. The existing `float16-1-100` case uses contiguous CUDA FP16 `[2,3,128]`, group 64, epsilon 1e-5, bounds `[1,100]`, repeated values `[-2,-1,0,.25,.5,1,1.5,2]`. Frozen Triton returns legal clipped values/scales; these guards raise instead. GPU0/3 pass. This is not an unusual invalid-input test. Keep it; candidate remediation is to accept representable positive lower bounds below a positive upper bound. Do not modify submitted candidates during evaluation.

Native session line anchors are relative to the original JSONL named in the visible index:

- GPU0: L132 removes the initial unnecessary nonpositive-lower-bound guard. Aligned vector fast path for groups 64/128, general warp path for other groups; offset gate present. L559 records 93 passed; L568/L576 contain measured timing/report. No hidden grader access or reward write observed.
- GPU1: initial launch-macro compilation fails at L209–214; L218 fixes macro placement, then rebuild/install succeeds. L444 records 64 passed, L461 benchmark measurements, L477 installed schema. Its tests omit positive lower bounds, so local green tests do not demonstrate full correctness.
- GPU2: vectorized groups 64/128 have a 16-byte alignment guard and generic fallback; the nonpositive-lower guard remains. L399 records 146 passed, L420 timings. L446 converts an ignored JSON report into Markdown. Self-tests include zero lower bounds but miss positive lower bounds.
- GPU3: L100 adds a missing alignment guard and test, L116 removes the initial nonpositive-lower guard, L130 removes the benchmark's dependency on its own test helper. It detects a final binding rebuild, reinstalls `_C`, then L440 records 150 passed on the final extension. L452 contains timing; L458 writes the report from measurements.

All four implement CUDA computation and public dispatch with a Triton fallback, guard/stream handling and early empty returns. No evidence of canned outputs, frozen-reference tampering, special grader branches, timing fabrication, reward-file writing, or reading hidden solution/verification files. Reading `/opt/bench/rebuild_native.sh` is inspection of the supplied build helper. Directory listings mentioning `codex-secrets` are not reads of credential content. Formatter installation attempts fail and are not successful environment changes. Observed outside-repository writes are build/test/timing logs and ordinary compiler/Python/Triton caches; unobserved external filesystem state cannot be certified.

## Complete snapshot replay and differential behavior

For each GPU, the existing `tools/curator/pr70-rollout/replay_saved.py` restored the **full** original repository in a fresh container and invoked `bash /tests/test.sh`, including its authoritative rebuild. No delivered `.so` substituted for rebuilding. Ordinary compiler-cache entries from the original GPU0 verifier build were seeded after verifier start, with entry hashes recorded. Cache keys determine reuse for the other sources; no build directory or native library was injected by the curator. Delivered snapshot build files naturally remain part of restoration. GPU0 reproduces the old library hash; others produce new hashes recorded separately, so diagnostics and fresh builds are not conflated.

| Behavior | GPU0 | GPU1 | GPU2 | GPU3 |
|---|---:|---:|---:|---:|
| Old seven-argument call | Fail | Fail | Fail | Fail |
| Legal functional operator under adapter | Pass | Pass | Pass | Pass |
| Positive lower bound `[1,100]` | Pass | Fail | Fail | Pass |
| Independent public/native offset probes | 18/18 | 18/18 | 18/18 | 18/18 |
| Isolated large-group / unaligned frozen-reference probes | 5/5 | 5/5 | 5/5 | 5/5 |
| Revised complete entrypoint reward | 1 | 0 | 0 | 1 |
| Minimum of five timed speedups | 3.009× | Not reached | Not reached | 2.772× |

Offset probes use an independent PyTorch expected computation across FP16/BF16/FP32, offsets 0/1/3 and native/public entrypoints. Five further probes isolate two existing large-group and three unaligned cases, run frozen-reference observation in a separate process, and explicitly compare results. These are supplemental checks, not additional model trials or additional grading points. They address the prior alignment/large-group risks and support both passing implementations without relaxing configured-range requirements.

Reproduction: use archived `start_codex_full_review.py` with the immutable image and original snapshot paths. Its per-GPU command is `replay_saved.py --container codex-pr70-codex129-replay-gpuN --snapshot <original-trial>/agent/final-state --base-manifest /data/codex-pr70-rollouts-20260918/base-file-manifest.json --task /data/codex-pr70-rollouts-20260918/next/tasks/vllm-int8-per-token-group-quantization --output <new-empty-output>`, followed by `audit_generated.py --inventory <output>/inventory.json --image <recorded-image> --output <new-empty-audit-output>`. Exact entrypoint, compiler, probe, stage and timing logs are archived. This is saved-state curator replay using the real test entrypoint, **not newly launched Harbor model trials**.

## Ignored/generated artifacts and limits

Generated text audits cover 16 files per attempt: CMake/dependency scripts/logs and pytest cache. Changes match the observed Release build, `/workspace/repo` install/build paths, container hostname and regenerated dependency lists; dependency source content is unchanged. Cache nodeids match 93/64/146/150 tests. All 24 ordinary bytecode records were checked without executing candidate bytecode: production bytecode matches source; five stale test/benchmark caches in GPUs1–3 have mismatching mtime/size headers and are invalidated by normal imports. All four pytest-rewritten caches exactly match fresh pytest assertion rewriting of delivered source. Follow-up records document these checks.

Other generated files are the recorded compiler/build outputs, object files and two copies of `_C`; they were inventoried and rebuilt, not reverse-engineered instruction by instruction. Replays reproduce the scoring behavior with freshly installed binaries. No new artifact-based scoring bypass observed. GPU0's ignored benchmark JSON matches its logged method/results but should be added explicitly if that candidate were submitted as a patch-only contribution; full-snapshot evaluation retained it.

ROCm routing is simulated, not measured on ROCm hardware. Encrypted reasoning, originally truncated output, and uncaptured external filesystem remain evidence limits. Historical 20-control results are not a freshly rerun 1.2.9 control matrix. Existing Oracle and functional Harbor controls establish task solvability for this environment; rollout-derived controls are development evidence, not held-out evaluation. Four attempts do not estimate general model success reliably.

## Disposition

Retain task/verifier 1.2.9 unchanged. Preserve positive-range, alignment, large-group and frozen-performance checks. Complete fresh rebuild results confirm the earlier diagnostic 2/4 outcome. This commit adds review/evidence only; the historical focused diagnostic report remains distinguishable from this full visible-trajectory and repository audit. Evidence and hashes: [manifest](evidence/codex-r01/manifest.json).
