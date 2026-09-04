# Task Review Rubric

A valid task presents a realistic problem, lets a strong solver reconstruct the
behavior-determining path in a normal development environment, and rewards the
observable contract without requiring the Oracle's implementation.

## 1. Fix the review revision and target

If the user requests a remote branch, commit, or worktree version of the skill,
create that worktree first, then reread the skill and this rubric from the
checked-out revision. Record:

- absolute skill worktree path, HEAD, and dirty state;
- SHA-256 for `SKILL.md` and every loaded reference or script when the skill
  worktree is dirty; never use HEAD alone to identify modified skill contents;
- absolute task worktree, branch, HEAD, and dirty state;
- task directory, name, repository, Base commit, and cutoff;
- candidate and instance identifiers when present;
- canonical image tag and image ID.

Do not mix rules from one revision with task artifacts from another. Existing
tracked and untracked changes belong to the user.

Read the task in a contract-first order:

1. Read `task.toml`, `instruction.md`, and the environment inputs.
2. Describe the user workflow and write the target semantic boundary without
   using the Oracle or verifier as the contract.
3. Read the solution, tests, controls, remediation records, evidence, and every
   other file that affects build, execution, scoring, or publication.

Read text, configuration, code, and patches completely. For large or binary
resources, record at least type, size, and hash and inspect content when it
affects the conclusion.

In a complete review, inspect the three gates in order even after finding an
early blocker. An early failure prevents approval of later gates, but later
read-only findings may still be reported as provisional. During hardening, fix
and freeze earlier gates before changing later ones.

## 2. Identity and repository contract

Check repository conventions and every relevant `task.toml` field.

- The directory uses semantic lowercase kebab-case and contains no PR, issue,
  candidate, or instance identifier.
- `[task].name` equals `ai-infra-bench/<task-directory>`.
- The description is non-empty and suitable as publication metadata.
- `base_commit` is a full immutable SHA and agrees with Docker, lock, image,
  and evidence records.
- `[agent].timeout_sec` is exactly `36000`.
- Workdir, network policy, CPU, memory, storage, build timeout, and verifier
  timeout are sufficient and internally consistent.
- CPU tasks request no GPUs or topology. GPU tasks use a supported topology and
  identify the actual accelerator.

Run the repository validator for repository-enforced constraints. Independently
enforce the 10-hour review policy even when the current repository validator
does not check it. The skill may add semantic findings that a schema validator
cannot detect.

## 3. Gate 1: Task-statement authenticity

### 3.1 Review the scenario independently

The task statement does not need to reproduce, summarize, or remain factually
identical to a PR, issue, incident, benchmark candidate, or patch. Those sources
are inspiration and technical context, not the contract.

Do not report a source mismatch merely because the task uses a different:

- prompt, model, dataset, business setting, or user goal;
- command sequence or deployment narrative;
- observable scenario produced by the same underlying mechanism;
- correct repair approach.

A source difference becomes a finding only when:

- the task explicitly claims to describe that historical event;
- the scenario uses an interface, configuration, or operation that does not
  exist or cannot work as described;
- the substituted story changes the behavior-determining mechanism;
- quoted observations cannot be produced by the corresponding real subsystem.

First ask who would perform the workflow, why they need the outcome, whether
the product interfaces exist, and whether the symptom and expectation make
sense. A new scenario needs no public provenance when it is realistic and
technically valid.

A task written in the first person is still a constructed scenario by default.
Phrases such as "our service" or "I observed" do not create a historical
provenance requirement. Treat a statement as historical only when it explicitly
identifies or cites an actual organization, person, incident, date, deployment,
measurement, or source record.

### 3.2 Classify evidence correctly

Use three evidence classes:

| Content | Required support |
|---|---|
| Historical claim, verbatim log, exact error, response, event sequence, or performance number | A source or captured execution record |
| Newly constructed business context, prompt, example input, or user goal | Realistic product semantics; no public incident required |
| Deterministic or mocked verifier input for an unavailable boundary | A documented substitution that preserves the target semantics |

Constructed scenario details must be realistic and valid under the product's
semantics. Historical claims and quoted observations require evidence.

Requests and commands must conform to the real interface at the pinned Base.
Quoted logs and outputs must be producible by the corresponding real subsystem;
do not assemble a log from lines that never coexist on that path. The complete
production deployment need not run when an unavailable boundary can be
substituted without changing the target mechanism. Record the substitution and
its limitations in validation evidence, not in the user-facing statement.

Code reading may establish interface and mechanism facts. Claims about actual
output, failure, ordering, or metrics require execution or an original captured
record.

### 3.3 Keep the statement in the user's perspective

The statement may describe the user's workflow, public inputs, observable
symptoms, expected outcome, and behavior that must remain intact. It must not
publish:

- curation, qualification, Harbor, Base/Oracle, or evidence details;
- mocks, fixtures, reduced drivers, missing-resource tradeoffs, or reproduction
  scripts;
- Oracle helpers, private fields, variable names, algorithm steps, or hidden
  case inventory;
- root-cause details that the user would not know and that disclose the repair.

### 3.4 Use sources to improve the task

After assessing the scenario on its own, use PRs, issues, discussions, and
related failures to understand the mechanism and identify a stronger task.
Consider additional values, shapes, batches, backends, lifecycle transitions,
repeated requests, recovery behavior, and state isolation when they follow from
the same real workflow. Do not combine unrelated bugs merely to add work.

Difficulty and interest are design questions, not provenance requirements.
Report an improvement proposal as non-blocking unless the current scenario is
unrealistic, trivial because it leaks the answer, or otherwise invalid.

### 3.5 Gate 1 blockers

Block when the scenario is not a plausible real workflow, uses nonexistent
interfaces, makes unsupported historical or quoted claims, cannot reach the
claimed mechanism, exposes private solution information, or withholds
information the solver cannot discover in the image.

Do not block because a constructed scenario differs from its source material.

## 4. Gate 2: Environment authenticity

### 4.1 Define the semantic boundary first

Write the smallest complete causal path:

```text
input or event -> behavior-determining subsystem or state transition
-> observable result
```

Classify every component mentioned by the story:

- **semantic component:** replacing it with contract-valid deterministic input
  could remove, reverse, or materially alter the Base-versus-Oracle distinction
  at the target boundary; it must run for real;
- **substitutable boundary:** it only produces valid input or consumes output
  without determining the behavior; a strong solver may replace it;
- **context only:** it makes the story realistic but is not required to execute
  the target path.

A GPU, model, HTTP service, CLI, or multi-node deployment is not automatically
semantic merely because the user story mentions it.

Examples:

- Run the real tokenizer when tokenization determines the outcome.
- Run the target device and runtime for a kernel, CUDA Graph, collective, DMA,
  or device-placement issue.
- Preserve real independent-process or node behavior when isolation or network
  timing determines the problem.
- A model forward pass may be replaced for parser, serialization, routing, or
  device-independent orchestration work.
- HTTP may be omitted when it is only a trigger, but must run when request,
  streaming, cancellation, or lifecycle semantics determine the result.

The image must let a strong solver construct missing inputs or substitutes from
the statement and normal source. It must not provide task-specific mock,
fixture, trace injector, or one-command reproducer scripts.

### 4.2 Required components and natural paths

The source, semantic dependencies, configuration, tools, and resources must be
usable under the agent user, workdir, resource, and network settings. Put real
components in their normal repository, cache, installation, or configuration
paths. Avoid task slugs, candidate IDs, and curator-oriented paths such as
`/assets`, `/reproducer`, `/fixtures`, `/solution`, or `/validation`.

### 4.3 Agent visibility and leak prevention

Judge leaks by actual agent-phase visibility:

| Artifact | Default visibility | Review treatment |
|---|---:|---|
| `instruction.md` | Agent-visible | Check for answer and test hints |
| Base repository, image filesystem, Git objects, caches, environment | Agent-visible | Check for future source and diagnosis aids |
| `task.toml` | Harness metadata, not agent-visible | Validate metadata; do not call it a solver leak |
| task `tests/`, `solution/`, and `validation/` | Verifier/CI-only | Ensure they never enter the agent image or layers |

If the actual harness differs, inspect it and update the matrix for the report.
Information is a solver leak only when it is visible during the agent phase and
materially reveals the answer, tests, or investigation path. Upstream project
tests that normally belong to the Base repository are not task verifier leaks.

### 4.4 Cutoff scope

Cutoff applies to:

- the target repository Base, retained history, and source objects;
- models, tokenizers, templates, data, and other supplied runtime resources;
- external service or protocol versions required by the task;
- runtime dependencies whose behavior affects the task's semantic boundary.

General benchmark infrastructure is cutoff-exempt unless its behavior is part
of the task. This includes base images, operating-system plumbing, Python, Rust,
uv, nextest, Harbor, compilers, build tools, and test tooling. Exempt components
must still be version- or digest-pinned sufficiently for reproducibility.

Do not report an exempt tool as post-cutoff merely because it was released
later. If a normally exempt component affects the target behavior—for example a
Python GC, compiler, driver, or runtime bug—classify it as a semantic dependency
and apply cutoff.

The repository must be checked out at the exact Base and stripped of remotes,
remote refs, tags, reflogs, fetch metadata, future reachable or unreachable
objects, packs, bundles, alternates, caches, or secondary checkouts that can
recover future source.

### 4.5 Image audit

Inspect the Dockerfile, build context, final filesystem, and image history. At a
minimum verify:

```bash
docker image inspect "$image_tag"
docker history --no-trunc "$image_tag"
```

Inside the image verify HEAD, remotes, remote refs, tags, reflogs, unreachable
objects, absence of the future fix, clean status, installed semantic dependency
versions, and import paths. Confirm task tests, solution, validation evidence,
reward logic, and task-specific helpers were never present in the agent image or
earlier layers.

### 4.6 Gate 2 blockers

Block when the semantic path cannot execute, a required component is missing or
unusable, an agent-visible artifact reveals the answer, future repository source
is recoverable, a cutoff-sensitive dependency is too new, or the environment
selects the wrong hardware semantics.

Do not block because a cutoff-exempt benchmark tool postdates the task, or
because a non-semantic production component is replaced outside the agent
image.

## 5. Gate 3: Verifier fairness

### 5.1 Map behavior, not source lines

Map every reward-affecting behavior and every collected case group to the task
contract. Record parameterized dimensions and counts. Source-line mapping is
optional and must not replace behavioral coverage.

Check both directions:

- every promised behavior has coverage;
- every reward-zeroing assertion follows from the statement or its unavoidable
  semantics.

Never repair a verifier mismatch by publishing Oracle helpers, private fields,
file paths, buffer layouts, call order, or algorithms in the task statement.

### 5.2 Behavioral boundary and E2E

Reward should enter through a public or stable subsystem boundary and observe
user-visible output, state, side effects, persistence, errors, or lifecycle.
Private helpers and intermediate state may aid diagnosis but must not determine
reward unless they are themselves the contract.

The E2E must execute the semantic boundary from section 4.1. A single literal
production deployment is not required. A composed E2E is valid when a real
target-boundary test and real downstream contract test together preserve
compatible payload and lifecycle semantics.

For each substitution, verify that it preserves the relevant state,
cardinality, ordering, timing class, and lifecycle. A component is required in
the target E2E when a contract-valid deterministic substitute could remove,
reverse, or materially alter the Base-versus-Oracle distinction. Preserve other
explicit output contracts through real downstream tests without automatically
pulling the entire production stack into the target E2E.

### 5.3 Regressions, hidden cases, and controls

Protect adjacent behavior that already works, especially results the statement
explicitly says must remain unchanged. Hidden cases should vary meaningful
contract dimensions such as values, length, shape, batch, mode, backend,
ordering, cold/warm state, repeated calls, recovery, and state isolation.

Adversarial controls should include plausible incomplete or hacked repairs:
special-casing examples, fixing only one path, returning constants, swallowing
errors, incorrect fallback, corrupting required output, or leaking state. At
least one semantically different correct alternative must receive reward 1 and
differ from the Oracle in algorithm, data representation, or repair location.
Patch similarity alone cannot establish semantic difference.

### 5.4 Challenge the Oracle independently

Derive the behavioral invariants before treating the Oracle as evidence. Create
at least one small contract-valid case not copied from the current tests or
Oracle conditions. The Oracle and a correct alternative should pass it. This is
a general challenge, not a requirement for any particular concurrency or state
test when those semantics are outside the task.

### 5.5 Base, Oracle, and result integrity

- Base receives reward 0 because of the target behavior, not an import error,
  missing Oracle symbol, invalid argument, dependency failure, or unrelated
  hardware.
- Oracle receives reward 1 at the same semantic boundary, runs all tests, and
  has zero skips and errors.
- Incorrect controls receive 0 and correct alternatives receive 1.
- The verifier must not read control patches or compare a solution with the
  Oracle. It may distinguish implementations only through behavior.

### 5.6 Gate 3 blockers

Block when required behavior is untested, reward depends on undisclosed or
Oracle-specific internals, no test executes the semantic boundary, a semantic
component is mocked away, Base or Oracle fails for an unrelated reason, an
incorrect implementation receives 1, or a correct alternative receives 0.

## 6. Priorities

- **P0:** false task premise, material agent-visible answer leakage, direct
  verifier bypass, or fabricated evidence.
- **P1:** wrong reward, Oracle contract violation, correct alternative rejected,
  Base failing for an unrelated reason, or the core semantic path being
  unreachable.
- **P2:** metadata, traceability, stale evidence, reproducibility, or publication
  completeness issue that must be resolved before release.
- **Non-blocking:** an improvement that does not affect authenticity,
  solvability, scoring fairness, or release integrity.

P0 and P1 findings require a reproducible counterexample, actual failure,
agent-visible leak, unreachable path, or explicit contract contradiction. Do not
promote an unsupported concern to a blocker.

## 7. Review report

Start with whether the task can be retained and whether it passes, needs
hardening, or is invalid. Report:

1. Realistic workflow, evidence classification, and any unsupported historical
   or quoted claims. Do not produce a source-difference table unless the task
   claims historical identity.
2. Semantic boundary, real components, substitutions, solver reconstruction
   path, cutoff-sensitive dependencies, agent visibility, and image isolation.
3. Behavior-to-case mapping, E2E composition, regressions, hidden coverage,
   independent Oracle challenge, and Base/Oracle/control results.
4. Findings with priorities, evidence, reproducible counterexamples, affected
   artifacts, and non-blocking proposals for making the task harder or more
   interesting.
