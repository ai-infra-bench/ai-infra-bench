# Task Review Rubric

Use this rubric to review ai-infra-bench tasks in this order: task statement, environment, verification. A task is valid only when all three hold: the task statement describes a real-world problem, the image resembles a normal development environment that could have been created on the cutoff date, and the verifier scores only the externally observable behavior promised by the task statement.

## 1. Fix the review target

Read all of the following in full:

- `task.toml` and `instruction.md`;
- the Dockerfile, image manifest, dependency inputs, lock outputs, runtime asset manifest, and build scripts under `environment/`;
- the solve script and Oracle patch under `solution/`;
- the runner, behavioral tests, E2E tests, and integrity checks under `tests/`;
- controls, the case manifest, the remediation matrix, and evidence under `validation/`;
- any other files at the task root that affect the build, execution, or publication of the task.

Read all text, configuration, code, and patches completely. For binaries and large resources, check at least the file type, size, and hash; inspect their contents when the review conclusion depends on them.

Record:

- the absolute worktree path, branch, HEAD, and dirty state;
- the task directory, `[task].name`, repository, Base commit, and cutoff;
- candidate/instance identifiers, canonical image tag, and image ID.

Existing tracked and untracked changes belong to the user. Do not clean them, overwrite them, or mix them into the target task. Focus only on the task currently under review.

Neither the solution nor the tests can define the contract on its own. The solution is only one reference implementation, and the tests are only the current scoring mechanism. The task statement, the real environment, and observable behavior define the contract together.

## 2. Check task identity and repository conventions first

### 2.1 Task name

- The directory name must be a semantic lowercase kebab-case name.
- The name must describe the workload, the user-visible symptom, or the capability being requested.
- PR, issue, candidate, and instance numbers and temporary identifiers are forbidden. Invalid examples include `vllm-pr-12345`, `issue-456`, and `candidate-223`.
- Use the repository's conventional project or workload prefix, followed by enough semantic detail to distinguish the task.
- `[task].name` must equal the repository namespace plus the directory name, for example `ai-infra-bench/<task-directory>`.
- `[task].description` must describe the user-visible problem or requested capability without revealing the solution.

An invalid task name or directory, or a mismatch between the directory and task name, is a publication blocker.

### 2.2 Directory layout and metadata

Compare the directory structure and metadata with the current CI, generator/template, and peer tasks. Check the schema, track, workload, subsystems, repository, source, publication metadata, required artifacts, and field names.

Check every relevant field in `task.toml`:

- `base_commit` is a full immutable SHA and matches the Dockerfile, manifests, lock data, and evidence.
- The cutoff and image digest match the actual artifacts.
- The agent timeout is exactly 10 hours: `[agent].timeout_sec = 36000`. Verifier and build timeouts, along with CPU, memory, storage, and OS resources, are sufficient to execute the contract.
- The workdir is an absolute path that looks like a real development path.
- Agent and environment network policies match unless the phases intentionally differ.
- The accelerator is a runner class supported by the current CI.
- CPU tasks do not declare a topology and request zero GPUs.
- GPU tasks use an allowed runner topology, `gpus` matches the topology, and `gpu_types` explicitly includes the actual accelerator.
- The accelerator and topology reflect the device semantics the correct behavior truly depends on, rather than simply copying the machine used in the original incident.

Incorrect metadata is blocking when it selects the wrong runner, resources, Base, or image.

## 3. Gate 1: Task-statement authenticity

### 3.1 Confirm that this is a real-world problem

A valid task statement must correspond to a workflow that occurs in the real world. These workflows generally fall into two categories:

- An ordinary user encounters unexpected behavior while deploying an inference service locally or in a private environment, training a model, invoking an agent or CLI, or processing inputs and outputs, or asks the infrastructure to support a reasonable capability.
- An infrastructure practitioner develops, integrates, analyzes, or debugs a system, including work involving performance analysis, behavior analysis, resource scheduling, caching, communication, parsing, serialization, or observability.

But not limited to this two categories, you can propose more interesting one.

Desired directions include GPU kernel engineering, model serving, distributed systems, training, profiling, agent-harness features, agent-harness bug fixes, and multi-agent design. Treat them as idea areas for realistic tasks, not as a closed taxonomy or a reason to combine unrelated work.

The task statement does not need to reproduce a public issue word for word, and no public incident report is required. It must not, however, be a collection of test conditions invented solely to match a patch. The reviewer should ask: who would actually perform these actions, why would they need this result, and do these product interfaces and workflows really exist? Does this read like an artificial exercise written around the Oracle patch rather than a real use case or requirement—something no one would actually do or say? If so, the task statement has a problem.

### 3.2 Establish evidence for every concrete detail

Create a fact table:

| Detail in the task statement | Type | How it was validated | Result in the pinned environment | Evidence location |
|---|---|---|---|---|
| Command or startup argument | Operation | Run the real parser/CLI | Exit status and resulting configuration | Run record |
| Request/body/header | Input | Pass it through the real request-conversion path | Actual internal request | Run record |
| Response/stream/log | Output | Produce it through the corresponding code path | Raw output and ordering | Run record |
| Model or tokenizer behavior | Component | Run the image's real tokenizer/template | Token/text result | Run record |
| Performance or resource figure | Metric | Measure repeatedly under fixed conditions | Raw samples and statistical method | Run record |

Requirements:

- Every command, configuration, request, input, output, error, log, metric, and sequence of events must be validated by actual execution. Code reading alone is not enough to conclude that something is theoretically possible.
- Logs must come from the real code path described by the task statement. Preserve their original format, fields, and values; do not assemble them by hand.
- Requests must be accepted by the real entry point, and their arguments and values must conform to the schema at that version.
- When deterministic input replaces an unavailable producer, the input must still pass through the first real target component and every relevant downstream stage.
- Record substitution methods, temporary drivers, and limitations in evidence, not in the task statement.
- The reviewer may build temporary machinery outside the container to validate facts, but reproduction or mock scripts must not be placed in the agent image.

"It is plausible that this could happen" is not evidence. Neither is "the code path looks as though it would produce this output."

### 3.3 Keep the task statement in the user's perspective

The task statement may include:

- What the user is doing.
- Which real public entry points, configurations, or inputs they use.
- What unexpected behavior or missing capability they observe.
- What result they expect.
- Which existing behavior must remain intact.
- What the user currently has, what their application is, and what actions they took.
- What assignment an expert developer has been given and the background behind it.
- What an expert developer is exploring experimentally and what part of the system they want to optimize.
- What the user wants to build, what it should be able to do, and how it should behave.
- ...

The task statement must not include:

- `reproducer`, `reproduction`, or `reduced reproduction`;
- `mock`, `fixture`, deterministic substitutes, or test-injection mechanisms;
- environmental tradeoffs such as "the image has no GPU or weights" or "CPU sandbox";
- the origin of supplied materials, qualification checks, Harbor, Base/Oracle, or curation conclusions;
- Oracle helpers, function names, variable names, private fields, algorithm steps, or the case inventory;
- internal requirements added only to make the existing verifier appear justified.

The task statement may include real logs and requests, but only as the user would see them. How they were obtained belongs in evidence.

### 3.4 Choose the right starting point

You may use the GitHub CLI to collect context for the task when such context exists. For example, if the task is based on a PR in a repository, use the CLI to retrieve the full PR context, including its title, body, all discussions, and related issues, so you understand the entire chain of events. If the CLI requires authentication, ask the user to sign in.

Break the problem into:

- A: the user's normal workflow;
- B: an observable failure or missing capability;
- C: a trace, internal localization, or numeric discrepancy discovered during investigation;
- D: the root cause and repair design.

Normally, start from A or B. Start from C only when an infrastructure practitioner's real work genuinely begins with a performance trace, behavioral analysis, or subsystem development. D must not appear in the task statement.

As a rule, the chain of events recovered from a PR should not simply become the task statement. The task statement may instead build a real scenario from the observed behavior, the bug itself, or the requested capability. Do not force it to mirror the same chain of events or tell the same story. If the scenario is too simple or superficial, consider how to make it more realistic, more interesting, and more difficult. The bug or requirement itself and the context you collected can guide that work. The goal is a scenario that is more realistic, more interesting, and harder.

The task statement also does not have to originate from a PR or issue; the only requirement is that the problem be real. When a task is based on a PR or issue, consider whether the same underlying bug is related to other bugs or produces additional user-visible behavior under the same operation. In that case, you may propose a more complex task statement. Its Oracle would no longer be the PR patch alone, but a solution to a more realistic and more complex problem. Such proposals are encouraged when the combined scenario is more realistic and meaningfully deeper. Do not propose combining unrelated bugs or requirements merely to add more work; that produces a bundle of separate tasks, not the kind of deeper task we want. This is optional. Raise the proposal only when you find a particularly suitable or interesting opportunity.

### 3.6 Task-statement gate

Any failure to follow the principles above is blocking. Examples include:

- The scenario is not a realistic user or infrastructure workflow.
- Any concrete technical detail has not been validated or does not hold in the pinned environment.
- Logs, requests, or outputs were assembled by hand or came from the wrong code path.
- The task statement reveals curation methods, mocks/reproducers, environmental limitations, or the solution.
- The agent needs private information that the task statement does not provide and that cannot be discovered in the environment before it can begin.

Assign P0, P1, or P2. Do not review the environment until the task statement passes and is frozen.

## 4. Gate 2: Environment authenticity

### 4.1 Build a list of required components

Derive the list from the frozen task statement rather than reasoning backward from the existing Dockerfile:

| Object or operation in the task statement | What the image must contain | Boundary that may be omitted | How to check it |
|---|---|---|---|
| Named tokenizer/template | The real tokenizer, config, template, and invocation dependencies | Model weights unrelated to the bug | Actually tokenize/render |
| Named agent/CLI | The real executable and its dependencies | Unrelated remote services | Actually start and invoke it |
| Parser/stream bug | The real parser and upstream/downstream conversions | Model forward pass | Drive the path with valid generated output |
| Kernel/collective bug | The target device, runtime, kernel/backend | Unrelated model layers | Execute on the target device |

Many other cases will not appear in this table. The governing principle is that once the task statement has been fixed, the environment must provide the tools, packages, components, and other resources it requires to test the solver's ability. If the task statement says the user built an application, the image should contain that application's repository. If the user says they were running the OpenCode agent when the problem occurred, the image should contain OpenCode. Build an environment that resembles the user's real development environment, but never include scripts that reproduce or mock the bug.

A component must do more than exist as a file. It must work under the agent's user, workdir, network, and resource constraints.

### 4.2 Paths and environment must look natural

The image should resemble an ordinary user development environment:

- The repository is in the project's normal working directory.
- Dependencies are installed through the project's usual environment or system mechanism.
- Tokenizers, model configurations, CLIs, and tools use their normal cache, configuration, or installation paths.
- The username, HOME, workdir, PATH, environment variables, and file permissions are reasonable.
- Commands in the task statement map directly to those real paths.

Reject names and paths that reveal curation, including:

- a task slug or candidate/instance ID in a path;
- artificial resource directories such as `/assets`, `/task-assets`, `/reproducer`, `/fixtures`, or `/golden`;
- environment variables or labels that suggest tests, the solution, the Oracle, reward logic, or validation;
- a README, shell history, cache, or temporary file that reveals the direction of the fix.

When an external component must be preinstalled, place it where that component would normally live in a development environment, and retain verifiable source and version records. Do not expose it through curator-oriented naming.

### 4.3 Forbid artifacts that make diagnosis easier

The agent image and all image layers must not contain:

- tests, hidden tests, the solution, the Oracle patch, controls, evidence, reward logic, or validation artifacts;
- task-specific reproduction scripts, mocks, fixture generators, trace injectors, or one-command trigger scripts;
- answer comments, the fixing commit, future source, or a pre-applied patch;
- any of the above copied in during the build and deleted later.

A sufficiently capable agent can write temporary programs from the task statement and source. Preinstalling those programs reveals the investigation path and lowers the difficulty.

### 4.4 Audit the cutoff strictly

The image must be defensible as an environment that could have been installed on the cutoff date. Audit:

- the repository Base commit and retained history;
- the base image digest;
- the OS repository snapshot and system packages;
- Python wheels/sdists, npm packages, Rust crates/toolchains, and Java/Go dependencies;
- external binaries, CLIs, agents, compilers, drivers, and runtimes;
- tokenizers, chat templates, model configurations, metadata, media, and other runtime assets;
- build caches, wheel caches, source caches, and pregenerated artifacts.

Record an immutable version or digest for each item and prove that it was released no later than the cutoff. The following are forbidden:

- `latest`, floating branches, unpinned URLs, or newly resolved versions;
- packages, binaries, model resources, or backports released after the cutoff, even if used only for testing;
- versions introduced after the cutoff under the label of an override;
- a future wheel shadowing the Base worktree;
- additional components with no recorded source, version, or date.

The repository must be checked out at the exact Base and stripped of:

- Git remotes and remote refs;
- tags, reflogs, `FETCH_HEAD`, `ORIG_HEAD`, and fetch metadata;
- reachable or unreachable objects newer than the cutoff or Base;
- packs, bundles, alternates, caches, or a second checkout that can restore a future commit.

Keep normal history from before the Base when it helps investigation. Do not use future objects, and do not make the repository excessively shallow in a way that artificially raises or lowers the difficulty.

### 4.5 Solvability and the real semantic boundary

Start the canonical image with the same user, workdir, CPU, memory, storage, GPU, and network settings used during the agent phase. Do not mount tests, the solution, or validation artifacts. Confirm that:

- the agent can find the source and real components named by the task statement;
- the Base reaches the target behavior before any missing dependency, invalid argument, wrong backend, or resource failure blocks it;
- the agent can construct input and observe the symptom independently;
- the subsystem being fixed actually executes;
- the agent can substitute unavailable boundaries without changing the semantics of the bug.

The fact that the original problem involved a GPU, model, HTTP service, or multiple nodes does not automatically require the image to reproduce the full deployment:

- A model forward pass may be replaced for parser, serialization, routing, or device-independent orchestration issues.
- Tokenizer issues must execute the real tokenizer.
- When HTTP lifecycle semantics determine the result, the test must use the real HTTP/ASGI/SDK path.
- When a kernel, CUDA Graph, collective, DMA, device placement, or backend selection determines the result, the test must use the target hardware and runtime.
- When isolation, placement, or network timing determines the problem, preserve the real independent-process or node semantics.

### 4.6 Audit the image and its layers

Inspect the Dockerfile, build context, final filesystem, and image history. At minimum, run:

```bash
docker image inspect "$image_tag"
docker history --no-trunc "$image_tag"
```

Inside the container, check:

```bash
git rev-parse HEAD
git remote -v
git for-each-ref --format='%(refname)' refs/remotes refs/tags
git reflog show --all
git fsck --full --no-reflogs --unreachable --no-progress
git cat-file -e "$future_sha^{commit}"
```

The final command must fail. Also verify that installed packages match the lock, imports resolve to the Base worktree, editable-install metadata does not point to another source tree, and earlier image layers never contained forbidden artifacts.

### 4.7 Environment gate

Any failure to follow the principles above is blocking. Examples include:

- A real component required by the task statement is missing or cannot be used under agent conditions.
- A path, filename, environment variable, label, or cache reveals the task identity, curated resources, or the answer.
- The image contains reproduction/mock scripts or test artifacts.
- The Base cannot reach the target path before an unrelated failure.
- The repository, any dependency, or any additional component is newer than the cutoff, or its source, version, or date cannot be verified.
- A future Git object, remote, or recoverable future source remains available.

Assign a P0, P1, or P2 priority. Do not review the verifier until the environment passes.

## 5. Gate 3: Align the verifier with the task statement

The principles are as follows. First, the verifier must be independent of the details of the Oracle implementation. It must never depend on Oracle-specific implementation details such as functions, variable names, or intermediate algorithm state. Otherwise, other correct solutions may fail simply because the task does not require a particular function or Oracle variable. The verifier must align with the task statement, not the other way around. Never address this problem by adding required function names, algorithm details, or similar constraints to the task statement. Change the verifier instead. Second, the verifier must use behavioral tests rather than unit tests: it should use enough behavior-level cases related to the task to determine whether the described problem or requirement has been implemented correctly. Third, the verifier must include a real end-to-end test. Environmental limits may make a fully literal E2E impossible—for example, a CPU sandbox may not have model weights or a GPU—so the E2E may use mocks. Even then, it must remain as realistic as possible. To test whether a parser bug has been fixed without model weights or a GPU, for example, the test may mock the model's generated text while keeping every other part of the path real, including a real downstream agent such as OpenCode making the request. Reviewers must determine how the E2E can be made more realistic under the available constraints. Fourth, the verifier must include regression tests that protect existing behavior that the change might break. Fifth, the verifier must include hidden tests rather than testing only the cases described in the task statement, which could be special-cased.

### 5.1 Check alignment in both directions

Every requirement and behavior in the task statement must be tested by the verifier.

For every verifier test—especially every test that can cause `reward = 0`—ask whether the task statement contains the corresponding requirement. If it does not, determine whether that requirement follows directly from the task statement. Imagine the strongest human expert solving the task: would they reasonably understand that the verifier's requirement must be satisfied? If so, the test may remain. Otherwise, it is misaligned and should be removed from the verifier.

### 5.2 The verifier must align with the task statement

When tests depend on function names, algorithms, or internal structures that the task statement does not promise, change the tests. Do not "fix" this by:

- requiring the Oracle helper in the task statement;
- publishing variable names, private fields, file paths, or intermediate state in the task statement;
- prescribing call order, buffer structure, cache keys, or a specific algorithm in the task statement;
- copying the hidden-case inventory into the task statement.

The task statement defines the user contract, and the verifier observes that contract. The verifier cannot dictate how the user must implement it.

### 5.3 Behavioral tests, not Oracle unit tests

Reward must be determined by real external behavior:

- Enter through a public/stable API, CLI, service, protocol, or stable subsystem boundary that already existed before the fix.
- Observe user-visible output, state, side effects, persistence, errors, or lifecycle behavior.
- Small unit tests may help localize problems and speed up feedback, but private helpers, fields, intermediate structures, and call details must not determine reward.
- Do not require a particular file to be changed, parse patch text or ASTs, or compare the implementation with the Oracle.
- Correct implementations may use different algorithms, data representations, and repair locations.

Unless they are themselves part of the public contract, none of the following may affect reward: helper/class/method/parameter names, variable and field names, file layout, private maps/cursors/counters, specific retries/locks/buffers, or unrelated call counts and internal ordering.

### 5.4 A sufficiently realistic E2E

Every task must include at least one E2E that genuinely traverses the user workflow. When the environment truly lacks model weights, a GPU, or an external service, the test may replace only that unavailable producer or boundary. The substituted data must be valid input to the next real component, and every other part of the path relevant to the task's outcome must run real code.

For example, a parser task may substitute deterministic generated text for model execution, but it should still run the real tokenizer/template, serving conversion, parser, stream aggregation, and any real downstream agent or CLI named by the task statement. If the task statement says OpenCode consumes the result, the E2E should run real OpenCode rather than a hand-written fake consumer.

Map the E2E path one stage at a time:

```text
real user entry point -> real upstream conversion -> [the only allowed substitution boundary]
-> real target subsystem -> real downstream conversion -> real user observation
```

For each stage, ask:

- Can this stage run for real under the image constraints?
- If it is currently skipped, is it genuinely irrelevant to the bug?
- Can a project-provided entry point replace a test-only helper?
- Can the test retain real processes, ASGI, streaming, protocols, a CLI, or an agent while replacing only the model forward pass?
- Do the Base and Oracle follow exactly the same path?

The E2E must validate the final task outcome and behavior that must remain intact, not just an internal parser return value. Include at least one input, ordering, state, or repeated-request scenario that is not disclosed verbatim in the task statement.

### 5.5 Regression, negative, and hidden tests

Regression tests protect behavior adjacent to the fix that already works on the Base, including output the task statement explicitly says must remain unchanged. It is not enough to prove only that the primary failure disappears.

Negative tests cover malformed, unsupported, partial, or persistently failing input, failure recovery, empty results, exception propagation, and forbidden fallbacks. A fix must not pass by swallowing exceptions, returning a constant, or reporting unconditional success.

Hidden tests vary dimensions within the contract: values, length, batch, chunking, ordering, mode, language, backend, layout, concurrency, cold/warm state, first/repeated calls, end-of-stream flush, and recovery. They must not merely replace a task-statement fixture with an equivalent fixture, and they must not test undisclosed functionality.

For delimiters, markers, frames, prefixes, or partial records, relevant cases generally include an unterminated prefix, similar prefixes in ordinary text, a complete marker split across deltas, end-of-stream flushing, consecutive requests, and state isolation.

### 5.6 Base, Oracle, and controls

Base:

- receives reward 0;
- fails because of the target behavior in the task statement;
- does not fail primarily because of an ImportError, a missing Oracle symbol, a missing dependency, an invalid argument, or unrelated hardware;
- can still execute the normal regression paths.

Oracle:

- receives reward 1 at the same entry point and boundary;
- actually runs every behavioral, E2E, regression, negative, and hidden test;
- has zero skips and zero errors;
- does not modify tests, the verifier, or reward logic;
- does not add behavior outside the task statement.

Controls:

- Adversarial controls should cover realistic incomplete strategies such as special-casing public examples, fixing only some paths, returning constant output, swallowing exceptions, using an incorrect fallback, or leaking state after the first successful call. They should receive reward 0.
- At least one alternative control must use a semantically different correct implementation, preferably based on a validated workaround, revert, rejected approach, or independent design. It should receive reward 1.
- The alternative must not merely rename an Oracle helper. It must differ in at least one of algorithm, data representation, or repair location.
- The verifier must not read control patches. It may distinguish them only through behavior.

### 5.7 Verifier gate

Any failure to follow the principles above is blocking. Examples include:

- Behavior explicitly required by the task statement is not tested.
- Reward depends on functionality outside the task statement or on Oracle implementation details.
- The primary tests call only private helpers or observe intermediate state.
- No E2E reaches the real target subsystem and required downstream components.
- A component that could run for real is mocked without justification, making the path unrealistic.
- Required regression or hidden tests are missing.
- An implementation that violates the task statement receives reward 1, or a behaviorally correct alternative receives reward 0.
- The Base fails for an unrelated reason, or the Oracle passes by skipping tests.

Assign a P0, P1, or P2 priority.

## 6. Review report format

Start with a conclusion: whether the task passes review, needs hardening, or is currently invalid. Then report by gate:

1. Task statement: the real workflow, evidence for each concrete fact, fabrication or leakage risks, and whether there is a better proposal.
2. Environment: required components, realistic paths, cutoff, Git/dependency/image-layer isolation, and task metadata.
3. Verification: bidirectional contract mapping, behavioral entry points, the E2E path, regressions, hidden tests, and Base/Oracle/controls.
