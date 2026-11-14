# Contributing

AI Infra Bench welcomes real engineering problems from inference, agent harnesses,
training, and other AI infrastructure domains. You can contribute benchmark tasks,
environments, verifiers, workload analysis, documentation, or evaluation tooling.
You do not need to open an issue before contributing.

For a new task, follow this workflow: **choose a problem → build the task → review
and validate it → run model trials → open a pull request → maintainer review**.

## 1. Choose an AI infrastructure problem

Choose a problem that an AI infrastructure developer could realistically encounter:
a bug, a missing capability, or a performance bottleneck with observable behavior.
Explain the engineering value, affected domain and subsystem, and expected outcome.
Tasks are not limited to vLLM or the projects already represented in the benchmark.

Include the source repository and relevant issue, pull request, or other background
when available. An upstream issue or merged fix is not required; a task must still
be grounded in real interfaces and workflows. Describe known hardware, model,
checkpoint, and dependency requirements, along with reproduction or leakage risks.

## 2. Build the task

Follow the repository's [`create-task` skill](.agents/skills/create-task/SKILL.md)
for the complete construction workflow. In Codex, invoke `$create-task` with the
problem and source context. You can also follow the skill manually.

Tasks use [Harbor](https://github.com/harbor-framework/harbor) for reproducible agent
execution and grading. The [task template and conventions](templates/harbor-task/README.md)
are the maintained reference for directory layout, supported metadata, resource
settings, image manifests, and validation controls. Start from that template under
`tasks/<task-id>/`; the skill links to project-specific environment builders.

A complete task includes:

- an instruction describing the observable problem and required behavior;
- a pinned, offline environment containing the pre-solution source state;
- a behavioral verifier exercising the real subsystem end-to-end path;
- a reference solution and positive and negative validation controls;
- reproducible build and validation records identifying the exact task and image.

The agent environment must not expose solutions, task tests, validation artifacts,
or answer-bearing future source, dependencies, or caches. Hidden tests must follow
from the task contract and normal product semantics available to the solver.

Tasks without a complete reference solution need explicit acceptance of the
[`verifier_only` mode](templates/harbor-task/README.md#validation-layout). Provide a
solvability analysis, independent positive controls, repeated runs of the original
source state (Base) at the real target boundary, and a precise statement of what
remains unvalidated. These controls do not establish full-task solvability or an
Oracle pass. Do not use this mode to work around a failing reference solution.

## 3. Review and validate before submitting

We recommend running the
[`ai-infra-bench-task-review` skill](.agents/skills/ai-infra-bench-task-review/SKILL.md)
before opening a pull request. In Codex, invoke `$ai-infra-bench-task-review` for
`tasks/<task-id>/`. Without Codex, follow the linked
[review rubric](.agents/skills/ai-infra-bench-task-review/references/review-rubric.md)
manually. The quality requirements apply either way.

Review the task's realism, environment solvability, and verifier fairness. Fix
blocking findings and repeat the affected checks on the final revision. The
verifier must accept different correct implementations, rather than require the
reference solution's private names or structure.

Run the static task check from the repository root:

```bash
python3 .github/scripts/task_ci.py validate <task-id>
```

Static validation is only one part of readiness. Follow the skill's construction
and Harbor validation steps to demonstrate that:

- Base fails repeatedly because of the intended behavior, not an environment error;
- the reference solution (Oracle) passes repeatedly;
- no-op, output-spoofing, test-skipping, example-specific, and plausible partial
  fixes fail;
- a behaviorally correct alternative implementation passes;
- the real subsystem end-to-end path and final Harbor validation pass with the
  retained canonical image.

Performance tasks must show that the measured improvement exceeds environmental
noise. Accepted `verifier_only` tasks use the mode-specific controls described
above and explicitly report the missing full-solution validation.

Keep commands, image identifiers, checksums, test results, and limitations with
CI or Harbor run records **outside the task directory**. Link those records in the
PR. Label reconstructed inputs and simulated outputs accurately. Refresh affected
evidence after changes to the task contract or executable files.

## 4. Run model trials

Before opening a pull request, run real agent rollouts on the final task revision:
the same instruction, environment, verifier, and retained image that the pull
request submits. Score every run with the task's standard verifier, with the
verifier phase kept offline.

| Model | Runs per task |
| --- | --- |
| Claude Opus 5.5 | At least 2 (required) |
| GPT-6.1-sol | At least 2 (required) |
| DeepSeek V4.1 Flash | At least 2 (optional, strongly recommended); 4 when every Opus 5.5 and GPT-6.1-sol run passes |
| GLM 5.3 | 4 when every Opus 5.5 and GPT-6.1-sol run passes |

[`tools/local_agent_rollout.sh`](tools/local_agent_rollout.sh) runs one rollout
through Harbor with a locally built task image; its header describes credentials,
agents, and network modes. Report every attempt, including failed, interrupted,
and errored ones. Do not drop or replace a run because of its reward. Keep model
credentials out of the task, the run records, and the pull request.

For each run, record:

- **Run configuration:** model ID, reasoning effort, agent harness and version,
  agent timeout multiplier, Harbor version, task commit, image ID, effective
  CPU/memory limits, network policy, and the Harbor job and trial IDs;
- **Result:** reward and verifier passed/total, with a link to the run record;
- **Hack screen** for every reward-1 run: check the trajectory, final submission,
  and scoring path for fabricated results, skipped or missing tests, early
  successful exits, report or reward writes, test- or input-specific special
  cases, and answer leakage, as described in the
  [`ai-infra-bench-rollout-review` skill](.agents/skills/ai-infra-bench-rollout-review/SKILL.md).
  For pi tasks, [`tools/rollout_hack_screen.py`](tools/rollout_hack_screen.py)
  automates a first pass; every hit still needs a manual look;
- **Failure attribution** for every reward-0 run: a model error, a verifier
  problem (an unstated requirement, an over-strict assertion, or a rejected
  correct answer), or an environment or infrastructure failure, with the evidence
  for that conclusion.

Model trials do not establish that a task is valid. They show maintainers how
frontier models approach the task and expose verifier weaknesses that the
controls missed. When a run reveals a verifier, instruction, or environment
problem, fix it, repeat the affected checks in section 3, and rerun the model
trials on the new revision. Results from an earlier revision do not count toward
the required runs, except that saved submissions may be regraded on the new
revision when only the verifier changed; label those results as regraded.

### Tasks that may be too easy

When every Claude Opus 5.5 and GPT-6.1-sol run passes, also run DeepSeek V4.1
Flash and GLM 5.3 four times each. If all of those runs pass too, the task is
likely too easy for the benchmark, and we may decline it unless the pull request
shows evidence of its value. Such evidence could show, for example, that the task
covers a subsystem, failure mode, or hardware path that no existing task covers,
or that maintainers or users have reported the problem as one that matters in
practice. Apart from this rule, no pass rate is required.

## 5. Open a pull request

Create a focused branch from the current `main`. Before submitting:

- inspect the complete diff and keep unrelated changes out of the commit;
- confirm generated environment files match their shared templates where applicable;
- confirm the retained image matches the final build inputs and contains no leaked
  curator material;
- complete the self-review and validation required by the task's validation mode;
- complete the required model trials on the final revision.

In the PR description, include:

- **Problem:** AI infrastructure domain, engineering value, and source context;
- **Task:** required behavior, pinned base commit, and real end-to-end boundary;
- **Environment:** hardware and asset requirements, retained image identity, and
  any reconstructed inputs or unavailable hardware;
- **Validation:** self-review findings and resolutions, Base/Oracle/control results
  as applicable, and links to final run records;
- **Model trials:** one row per run with the model, harness, reasoning effort,
  task commit, reward, verifier passed/total, hack-screen result for reward 1,
  failure attribution for reward 0, and a link to the run record. When every run
  passes, include the evidence of the task's value described in section 4;
- **Limitations:** remaining uncertainty, missing evidence, or accepted exceptions.

Wait for CI results and address failures before requesting maintainer review.
If a review change affects the contract, environment, solution, verifier, or
validation inputs, rerun the affected checks, including model trials as described
in section 4, and update the PR evidence.

## 6. Maintainer review

Maintainers review the problem's authenticity, environment reproducibility, and
scoring fairness. Contributor self-review and model trials support this
independent review. Maintainers check the reported trials, may run additional
models or harnesses, and use the
[`ai-infra-bench-rollout-review` skill](.agents/skills/ai-infra-bench-rollout-review/SKILL.md)
to inspect final submissions, trajectories, and rewards, distinguishing model
errors from verifier weaknesses and environment failures.

Resolve blocking findings and repeat affected validation before inclusion in the
benchmark. A model's pass or fail alone does not establish that the task is valid.
Keep the task revision, image identity, and verifier version tied to the reported
results so later changes can be evaluated against the correct snapshot.

## Other contributions

For documentation, tooling, environment, or verifier improvements, open a focused
PR explaining the change and relevant checks. Task-affecting changes must repeat
the affected review and validation steps above.

For survey data, preserve respondent wording under `survey` and put curator
inference under `benchmark`. Survey evidence belongs in
`data/vllm_survey_results.jsonl`. Check that each JSONL line is valid, source IDs
remain unique, and public documentation links resolve. Do not include respondent
email addresses, identities, personal profile/comment links, or private discussions.
