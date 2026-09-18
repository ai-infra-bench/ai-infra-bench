---
name: ai-infra-bench-rollout-review
description: Review completed model rollouts for ai-infra-bench tasks after initial task and verifier review. Audit trajectories, final artifacts, and rewards to distinguish agent errors, hacks, weak or unfair verifiers, and environment failures; derive implementation-independent behavioral tests from differences between attempts. Use for post-rollout review and authorized verifier hardening, not initial task qualification or routine code review.
---

# Review Completed ai-infra-bench Rollouts

Use completed SOTA-model attempts as additional evidence about both the answers
and the benchmark. Initial task review is a prerequisite, not a guarantee that
the task, Oracle, environment, or verifier is correct. A reward is an observation
to audit, not ground truth about the answer.

This skill starts where initial task qualification ends. Read the earlier
review and the exact task revision used for the rollouts; do not routinely
repeat every initial image/provenance gate. Reopen the affected gate when a
rollout exposes contradictory evidence. If no initial review exists, make
post-rollout findings provisional and identify the missing prerequisite.

## Inventory artifacts and confirm validation mode first

Before interpreting scores, check each attempt's manifest, tracked patch,
untracked archive, captured status, trajectory, and verifier logs, or equivalent
immutable final-state evidence. Verify that they are readable, correspond to
the correct Base/trial, and cover the delivered state. Distinguish a missing or
failed collection from a valid empty patch/archive for an unchanged worktree.

Trajectory edit commands are not a final filesystem snapshot: later edits,
command failures, generated files, and verifier mutations can change the result.
When final state is missing, continue reviewing directly evidenced behavior
failures, but do not claim complete final-code review, exact final change counts,
faithful full-state replay, or complete hack screening. Label reconstructed
fragments as diagnostic artifacts, not recovered original deliverables.

For authorized new rollouts, confirm collection occurs after final agent writes
and before verifier mutations and teardown, with usable tracked and untracked
outputs. Reuse matching collection evidence; when the collector/harness changes
or evidence is absent, run a small actual harness integration check before the
campaign. A configured collector or parsed config alone does not prove capture.

Record the task's approved validation mode and review scope:

- For Oracle-based tasks, use the agreed Oracle and alternative-solution
  controls, reusing matching evidence and rerunning as warranted by changes.
- For approved verifier-only tasks, do not require an Oracle or multiple
  complete implementations to perform local review. Use independent contract
  evidence and positive/negative controls at the relevant behavioral boundary.
  A positive control must exercise the property being validated; a stub that
  merely emits the expected output does not prove the target implementation
  is correct.
- Keep test validity, a candidate's local correctness, and demonstrated full-task
  solvability separate. Boundary controls cannot establish that one complete
  solution satisfies all requirements together. Missing full-solution evidence
  is an explicit limitation, not an automatic blocker for an accepted
  verifier-only mode; demonstrated contradictions or wrong rewards still matter.

Do not silently select verifier-only mode because an Oracle fails or is absent,
and do not narrow the task contract merely to fit the available controls.

## Preserve the experiment

- Identify every requested attempt, including failed, interrupted, and errored
  attempts. Record the model and available immutable version, reasoning effort,
  agent harness/version, Harbor version, task snapshot hashes, Base, image
  digest, resource limits, network policy, and timings. Never invent an
  unrecorded model revision.
- Match prior review evidence to the actual instruction, verifier, image, and
  runtime used. Group differing revisions/configurations explicitly; a shared
  task slug does not establish comparability.
- Keep original rewards, logs, trajectories, and final artifacts unchanged.
  Store diagnostic replays and proposed tests separately. Record the skill
  revision and hashes for dirty instructions used in the review.
- Freeze replay/validation inputs and record their hashes before execution;
  verify them afterward. A post-run hash of a mutable worktree does not prove
  which bytes ran. Keep historical snapshot identities separate from current
  documentation and evidence-file hashes.
- Reviewing existing rollouts permits scoped local reproductions and diagnostic
  probes. It does not authorize new paid model rollouts, changed campaign
  settings, or publication. Apply task/scoring changes when the user's request
  authorizes hardening; commit or push only when explicitly authorized.

## Reconstruct the contract before judging answers

Read the statement and the normal development material available to the solver
at the pinned Base before relying on verifier expectations or the Oracle. Write:

```text
input or event -> behavior-determining subsystem or state transition
-> observable result
```

Map each required behavior to existing coverage, missing coverage, or an
explicit validation limitation. Every reward-zeroing assertion needs a
defensible contract. Recording gaps does not authorize expanding the repair
scope. Separate:

- explicit task requirements;
- unavoidable implications of the stated workflow and documented/stable
  product semantics discoverable in the solver's environment;
- ambiguous policies or new requirements introduced only by tests, the Oracle,
  a source PR, or reviewer preference.

Ordinary correctness need not be exhaustively spelled out. However, choices
such as retaining pre-upgrade cache files, migration policy, exact error timing,
or storage representation are not automatically required just because the
Oracle chooses them. An upstream PR is context, not a hidden extension of the
task contract. Do not expose solution internals in the statement to justify a
test that depends on them.

Distinguish structural, semantic, and experimental evidence:

| Evidence | What it can establish |
|---|---|
| SDK types and schemas | Types, requiredness, defaults, and explicit constraints in the applicable version. |
| Protocol and product semantics | What fields and operations mean, when they apply, and required value/lifecycle invariants within the task scope. |
| Reference implementation or candidate outputs | What that version did under the recorded inputs and effective configuration. Agreement is not a specification. |

Successful SDK serialization or parsing does not establish end-to-end semantic
correctness, and a type alone does not imply constraints it does not declare.
For example,
`signature: str` alone cannot justify a nonempty assertion; that needs separate
contract support. `Optional[int]` allows null, but omission also depends on
defaults or schema requiredness. Establish optionality and value semantics
separately: an optional cache-hit count is not arbitrary when returned, and an
exact expected count needs a justified mapping from backend accounting to the
public statistic, including units and applicable conditions.

### Reference implementations and differential comparisons

A reference implementation, regardless of language, product, or source, is a
comparison subject. It becomes normative only where the task explicitly makes
its specified behavior/version a compatibility requirement. Even there, check
the scope and allowed variation; do not silently resolve contract conflicts in
favor of the reference. Matching it is not a complete correctness proof, and
differing from it is not automatically a bug.

Compare effective semantic conditions: inputs, configuration, dependencies,
backend behavior, and lifecycle. Different flag names can express equivalent
conditions; a mismatch is a reason to investigate, not proof of a verifier
error. If a reference violates an independently established contract, record
its limitation instead of excluding the valid test. When the user restricts
the experiment to cases a chosen reference passes, honor that selection and
report excluded coverage without treating it as outside the task contract.

## Inspect each complete rollout and final deliverable

Read the recorded trajectory, tool inputs/results, iterations, and final
response for every attempt, subject to the recorded inventory limits. A final
summary or selected grep hits are not a complete trajectory review. For large
logs, work through indexed chunks and record missing or truncated material; do
not claim unseen evidence was checked.

Reconstruct what the agent diagnosed, which code it read, what it changed, how
its approach evolved, what it tested, and why it stopped. Distinguish actual
test results from the agent's claims. Explain whether failed commands exposed
an implementation error, an unavailable dependency, a fixture problem, or only
an unsuccessful search. Inspect local Git-history and external-fetch activity
for actual answer exposure; an attempted but blocked fetch is not evidence of
successful retrieval.

Review the final tracked diff AND untracked files, including new modules,
configuration, symlinks, binaries, and generated artifacts that affect runtime.
Also inspect commands that changed installed packages or files outside the
captured repository. Confirm which artifacts the verifier actually executed.
Replay the complete delivered state; if it cannot be reconstructed, state that
limitation rather than validating a silently reduced production-only patch.

## Judge correctness separately from reward

For each attempt report the observed reward, independent correctness finding,
attribution, and confidence. Multiple causes can coexist.

Distinguish an invalid assertion from an incorrect final reward. A bad assertion
may coexist with independent valid failures, so correcting it need not change
reward 0. Report whether the correction actually changes the full-suite reward;
mark untested reward impact as unverified. Do not label the whole attempt a
false negative merely because one assertion was invalid.

| Observed result | Required investigation |
|---|---|
| Reward 1, contract appears satisfied | Verify the causal implementation, completion of scored checks, and a relevant independent behavioral challenge before calling it correct. |
| Reward 1, contract violation reproduced | False positive: identify missing coverage, a bad expectation, or grading bypass. Distinguish an ordinary incomplete repair from deliberate scoring manipulation. |
| Reward 0, contract violation reproduced | Agent error when the input is valid, required behavior is inferable, the environment is adequate, and the failure occurs in candidate behavior. |
| Reward 0, contract-valid answer rejected | False negative: identify an undisclosed requirement, Oracle-specific constraint, incorrect fixture, or scoring/infrastructure failure. |
| Exception, timeout, missing records, or unresolved contract | Preserve the observation and mark affected conclusions inconclusive; establish whether the candidate, environment, or harness caused it. |

For reward 1, check for fabricated results, skipped or missing tests, early
successful exits, reward-file manipulation, test/model/input special-casing,
and answer leakage actually visible during the agent phase. Inspect the trusted
scoring path as well as the patch. Neither exit code zero nor a success marker
written by a process executing candidate code proves all checks completed.
Reading normal upstream tests, editing tests to add legitimate coverage, using
deterministic offline inputs, or differing from the Oracle is not itself a hack.
Report concrete actions and effects; do not infer intent from reward or patch
similarity. If evidence only supports 'not observed', do not certify absence.

For reward 0, trace each failure group to its first causal fault. A constructor
error inside a verifier-owned fixture is different from a wrong public result.
Required new candidate fields, alternate internal APIs, or different valid
validation timing must not become hidden constraints. Check the real caller
before labeling an internal API change an agent regression. Use minimal
diagnostic repairs to the fixture/environment when needed, clearly labeled;
do not quietly repair the candidate and report its original answer as correct.

### When every attempt fails

All-zero rollouts do not prove excessive difficulty, an invalid task, or
unsolvability. Likewise, one passing Oracle does not prove fairness.

Check that the unmodified Base fails because of the target defect or missing
feature, not a broken verifier setup. Select positive controls according to the
approved validation mode. Check contradictory assertions, unreachable paths,
missing behavior-determining resources, and fixtures that reject valid
alternatives. An Oracle failure alone proves only that the tested Oracle or
setup failed. Call a task unsatisfiable only with a concrete contradiction or
unavoidable environmental impossibility; otherwise identify what solvability
evidence remains missing without blocking supported local review.

Where a behavior's contract and execution boundary are established, distinguish
different defects among the failed answers even if full-task solvability is
unproven. A case may pass for some globally failing answers and fail for others.
That is useful differential evidence even while every original reward stays 0.
Do not equate one attempt passing a new case with completing the whole task.

## Derive behavioral cases from rollout differences

Read [references/differential-cases.md](references/differential-cases.md) before
designing, running, or promoting rollout-derived cases into the verifier.

Use observed implementation differences to propose hypotheses about missing
behavior, then specify the input and expected result independently of those
implementations. A new case must satisfy the same statement, discoverability,
semantic-boundary, and implementation-independence requirements as initial
task review. Difficulty or a desired pass/fail ratio never justifies it.

**Never make a scored test depend on solution-specific API names, functions,
classes, fields, variables, representation, file layout, or algorithm introduced
by a candidate or Oracle.** Existing or task-specified public/stable product
APIs are legitimate entrypoints; their name appearing in a solution does not
disqualify them. Internal inspection may diagnose a defect, but the promoted
assertion must observe contract behavior through a stable boundary or a
semantically faithful end-to-end lifecycle.

For all-zero campaigns, seek cases that separate meaningful correctness gaps,
not cases that manufacture winners. When reward requires all checks to pass,
adding a test cannot turn an existing reward 0 into 1. Fixing a demonstrated bad
test or clarifying a contract is a separate, versioned correction.

## Finish with evidence and a reproducible handoff

Use [references/reporting.md](references/reporting.md) for the attempt table,
behavior matrix, attribution, and validation records.

Distinguish original scores, diagnostic replay results, and any new-version
results. State confirmed findings separately from suspicions and unresolved
limitations. Prioritize wrong rewards and demonstrated bypasses over style or
difficulty suggestions. Identify whether the task can be retained, needs a
targeted repair, or cannot yet be certified.

Scale validation to the change using the
[validation stages](references/differential-cases.md#5-promote-with-validation-proportional-to-the-change).
Use minimal probes for diagnosis, affected cases/candidates during test edits,
and actual Harbor checks for collection/startup/scoring changes. Consolidate
full-scoring acceptance after the executable revision is frozen, following the
approved validation mode. Documentation-only changes need evidence consistency
checks, not repeated model or full-suite runs.

Use only actual executed evidence. Do not reroll models unless authorized;
regrading saved artifacts and generating new answers are different experiments.
Cases developed from these rollouts are not independent held-out evidence of
model capability. Report evidence limitations and the resulting benchmark and
commit/push state.
