# v1.8.5 rollout review — 2026-09-18

This is a compact publication summary, not a replacement for raw trajectories or a full security certification. The task executable files and instruction match the frozen inputs of the runs below. Only publication documentation was subsequently updated.

## Identity

- Model: GPT-6 Astra, reasoning effort high; Harbor 0.22, Codex 0.153.4.
- Base: `be3af2d29e2507f32b2190fe015cd6609b348caa`.
- Image: `sha256:462fc769cac14468d0c1a7128eb17116c728e12e31efaee14b9ea7fd6c3e9868`.
- Instruction SHA256: `2884d6c2f1e6cb53c8d0e6be7765017df43e51d89d013ee479ed716d7d81a25a`.
- Distributed verifier SHA256: `c32b446a9ab2f9dd51ce0f874b1487b617c575d49a5739d568f4b8f554872a0a`.
- task.toml SHA256: `2e5a5f13f7a4c70711eb6888728216a8dff0ff0255489c881ed00091b819fa6c`.

## Original full Harbor scores

| Attempt / trial | Reward | Completed checkpoints | Reviewed outcome |
|---|---:|---:|---|
| r01 `task__hb9ZYMp` | 1 | 24/24 | All required checks passed; two independent new-input generation challenges also passed. |
| r02 `task__TJjup8y` | 0 | 22/24 | FlashAttention default-interleave graph startup has a CUDA illegal access. Self-tests exercised a different valid compilation configuration and missed this dummy warmup path. |
| r03 `task__xkJSfhm` | 0 | 20/24 | FlashInfer chunked-prefill generation is numerically wrong: base-2 attention statistics are merged as natural-log statistics. Self-tests did not force cached partial-prefill. |
| r04 `task__eusrmxt` | 0 | 20/24 | Same observed FlashInfer partial-prefill defect; successful local tests did not cover this context merge. |

All four are actual model attempts on the same v1.8.5 runtime and prompt. No framework exception or scoring timeout occurred in these four runs. Concurrency differed, so 1/4 is only the observed count, not a stable pass-rate estimate. Fail-fast checks that were never reached are not additional observed bugs. Scores were not rewritten after diagnosis.

## Review and isolation

Available action timelines, testing feedback, final tracked/untracked changes and scoring reasons were reviewed. All three failed agents genuinely tested and iterated. No scoring manipulation was observed in the reviewed material; truncated tool output and unavailable private reasoning limit what can be claimed.

Ten diagnostic cases ran in fresh containers, sequentially on the same pair of shared-host H20 GPUs. The three original failures reproduced. Oracle and the unchanged successful r01 passed both failure scenarios (four positive cases). Three minimal candidate-only diagnostic overlays passed their corresponding failing scenario. The verifier inputs, independent CPU Transformers reference and tolerances were unchanged. Original candidate repositories were read-only and post-run hashes were checked.

The numerical failures affected 151/256 vocabulary entries, with maximum error approximately 0.107432 against a 0.02 tolerance. Correct implementations and diagnostic corrections produced maximum errors around 0.00234–0.00283. This supports genuine implementation omissions rather than excessive tolerance strictness. Diagnostic overlays were not full 24-checkpoint Harbor regrades or new agent successes.

## Evidence boundaries

The curator retains complete reports, trajectories, final code, score outputs and integrity records in campaigns `pr60-gpt6-v185-20260918` and `pr60-gpt6-v185-parallel-20260918`; these large raw campaigns are not embedded in this task. The latter includes `REPORT.zh-CN.md`, three per-run `REVIEW.zh-CN.md` reports, `FINAL_INTEGRITY.json`, and `isolation-review/results.json`. This summary does not claim those raw files are available in this PR.

The committed `evidence.zip` contains historical full control calibration, including v1.8.4 Oracle=1, distinct curated positive=1, Base=0 and historical v1.8.3 Oracle=0. It does not contain these new full model trajectories and is not a fresh full v1.8.5 control matrix. The v1.8.5 logging change separately passed five logging regression checks, including a real controlled child timeout preserving stdout and stderr.

No new verifier false rejection was confirmed in the reviewed failures. This does not certify all possible implementations/configurations, A100 hardware, grading trust, or throughput. The earlier isolated FlashInfer timeout still has no confirmed root cause; logging improvement and four subsequent timeout-free attempts do not prove it fixed. Existing review limitations remain open.
