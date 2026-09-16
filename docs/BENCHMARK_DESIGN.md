# Benchmark Design

## 1. Objective

AI Infra Bench measures how much real AI-inference engineering work frontier coding agents can complete under fixed environments, harnesses, and resource budgets. It also studies where additional test-time compute stops helping and why agents fail.

The unit of evaluation is an independently verifiable engineering task. It is not an issue, a pull request, or a patch-similarity score. One pull request may yield multiple tasks, or none if it cannot be reproduced and scoped without leaking the solution.

## 2. Research questions

### RQ1: What is the real maintenance workload in vLLM?

This is an observational study of the community, separate from the agent benchmark score.

We will measure:

- issue arrivals, closures, backlog, first human response, first
  snapshot-collaborator response, human-annotated substantive response, and
  time to close;
- pull-request categories, first review time, time to merge, review rounds, requested changes, review comments, reviewers, and code churn;
- monthly demand relative to active maintainers and reviewers;
- workload categories such as bug fix, feature, performance, refactor, test/e2e, CI/build, docs/API, and chore;
- subsystems such as models, scheduling, memory/KV cache, distributed serving, kernels/operators, frontend/API, and hardware backends;
- accelerator coverage across CPU, NVIDIA CUDA, AMD ROCm, Intel XPU, Ascend NPU, MLU, and cross-backend work.

GitHub activity is only an observable proxy for human effort. We will not equate comment counts or elapsed time with actual engineering hours without maintainer-survey calibration.

Because vLLM emerged in 2023, the proposed reporting windows are launch through 2024, calendar year 2025, and 2026 through the frozen snapshot date. Monthly time series remain the primary view.

The canonical observational snapshot is the
`vllm-github-data-2026-07-31` release. Its collaborator list is a May 18
snapshot roster, not historical event-time maintainer membership. The August
8 API collection is a later supplement.

The frozen operational definitions and data-quality rules for this study are
documented in [`RQ1_METHODS.md`](RQ1_METHODS.md).

### RQ2: How much of that workload can agents solve?

We will report overall and stratified success rates by workload, subsystem, hardware tier, patch size, estimated expert effort, and benchmark track. Any headline coverage estimate must include its task composition and confidence interval.

### RQ3: Why does test-time scaling saturate?

Complete trajectories will be analyzed across the following failure stages:

1. problem understanding;
2. environment setup or reproduction;
3. localization;
4. root-cause hypothesis;
5. implementation;
6. test selection;
7. correctness regression;
8. performance regression;
9. resource or tool failure;
10. test overfitting or reward hacking.

Failure labels should be independently assigned by two reviewers on a sampled subset. Model self-assessment alone is not sufficient.

## 3. From sources to tasks

```text
GitHub events
  -> 200-PR candidate pool
  -> 76 representative sources

Maintainer survey
  -> memorable sources
  -> split, merge, reject, or supplement
  -> 24 memorable tasks

Both tracks
  -> reproduce -> scope -> package -> verify -> expert review
  -> 100 validated tasks
```

The repository keeps three concepts separate:

- **source:** immutable issue, PR, and survey evidence;
- **candidate:** curator classification, sampling probability, feasibility, and cost estimates;
- **task:** a fixed base state, instruction, environment, reference solution, tests, verifier, and hardware contract.

The current survey file contains 24 sources, but zero validated tasks.

## 4. Benchmark composition

### Representative track: 76 tasks

The team will freeze a 200-PR candidate manifest and then select 76 tasks with a fixed random seed. Sampling is stratified primarily by workload type, then by time period, subsystem, and hardware tier.

Selection rules include:

- minimum coverage for bugs, features, performance, review-intensive changes, and heterogeneous backends;
- caps on low-diagnostic docs, style, and chore tasks;
- clustering of dependent PR series and shared root causes to avoid double counting;
- recorded inclusion probabilities so results can be reweighted to the observed workload distribution.

Sampling rules and seeds must be frozen before model results are inspected.

### Memorable track: 24 tasks

Maintainers nominate work that is important, difficult, or characteristic of AI-inference engineering: rare configuration interactions, silent wrong behavior, cross-repository root causes, correctness/performance tradeoffs, architectural review judgment, or new-hardware bring-up.

A nomination is not automatically a task. Curators may accept, split, merge, defer, or reject it. Open work without a stable solution remains in a future or live pool.

## 5. Task contract

Tasks use Harbor's native layout:

```text
tasks/<task-id>/
├── task.toml
├── instruction.md
├── environment/
│   ├── Dockerfile
│   └── lock/
├── solution/
│   └── solve.sh
└── tests/
    ├── test.sh
    ├── required/
    └── heldout/
```

Each task records its source IDs, benchmark track, workload and subsystem labels, source cutoff, base state, image and checkpoint digests, accelerator vendor/type/count, timeouts, and network policy. Reference-solution identifiers stay in curator-only metadata until the task is released.

### Instruction policy

- Use only information available before the reference solution.
- Describe symptoms, expected behavior, reproduction entry points, constraints, and evaluation dimensions.
- Do not reveal PR numbers, reference commits, target files, functions, or fix strategies unless they were already present in the original issue at the task cutoff.
- Review-derived tasks should express maintainer-confirmed requirements rather than asking the agent to reproduce the final diff.
- Every synthetic instruction must be checked for offline solvability and maintainer intent.

### Git leakage policy

Checking out a base SHA is insufficient because Git objects, tags, branches, remotes, and reflogs may contain the future solution. The released environment should export the base worktree, remove the original `.git`, create a new repository with one synthetic base commit, and remove remotes, patch caches, and shell history.

Dependency fetching may happen while the image is built. Agent trials run with no network access.

## 6. Environment strategy

An OCI image does not pin the host driver, firmware, interconnect, or device runtime. Every run manifest must additionally record driver/runtime versions, accelerator SKU and count, MIG configuration, CPU/RAM, topology, power or clock policy, and model/checkpoint/tokenizer digests.

Hardware tiers are:

- **T0:** CPU, static analysis, and build tasks;
- **T1:** one canonical NVIDIA GPU;
- **T2:** multi-GPU, pipeline/tensor parallelism, or disaggregated serving;
- **T3:** architecture-specific kernels and ROCm/XPU/Ascend/MLU tasks.

One task binds to one canonical hardware contract. Cross-backend behavior should use paired task variants rather than a full model-by-accelerator Cartesian product.

Harbor is the control plane and task format. Local Docker with the NVIDIA runtime is the development path; one supported cloud GPU provider should be selected for parity testing. Heterogeneous accelerators may require self-hosted Kubernetes or Slurm runners implementing the same prepare/run/collect contract.

## 7. Verifier design

Every task must demonstrate:

1. the base state fails reliably;
2. the reference solution passes;
3. a no-op fails;
4. a patch hard-coded to public examples fails;
5. at least one plausible but incorrect patch fails;
6. held-out tests are offline and deterministic, or variance is explicitly modeled;
7. a human can solve the task from the released instruction and environment;
8. a domain expert approves the instruction and verifier coverage.

Tests are injected after the agent finishes. Tamper-sensitive tasks use a separate verifier environment. Rewards are based on behavior, constraints, and performance, never patch similarity.

### Performance rewards

Correctness is a hard gate. For a metric normalized so that larger is better, let `B` be base performance, `G` reference performance, and `A` agent performance:

```text
performance_reward = correctness * clip((A - B) / (G - B), 0, 1)
```

The raw, unclipped improvement is also retained. Workload, warmup, concurrency, batch shape, model, hardware, and clocks must be fixed. We report repeated-run medians, tails, and coefficient of variation. If the reference improvement is not clearly larger than measurement noise, the task cannot use performance as a grader.

## 8. Evaluation protocol

### Harness tracks

- **Model track:** all models use one locked common harness, initially a minimal shell-based or mini-swe-agent baseline.
- **System track:** native combinations such as Claude with Claude Code and GPT with Codex.

System-track scores measure a model-plus-harness product and must not be presented as pure model rankings.

Every run freezes the agent commit, system prompt, tools, context policy, immutable model ID, sampling parameters, turn limits, wall-clock limit, token budget, and cost budget.

### Metrics

- `pass@1` as the preregistered primary metric;
- `mean_pass_4`, the fraction of four independent trials that pass;
- `pass@4`, whether at least one of four trials passes;
- success by wall-clock time, reported tokens, and API cost;
- correctness-gated continuous performance reward;
- macro-average and workload-reweighted coverage with bootstrap confidence intervals.

Token accounting differs across providers, so wall-clock time and actual API cost are reported alongside tokens.

### Repair-loop study

The primary benchmark uses one final hidden-verifier submission. An iterative `verify -> feedback -> repair` loop is a separate test-time-scaling experiment with preregistered coarse feedback and a fixed number of repair rounds. Hidden assertions, expected outputs, and grader source are never disclosed.

## 9. Live benchmark

Monthly releases retain 60–80 anchor tasks and rotate 20–40 tasks. Retired tasks record whether the reason was leakage, dependency failure, hardware retirement, or a grader flaw. Overlapping anchor runs calibrate score drift between releases.

Every release freezes a dataset version, image digest, task hash, and run protocol. High-contamination-risk tasks may remain private until after evaluation.

## 10. Initial delivery plan

- **By August 16:** freeze RQ1, produce the full monthly snapshot and 200-PR candidate manifest, validate taxonomy, and freeze the sampling seed.
- **By August 21:** deliver five Harbor pilot tasks with base/reference/no-op/wrong-patch checks, local/cloud parity, human solve, and maintainer review.
- **Week of August 22:** expand the task set while reporting selected, packaged, and validated counts separately.
- **Week of August 29:** begin pilot evaluation on the frozen validated subset before scaling to the full release.

The number of source records is never used as a proxy for benchmark readiness.
