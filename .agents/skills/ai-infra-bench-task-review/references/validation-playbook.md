# Hardening and Validation Workflow

Use this workflow only after the user authorizes changes. The review rubric remains the source of truth; this file explains only how to carry out an approved review and does not repeat the full rubric.

Work through the same three gates in order: task statement, environment, verifier. Do not use a change to a later gate to hide a problem in an earlier one.

## 1. Confirm the target and scope

- Continue from the reviewed version in the same isolated worktree.
- Preserve unrelated tracked and untracked changes.
- Turn the review findings into a short working checklist. A separate remediation matrix is unnecessary unless the repository requires one.
- Before changing task behavior, confirm that the task name, directory, `task.toml`, accelerator, topology, resources, and repository conventions are correct.

Commit, push, or create a PR only with explicit user authorization.

## 2. Fix the three gates in order

### 2.1 Task statement

- This is the part that requires the closest alignment with the user. Have as many rounds of discussion as needed to help the user understand the nature of the problem, point out issues in the current task statement, recommend potentially better task statements or ideas, and discuss what kind of scenario they want. Keep aligning with the user and exploring better possibilities. To reach a better result, the entire task may change, including the Oracle, environment, and verifier. The task statement itself matters most.
- Fix scenarios that do not belong to a real user or infrastructure workflow.
- Validate every concrete command, request, configuration, log, output, metric, and sequence of events through actual execution in the pinned environment.
- Keep only the user's context, observable behavior, expected outcome, and behavior that must remain intact.
- Remove curation details, mocks, reproducers, environmental tradeoffs, test hints, and Oracle implementation details.
- Use PR or issue context as background and inspiration rather than copying its story into the task statement.
- If a stronger related scenario would make the problem more realistic and meaningfully deeper, present it to the user as a proposal before expanding the task. Do not combine unrelated bugs, unrelated features, or completely unrelated material merely to add more work.

Freeze the task statement before changing the environment or verifier. If the verifier does not match the task statement, change the verifier.

### 2.2 Environment

- Review the environment again according to the review rubric after the task statement has been frozen, and resolve every issue you find.
- Add the real tokenizer, CLI, agent, source tree, configuration, or other component named by the workflow. Omit only boundaries whose semantics do not determine the problem.
- Put components in the paths they would normally use in a real development environment.
- Remove task-specific reproduction or mock scripts and every test, solution, validation, answer, and future-source artifact from the image and all its layers.
- Confirm that the repository, base image, packages, binaries, toolchains, model metadata, tokenizers, and runtime assets all existed before the cutoff and are pinned to verifiable versions or digests.
- Remove remotes, refs, reflogs, fetch metadata, and reachable or unreachable future Git objects.
- Ensure that `task.toml`, the image manifest, resources, workdir, network policy, accelerator, and topology match the actual environment.

Rebuild the image when the Dockerfile, dependencies, runtime assets, resources, or network configuration changes. Otherwise, reuse the image that has already been audited.

Start the final image under the same conditions used during the agent phase, without mounting tests, the solution, or validation artifacts. Confirm that every required component works and that the Base reaches the target behavior before any unrelated failure occurs.

### 2.3 Oracle and verifier

Once the task statement and environment have been confirmed, review the Oracle and verifier again using the review rubric if either the task statement or the environment changed. Then resolve every issue you find:

- Treat the Oracle only as one reference implementation, not as a code structure that must be followed. If the task statement changes, the Oracle may need to change as well.
- Make the verifier observe behavior through an existing public or stable boundary.
- Map every task-statement requirement to a test, and map every reward-affecting test back to the task statement.
- Remove checks for Oracle helpers, variable names, private state, file layout, AST structure, specific algorithms, or other implementation details.
- Include a real E2E that executes the target subsystem and every relevant downstream component for real. Substitute only a boundary that is unavailable in the environment and whose semantics do not determine the bug.
- Make the E2E as realistic as the environment allows. Prefer real project entry points, processes, ASGI/HTTP/SDK paths, streaming lifecycle, CLIs, and downstream agents over test-only helpers.
- Add regression tests for relevant behavior that currently works, and hidden tests that vary inputs or state within the task-statement contract.
- Add adversarial controls for plausible incomplete or hacked implementations, and at least one semantically different correct alternative.
- And so on.

Run the Base and Oracle through the same entry point and E2E path. The Base must fail because of the target behavior. The Oracle must pass without skips or unrelated errors. Incorrect controls must receive reward 0, and the correct alternative must receive reward 1.

## 3. Validate and freeze

Before the final run, check:

- task structure, syntax, metadata, hashes, test collection, and patch applicability;
- whether the facts in the task statement match actual behavior;
- required environment components and their normal paths;
- cutoff, Git object, image layer, and hidden-artifact isolation;
- Base, Oracle, E2E, regression, hidden, adversarial, and alternative results.

Fix each failure at the gate where it originates, then rerun the affected validation. Once the task statement, environment, Oracle, verifier, and controls are stable, freeze all executable artifacts.

After the freeze:

- Run the Base and Oracle stability trials required by the repository.
- Add appropriate stress runs for race, asynchronous, or nondeterministic tasks.
- Run the final Harbor Oracle trial with tests, the solution, and validation artifacts hidden during the agent phase.
- Confirm that the reward matches expectations, there are zero errored trials, and every required test layer succeeds.

If the task contract, execution configuration, environment, Oracle, tests, or verifier changes afterward, the affected final results are invalid and the corresponding validation must be rerun.

## 4. Keep evidence concise

Evidence exists to substantiate the final conclusions, not to serve as a work log for the hardening process. Record only what is needed to establish:

- the final task, Base, cutoff, and image identity;
- actual validation of concrete facts in the task statement;
- cutoff and isolation results for the repository and required components;
- Base, Oracle, E2E, adversarial-control, and alternative-control results;
- the real E2E path, the substituted boundary, and why that substitution does not change the target behavior;
- final stability and Harbor identifiers, reward, errors, and input checksum;
- hashes needed to tie the results to the executable artifacts.

Unless the repository schema or a specific finding requires it, do not repeat the rubric, keep planning notes, list every command, or maintain large status tables. Retain complete raw logs only when they are necessary to substantiate a conclusion; otherwise, keep the relevant output and result.

The Harbor input checksum identifies the task snapshot at the start of the trial. Writing evidence afterward may change the directory checksum. For an evidence-only change, validate only the evidence and artifact hashes; do not rerun behavioral tests or Harbor. After changing an executable artifact, rerun the affected validation.

## 5. Completion and handoff

The task is complete only when:

- all three review gates pass;
- no blocking finding remains unresolved;
- the task name, repository structure, and `task.toml` are valid;
- the final image passes cutoff and isolation checks;
- Base, Oracle, E2E, regression, hidden tests, and controls behave as expected;
- stability and Harbor validation pass;
- evidence matches the final artifacts and actual run results.

Before an authorized commit or PR, stage only the approved task paths, inspect the staged diff, and confirm that it contains no unrelated files. Report the exact uncommitted, commit, or PR state together with the final validation results.
