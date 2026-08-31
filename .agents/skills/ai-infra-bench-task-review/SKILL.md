---
name: ai-infra-bench-task-review
description: Review and harden ai-infra-bench Harbor tasks by checking provenance, instructions, environments, verifiers, and evidence; do not use for ordinary code review.
---

# Review and Harden ai-infra-bench Tasks

A task is jointly defined by its source history, instruction, environment, solution, verifier, and validation evidence. A passing Golden patch proves only that one implementation satisfies the current tests; it does not prove that the task is valid.

## Working modes

- For a review request, stay read-only: inspect primary sources, run relevant non-mutating diagnostics, and report findings. Do not rewrite the task before the user approves the direction.
- For a hardening request, first read the review report, confirm that it still applies to the current task revision, and convert approved findings into a traceable remediation matrix. Only then begin editing.
- Commit only when the user explicitly asks. Stage exact task paths and exclude shared templates and unrelated dirty files.

Read [references/review-rubric.md](references/review-rubric.md) for every review. When the user asks to fix, build, validate, or commit a task, also read [references/validation-playbook.md](references/validation-playbook.md) before changing files.

## Principles

1. Start from the public PR, issues, and the pinned base. Do not invent users, logs, failure modes, or discovery history.
2. When facts, environment, and scope allow it, start the instruction from an earlier user action or surface symptom in the discovery timeline. Do not begin from an already-narrowed internal diagnosis or disclose the Golden approach.
3. The instruction and verifier must align. Hidden tests may vary inputs and boundaries, but must not add hidden functionality.
4. Judge observable behavior, not implementation shape. The verifier must not require Golden-only helpers, private fields, new parameter names, exact internal state sequences, or a specific algorithm.
5. Cover a real subsystem boundary. Unit tests and mocks may support diagnosis, but cannot be the only basis for reward.
6. Base must fail because the target behavior is wrong, and Oracle must pass. A base failure caused by a missing Golden helper or import has no scoring value.
7. Challenge the verifier with incomplete and hack patches, and use a behaviorally correct implementation with different internals as a positive control. The former must score 0; the latter must receive full reward.
8. Build from the PR base without leaking future source, dependencies, Git objects, or build caches. Keep a complete, self-contained Dockerfile and retain the canonical image.
9. Record limitations accurately. Deterministic model output or fault injection may replace unavailable components, but reconstructed data must not be presented as original production or CI evidence.
10. Evidence must report actual results. Test counts, hashes, image IDs, Harbor IDs, exit codes, and limitations must match the final artifacts.
11. Every blocking finding must be fixed, rejected with evidence, deferred with user approval, or genuinely blocked. Do not claim completion while a blocking finding remains unresolved.

## Workflow

1. Establish scope and read the complete local task, including `environment/`, `solution/`, `tests/`, and `validation/`. Record the branch, worktree, base commit, and candidate or instance identity.
2. Retrieve the complete relevant GitHub context: PRs, issues, all discussions, inline review, every PR commit, related history, predecessor proposals, and later boundary-changing fixes.
3. Review the instruction using that context. The solution and tests may inform the review, but Golden-specific implementation choices must not become instruction requirements.
4. Start the base image without `/tests`, `/solution`, or validation mounts. Reproduce the instruction and inspect what the evaluated agent can actually access.
5. Build a contract matrix and confirm that the instruction, base behavior, provenance, Oracle, and verifier describe the same problem.
6. Review the Dockerfile, final image, Git objects, dependency lock, and caches for answer leakage and future information.
7. Map every test to instruction behavior. Identify implementation coupling, hidden requirements, weak assertions, fake E2E, and special-caseable coverage.
8. During review, run one complete base and Oracle trial when feasible. Confirm the recorded failure boundary, then report before editing.
9. After approval, validate the review report and create a remediation matrix.
10. Resolve every instruction finding with the user, confirm instruction choices, and freeze the final behavior contract and E2E boundary.
11. In order, address Docker and environment issues, Oracle, tests and verifier, adversarial patches, and a correct alternative implementation. Do not enter the next stage while the current stage has a blocking finding, and do not weaken valid tests to make Oracle pass.
12. Build or reuse the final image and complete isolation audits. Then run first-pass validation, post-change review, five-round stability checks, and Harbor.
13. Refresh evidence from actual results. Completion requires every blocking finding to be closed and the staged diff to match the approved scope.

## Review output

Lead with the verdict, then report:

- provenance and discovery history with direct PR or issue links;
- whether the instruction can remain, or what it leaks, omits, or invents;
- verifier findings ordered by impact;
- current base and Oracle results;
- the real E2E boundary and its limitations;
- concrete changes required before the task is valid.

Do not claim completion while final Harbor evidence or required integrity checks are missing.

## Hardening output

When hardening is complete, report:

- the final status of every remediation-matrix finding;
- the final instruction-verifier contract and E2E boundary;
- actual base, Oracle, adversarial, alternative, and Harbor results;
- image ID, retained state, isolation audit, and known limitations;
- commit hash or the exact uncommitted state.
