---
name: ai-infra-bench-task-review
description: Review and harden ai-infra-bench Harbor tasks by checking scenario authenticity, environment solvability and cutoff integrity, and behavioral verifier fairness. Do not use for ordinary code review.
---

# Review and Harden ai-infra-bench Tasks

Confirm that a task presents a realistic infrastructure problem, gives an expert
solver enough normal development material to reconstruct the essential
behavior, and scores externally observable behavior rather than one Oracle
implementation.

The task statement is an independent scenario. A PR, issue, incident, or patch
may explain the product, code path, failure mechanism, or possible directions,
but it does not define the task contract. Do not report differences from source
material as findings unless the task explicitly claims historical identity or
the difference makes the scenario impossible under the product's real
interfaces and semantics.

Treat first-person wording such as "our service" or "I observed" as part of a
constructed scenario unless the statement explicitly identifies or cites an
actual historical event, source, deployment, measurement, organization, or
person.

## Load the requested revision

When the user requests a skill from a remote branch, commit, or isolated
worktree, use the currently available instructions only to initialize that
worktree safely. After checkout, reread this `SKILL.md` and every required
reference from the target worktree before reviewing the task.

Record the skill worktree's absolute path, HEAD, and dirty state. When any
loaded skill file is modified relative to HEAD, record the SHA-256 of
`SKILL.md` and every reference or script actually used. Do not identify dirty
skill contents by the HEAD commit alone.

For every review, read
[references/review-rubric.md](references/review-rubric.md) in full. When the
user authorizes changes, validation, a commit, or a PR, also read
[references/validation-playbook.md](references/validation-playbook.md) in full.

## Working modes

- In review mode, inspect all three gates in order. An early failure prevents
  approval of later gates, but does not stop read-only diagnosis; mark later
  conclusions provisional when an earlier contract is not frozen.
- In hardening mode, fix the gates in order. Never change the verifier to hide a
  task-statement or environment problem.
- Commit, push, or create a PR only with explicit authorization. Preserve
  unrelated tracked and untracked changes and stage only the approved scope.

## Three gates

1. **Task statement:** Would a real user or infrastructure practitioner
   plausibly encounter or request this, using interfaces and operations that
   exist? Constructed context, prompts, and examples need not come
   from a public incident.
2. **Environment:** Can a strong solver reconstruct the behavior-determining
   path using the source and normal components in the image? Unavailable
   boundaries may be substituted when their semantics do not determine the
   problem. Task-specific mocks and reproducers must not be preinstalled.
3. **Verification:** Does the verifier execute the smallest semantically
   complete boundary, preserve required downstream behavior, accept different
   correct implementations, and reject incomplete or hacked ones?

Before judging environment completeness or E2E depth, write the target semantic
boundary in this form:

```text
input or event -> behavior-determining subsystem or state transition
-> observable result
```

Components that determine that transition must run for real. Other producers
or consumers may be substituted when the substitution preserves the relevant
state, cardinality, ordering, timing class, and lifecycle semantics. The number
of technologies mentioned in the user story does not determine E2E depth.

## Fixed project rules

- Every task has a 10-hour agent budget:
  `[agent].timeout_sec = 36000`.
- Cutoff applies to the target repository and history, models, tokenizers, data
  resources, external protocols, and runtime dependencies whose behavior
  affects the task. General benchmark infrastructure such as the base image,
  Python, Rust, uv, nextest, Harbor, compilers, and test tooling must be pinned
  for reproducibility but need not predate the task cutoff unless their behavior
  is part of the problem.
- Treat information as a solver leak only when it is visible during the agent
  phase and materially reveals the answer, tests, or investigation path.
- The Oracle is one reference implementation. Derive the behavioral contract
  before using the Oracle or tests to assess it.

## Findings and output

Use the priority definitions in the rubric. P0 and P1 findings require concrete
evidence such as a reproducible wrong reward, an unreachable target path, an
agent-visible leak, or an explicit contract contradiction.

Start the report with whether the task can be retained. Report each gate, the
semantic boundary and allowed substitutions, behavior-to-test coverage, actual
Base/Oracle/control results, reproducible counterexamples, and required artifact
changes. Suggestions that only improve difficulty or interest should remain
non-blocking unless the current task is invalid.

After authorized hardening, report final executable hashes, image identity,
stability and Harbor results, and the exact uncommitted, commit, or PR state. Do
not claim completion while a blocking finding remains open or evidence records
results that were not actually run.

You may run `scripts/audit_task_artifacts.py` for mechanical checks. Its JUnit,
image, and staged checks are optional layers; static success does not establish
scenario authenticity, E2E quality, verifier fairness, or actual control
behavior. Use `--strict-evidence` only for the final publication gate, when
incomplete executable hash coverage must fail rather than warn.
