# infra-bench-opt

This is an independent optimization track in the same repository. Ordinary tasks retain their existing binary acceptance and leaderboard contract. Optimization tasks live under `opt/tasks/` and use continuous scores, separate result records, and separate campaign summaries. Do not feed optimization results into the binary archive or reinterpret a validity flag as a performance score.

## Scoring contract

For a serving task with fixed workloads, let `r_i = candidate_throughput_i / baseline_throughput_i`. The primary score is the geometric mean of these ratios with weights frozen by the task before evaluation. The first Ascend serving task uses equal weights for 1K, 4K, 16K and 64K inputs. Baseline score is 1.0. Scores 0.95, 1.02 and 1.50 mean a 5% regression, a 2% improvement and a 50% improvement respectively. There is no 1.03 cutoff, binary success threshold, rounding to an integer, or upper clipping.

A complete correctness gate and valid measurement are prerequisites. A valid regression remains a valid score below 1.0. Incorrect, incomplete, late and infrastructure-error results have `valid: false` and `score: null`; preserve their distinct statuses and diagnostics. Missing results never count as successful optimizations. Report per-workload throughput, latency, ratios and variability, including regressions hidden by an improved aggregate.

Every result has schema `infra-bench-opt.result.v1`, benchmark `infra-bench-opt`, a task ID, kind (`baseline`, `candidate`, or `smoke`), status, validity, score, improvement percentage and completion timestamp. Baselines have score 1.0 and status `BASELINE_VALIDATED`; valid candidates use `VALID`, including regressions. `INVALID`, `ERROR` and `LATE` have no score. Smoke results are diagnostic-only. A candidate binds to the SHA-256 of its frozen baseline record and identifies its source/configuration snapshot. Detailed task-specific measurements remain in the result. There is no binary `reward.txt` in this track.

## Fixed-budget campaigns

The standard budget is four hours per model, measured by the trusted controller. Environment preparation and a verified baseline precede the timer. Code generation, compilation, tuning, failed trials and complete candidate validation consume the budget. Only validations completed and recorded before the deadline enter the best-within-budget result. Before launching each fresh candidate measurement, register its frozen source/configuration fingerprint with `begin`. Supply that trusted trial receipt to the task verifier; do not register historical measurement artifacts as new trials. The receipt binds the candidate, baseline and shared completion deadline; the controller also checks its own receipt time, so a backdated completion field cannot admit a result submitted after the budget.

The campaign score is the best valid score reached within the budget, with the known baseline (1.0) as an explicit fallback. Preserve every candidate's raw score: the fallback does not turn a 0.95 candidate into a 1.0 candidate. Report the selected source/configuration, improvement percentage, valid/invalid/late/error counts and the improvement curve. A campaign with no valid improved candidate is explicitly a baseline fallback. Compare methods under the same frozen baseline, hardware allocation, workloads, validation protocol and budget. For repeated campaigns, publish every run and a declared aggregate such as the median; do not silently publish only the best repeated run.

Use Qwen3.6-27B for method development and a separate Qwen3.6-35B-A3B campaign to evaluate the frozen method's generalization. Each gets its own baseline and four-hour budget. Do not combine their scores or tune the method using held-out outcomes unless a new benchmark protocol explicitly allows it.

## Trusted records

`tools/infra_bench_opt.py` implements campaign bookkeeping and result validation, not model execution or a hardware scheduler. Run it only in the trusted controller environment. The agent must not be able to read or write campaign directories, private tests, expected answers, result files or baseline records. The controller must launch measurement, collect independent timing and preserve source/workload identities; accepting arbitrary agent-authored JSON is outside this tool's trust model. A checksum is an identity check, not an authenticity proof.

Private tests are supplied only after an agent checkpoint is frozen. Keep assertions and expected answers outside processes executing candidate-generated code. Hiding tests during the agent phase does not by itself protect the verifier from candidate code executed later.

```bash
python3 tools/infra_bench_opt.py start --campaign /trusted/new-campaign --task TASK_ID --method FROZEN_METHOD_VERSION --baseline /trusted/baseline/summary.json
python3 tools/infra_bench_opt.py info --campaign /trusted/new-campaign
python3 tools/infra_bench_opt.py begin --campaign /trusted/new-campaign --source-sha256 CANDIDATE_SNAPSHOT_SHA256
# Launch fresh measurement, then run its verifier with the returned --trial receipt and frozen baseline.
python3 tools/infra_bench_opt.py record --campaign /trusted/new-campaign --result /trusted/candidate/summary.json
python3 tools/infra_bench_opt.py summarize --campaign /trusted/new-campaign
# After budgets expire: rank repeated campaigns using median best-within-budget scores.
python3 tools/infra_bench_opt.py leaderboard --campaign /trusted/run-1 /trusted/run-2
python3 -m unittest discover -s tools/tests -p test_infra_bench_opt.py
```

This initial track does not change existing binary tasks, register an Ascend CI runner, or claim Harbor execution support. Task-specific native validation and common-protocol tests must be reported separately from runner integration.
