---
name: ai-infra-bench-task-review
description: Review and harden ai-infra-bench Harbor tasks by checking, in order, the authenticity of the task statement, the authenticity and cutoff integrity of the environment, and the behavioral alignment and fairness of the verifier. Do not use for ordinary code review.
---

# Review and Harden ai-infra-bench Tasks

The goal is to confirm that the task describes a real infrastructure problem, the image provides a realistic development environment that could have existed only on the cutoff date, and the verifier accepts different correct implementations while rejecting incorrect or hacked solutions.

Every task must pass three gates in order: task statement, environment, and verification. When an earlier gate has a blocking issue, do not conceal it by changing a later gate. Do not change the task contract to accommodate the verifier.

For every review, read [references/review-rubric.md](references/review-rubric.md) in full. When the user authorizes changes, validation, a commit, or a PR, also read [references/validation-playbook.md](references/validation-playbook.md) in full. You may run `scripts/audit_task_artifacts.py` as a final static gate, but static checks do not replace behavioral validation.

## Working modes

- When the user asks only for a review, review the task completely. You may run any commands needed, including reproducing the behavior inside the image and running the verifier, but do not modify the task or create a PR.
- When the user asks for changes, continue in the same isolated worktree and from the same reviewed version. Map each finding to its change before editing the approved scope.
- Commit, push, or create a PR only with explicit user authorization. Stage only the target paths and preserve all other tracked and untracked changes.

## Gate 1: The task statement describes a real problem

The problem must be real, and every detail must be factual. It may come from an ordinary user's day-to-day work, such as deploying an inference service locally, training a model locally, encountering unexpected behavior, or needing the infrastructure to support something new. It may also come from an infrastructure practitioner, in which case it can be more specialized, such as conducting an investigation or building tools for performance or behavior analysis.

Desired task directions include GPU kernels, model serving, distributed systems, training, profiling, agent-harness features, agent-harness bug fixes, and multi-agent design. This list is not exhaustive. Use these as sources of task ideas when they lead to a real workflow and a factual problem, not as a reason to combine unrelated requirements.

Check each of the following:

- The user's actions match the real semantics of the product and project.
- Every command, configuration, request, input, output, error, log, metric, and sequence of events has been validated in the pinned environment by some concrete method.
- Logs in the task statement must be produced by the corresponding real code path. They must not be hand-assembled from output that does not exist.
- The task statement includes only information the user has, observable symptoms, the expected outcome, and behavior that must remain intact.
- It does not reveal the root cause, Oracle function names, variable names, internal state, algorithms, or the test inventory.

The task statement must not mention `reproducer`, `reproduction`, `mock`, `fixture`, `reduced`, missing CPU/GPU resources, curation work, qualification checks, or the origin of supplied materials. Those belong in validation evidence, not in the user's problem.

"Reproducible in the image" does not mean that every GPU- or model-related problem requires the actual GPU or model. A sufficiently capable solver may construct mocks in the environment and still reproduce the behavior. The image itself must not contain mock scripts or reproduction scripts, because they make the problem easier.

## Gate 2: The environment looks like a real development environment

Review the image only after the task statement is frozen. The image must allow the agent to investigate and fix the problem using only the task statement, source code, and components that would normally exist in the environment.

Check each of the following:

- Every real component required by the task statement is present. For example, if the task uses a particular tokenizer, provide that tokenizer. If an agent or CLI participates in the workflow, provide the real program. Model weights that are not needed may be omitted.
- The source, dependencies, configuration, runtime assets, system tools, and resources are sufficient to reach the target code path.
- Directories, filenames, environment variables, users, the workdir, and component installation paths look like a normal development environment. They must not expose the task name or curation markers such as `assets`, `reproducer`, `solution`, `tests`, or `validation`.
- During the agent phase, tests, the Oracle, validation artifacts, evidence, reward logic, reproduction scripts, and mock scripts are not visible. No image layer may contain them either.
- The repository checkout, Git history, dependencies, and all additional components are no newer than the cutoff. Remotes, remote refs, tags, reflogs, fetch metadata, and reachable or unreachable Git objects newer than the cutoff have been removed.
- The base image, system packages, Python/npm/Rust dependencies, external binaries, tokenizers, model configuration, and other resources actually existed on the cutoff date, and their versions and hashes can be verified. Do not use packages or resources released after the cutoff to complete the environment.
- Every task has a 10-hour agent budget. `[agent].timeout_sec` must be exactly `36000`.

It is not enough for the environment to run the tests. It must be a normal development environment that a user could actually have created on the cutoff date.

## Gate 3: The verifier fairly checks the task statement

Once the task and image are fixed, verification must align with the task statement.

First, the verifier must be independent of the details of the Oracle implementation. It must never depend on Oracle-specific implementation details, such as functions, variable names, or intermediate algorithm state. Otherwise, other correct solutions may fail simply because the task does not require a particular function or Oracle variable. The verifier must align with the task statement, not the other way around. Never address this problem by adding required function names, algorithm details, or similar implementation constraints to the task statement. Change the verifier instead.

Second, the verifier must use behavioral tests rather than unit tests: it should use enough behavior-level cases related to the task to determine whether the described problem or requirement has been implemented correctly.

Third, the verifier must include a real end-to-end test. Environmental limits may make a fully literal E2E impossible—for example, a CPU sandbox may not have model weights or a GPU—so the E2E may use mocks. Even then, it must remain as realistic as possible. To test whether a parser bug has been fixed without model weights or a GPU, for example, the test may mock the model's generated text while keeping every other part of the path real, including a real downstream agent such as OpenCode making the request. Reviewers must determine how the E2E can be made more realistic under the available constraints.

Fourth, the verifier must include regression tests that protect existing behavior that the change might break. Fifth, the verifier must include hidden tests rather than testing only the cases described in the task statement, which could be special-cased.

## Blocking findings

Any violation of the principles in any of the three sections above is blocking. Assign P0, P1, or P2 based on the extent of validation and the severity of the issue.

## Review output

Start with a conclusion on whether the task can be retained, then report:

- The real user workflow represented by the task statement and validation evidence for every concrete detail.
- Required image components, realistic paths, the cutoff audit, and leak prevention.
- The line-by-line mapping between the task statement and verifier, behavioral tests, E2E, regressions, and hidden coverage.
- Actual Base, Oracle, adversarial-control, and alternative-control results.
- Blocking findings, reproducible counterexamples, and the artifacts that must change.

After the user authorizes hardening, report the final status of every finding, hashes of the final executable artifacts, image identity, stability and Harbor results, and the exact uncommitted or commit/PR state. Do not claim completion while any blocking finding remains open or while evidence contains results that were not actually run.
