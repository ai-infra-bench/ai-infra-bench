# Hardening and Validation Playbook

Use this playbook only after the user authorizes changes. Its inputs are the review report and the current task revision. Its outputs are a task with closed findings, actual validation evidence, and an accurate commit state.

Execute stages in order. Do not enter the next stage while the current stage has an unresolved blocking finding.

## 1. Validate the report and create a remediation matrix

Read in full:

- the review report, including conclusions added in the conversation;
- the current `SKILL.md`, [review rubric](review-rubric.md), and this playbook;
- the current task instruction, environment, solution, tests, validation files, and metadata;
- PRs, issues, commits, logs, and run results cited by the report.

Confirm that the report still applies:

- check the current branch and `git status --short`;
- compare the task base commit, image ID, instruction hash, and test hash;
- check whether the user changed the instruction, Dockerfile, Oracle, tests, or scope after the report;
- spot-check base and Oracle observations from the report;
- verify primary-source links and factual claims;
- rerun affected review-rubric sections when material changes exist.

The report is not unquestionable. If new evidence disproves a finding, mark it rejected and record why. Do not change a correct task merely to comply with a stale report.

Split each finding into a separate row:

| ID | Severity | Finding and evidence | Contract impact | User approved? | Planned change | Validation | Status |
|---|---|---|---|---|---|---|---|

Use at least these severities:

- blocking: would make the instruction false, environment unusable, verifier incorrect, E2E invalid, answers exposed, or evidence inaccurate;
- non-blocking: improves readability, coverage, or maintainability without determining task validity;
- suggestion: optional improvement that must not expand scope without approval.

Use pending, in progress, fixed, rejected, deferred, and blocked statuses. Deferred findings require explicit user approval and a recorded residual risk. Add new blocking findings discovered during implementation. Obtain user approval before materially expanding scope.

Every finding needs an observable completion condition. "Code changed" and "test added" are not completion conditions. State which behavior, E2E path, isolation check, or evidence item proves closure.

Protect the worktree throughout: preserve unrelated tracked and untracked changes, use `apply_patch`, handle one task at a time unless the user requests a batch, do not commit before approval, and do not use destructive Git cleanup.

## 2. Resolve every instruction issue first

The instruction is the common input to the environment, Oracle, and verifier. Close all instruction findings before changing later layers.

### 2.1 Discuss choices with the user

An instruction may have several valid starting points, perspectives, or reproduction forms. Explain choices and tradeoffs, such as:

- beginning from the user action, first failure, or developer trace;
- using authentic logs, a reduced reproduction, or an A/B comparison;
- writing from a user, operator, or developer perspective;
- which regression boundaries must be explicit;
- which resource limitations belong in the instruction;
- which details leak the root cause or make the task too easy.

Follow choices the user has already made. If a missing decision would materially change difficulty, scope, or the verifier contract, discuss it before finalizing instead of assuming.

### 2.2 Correct the instruction

Use GitHub provenance and the review report to:

- correct fabricated, inaccurate, or unverifiable facts;
- use the earliest reasonable starting point;
- retain symptoms, requests, logs, traces, or comparisons needed by the agent;
- remove Golden root causes, helpers, fields, parameters, and algorithm hints;
- state behavior to change, regressions to preserve, and negative cases that must still fail;
- ensure the instruction requests implementation or a fix rather than only inspection or explanation;
- avoid promises the verifier will not check;
- vary expression across a task set without weakening `must`, return values, or error boundaries.

### 2.3 Freeze the instruction contract

After finalizing the instruction, record:

- surface problem and starting point;
- public behavior that must change;
- regressions that must remain correct;
- negative behavior that must still fail;
- API, mode, backend, language, layout, parallel, and other scope;
- agent reproduction path;
- real E2E entrypoint;
- boundaries where deterministic replacement is allowed;
- known limitations.

Draft both instruction → verifier and verifier → instruction mappings. Define expected verification without letting existing tests narrow the contract.

### 2.4 Instruction gate

Before entering the environment stage:

- every blocking instruction finding is fixed or rejected with evidence;
- every user decision needed for the instruction is resolved;
- instruction facts have primary-source or reproducible support;
- behavior scope, regressions, and negative cases are unambiguous;
- the remediation matrix is current.

### 2.5 Instruction-only exception

Strictly equivalent wording changes with no executable changes do not require another five-round base and Oracle run. Compare semantics item by item and update the instruction hash. The old Harbor task checksum no longer identifies the final task; run one final Harbor Oracle if publication requires checksum identity.

Any wording change to scope, modality, return values, failure conditions, or regression boundaries is not instruction-only and requires affected behavior validation.

## 3. Resolve Docker and environment issues from the instruction

Use the finalized instruction to ensure that the base image contains everything the agent needs to investigate and fix the problem. Environment issues come before Oracle and tests; otherwise later work may validate an unusable setup.

### 3.1 Add missing reproduction resources

Check and add required:

- Python and system dependencies;
- compilers, build tools, and runtime libraries;
- tokenizer, chat template, and model configuration metadata;
- audio, video, or other public fixtures;
- minimal real metadata or deterministic input that can replace large model weights;
- Ray, filesystem, IPC, port, or other local service conditions;
- CPU, memory, storage, GPU, and network resources required by the task.

Pin runtime assets by immutable revision or SHA-256 and record licenses and attribution. Do not download model tensors when metadata is sufficient. When private prompts, weights, or hardware are unavailable, use only a reduced boundary accepted by the instruction and report.

### 3.2 Fix future-information and hack risks

The Dockerfile and image must:

- fetch and check out the exact base commit;
- preserve useful history only through base;
- remove remotes, remote refs, tags, reflogs, fetch metadata, and unreachable future objects;
- use an empty build context so no layer contains task tests, solution, validation, evidence, or curator files;
- lock dependencies to the task cutoff and pin base-image digests;
- namespace source-derived caches by full base SHA and lock digest;
- avoid untrusted remote caches;
- import vLLM from the base worktree without a future vLLM wheel;
- avoid proxy settings or credentials in the Dockerfile when the host provides TUN networking;
- keep answers out of image environment variables, labels, history, and runtime assets.

### 3.3 Decide whether to build

- Build a new canonical image when the Dockerfile, lock, runtime assets, system dependencies, or agent resources change.
- Reuse the existing canonical image when only the instruction, solution, tests, or validation changes.
- Always build with an empty context and retain the canonical tag.
- Synchronize task metadata and the image manifest after a build.
- At this stage, confirm at least that the image starts and the agent can execute the instruction reproduction path.

### 3.4 Environment gate

Before entering the Oracle stage:

- the agent phase mounts no `/tests`, `/solution`, or validation files;
- all commands, dependencies, resources, and paths required by the instruction exist;
- base reaches the target boundary before unrelated environment failures;
- obvious answer paths and known future commits are unavailable;
- the new image is retained, or the reused image ID is confirmed;
- every blocking environment finding is closed.

Perform the full layer, Git, dependency, and cache isolation audit on the final image in section 7.

## 4. Correct Oracle contract violations

After the environment works, correct Oracle against the instruction contract. Oracle is a reference implementation, not a structural template for tests.

Oracle must:

- satisfy every instruction behavior;
- solve the problem through an entrypoint aligned with the instruction;
- preserve controls listed by the report;
- keep invalid inputs and persistent failures failing as required;
- avoid dependencies on tests, validation patches, or hidden data;
- avoid copying implementation from future commits, packages, or caches;
- apply to the canonical base worktree;
- use a solve script that does not modify tests, the verifier, or reward.

Compare base and Oracle through the instruction reproduction path and confirm that Oracle solves the same problem. Existing diagnostic tests may run here, but do not distort Oracle to preserve invalid old tests.

### Oracle gate

Before entering the tests stage:

- the Oracle patch applies and parses;
- the primary instruction behavior is correct under Oracle;
- explicit regression and negative behavior show no obvious breakage;
- every blocking Oracle finding is closed.

## 5. Correct tests and the verifier

Rewrite tests from the instruction contract and correct Oracle behavior. Do not copy Oracle structure into test requirements.

### 5.1 Implementation independence

The verifier:

- enters through public APIs or stable subsystem boundaries that existed before the fix;
- does not require Golden helpers, private fields, new parameter names, variable names, file names, AST shapes, or algorithms;
- does not require the agent to modify the same files as Golden;
- avoids exact internal timing and call-count assertions unrelated to public behavior;
- accepts correct implementations with different structures.

Do not delete valid behavior tests merely to make Oracle pass. Fix Oracle when it violates the contract; fix tests when they violate the contract.

### 5.2 Test layers

Use the layers the task needs:

1. fast unit or functional tests;
2. a hidden behavior matrix with unpublished inputs and edge cases;
3. real subsystem E2E from the instruction's public entrypoint;
4. regression and negative tests;
5. collection and reward integrity checks.

E2E must not only replay the instruction example. Add at least one unpublished input, mode, length, ordering, or repeated scenario. The target scheduler, parser, decoder, connector, channel, filesystem, kernel, or transport must run for real. Mocks and deterministic inputs may replace only unavailable components outside the target boundary.

### 5.3 Hidden, regression, and negative coverage

Hide inputs, not functionality. Vary values, lengths, ordering, modes, languages, layouts, concurrency, error types, and repetitions to prevent special-casing.

Regression tests cover paths already correct in base. Negative tests ensure missing, malformed, unsupported, and persistently corrupted inputs still fail. Swallowed exceptions, empty results, unconditional success, and forbidden fallback must not earn reward.

### 5.4 Integrity

Check at least:

- exact case count;
- unique case names;
- zero failures;
- zero errors;
- zero skips;
- every required unit, behavior, E2E, and integrity layer affects reward.

### Tests gate

Before creating control patches:

- instruction–verifier mapping is complete in both directions;
- base fails for target behavior rather than a missing Golden symbol;
- Oracle passes every required layer;
- E2E reaches the real target boundary;
- regression and negative behavior are covered;
- every blocking tests or verifier finding is closed.

## 6. Create adversarial patches and a correct alternative implementation

Use review findings to create distinct incomplete solutions:

- special-case only the instruction example;
- fix only one API, mode, process, language, or direction;
- handle the first call but leak state later;
- always succeed, return a fixed result, or swallow errors;
- omit one cache group, block, worker, rank, or completion;
- fall back to a forbidden backend;
- fix the target example while breaking a regression from the report.

An adversarial patch must apply and run, then score 0 because of its planned behavioral defect. Do not create fake adversarial failures through syntax errors, import errors, or patch-application failure.

Create at least one behaviorally correct alternative implementation. It should deliberately change Golden's internal names, file decomposition, helper structure, or algorithm while satisfying the full contract and scoring 1. If it fails because of implementation shape, return to the tests stage and fix the verifier.

The verifier must not read validation patches; it must detect defects through behavior.

## 7. Build or reuse the final image and complete isolation audits

After Oracle, tests, and controls are final, select the final canonical image:

- rebuild from the final Dockerfile when environment files changed;
- reuse the confirmed canonical image when environment files did not change;
- ensure task metadata image digest equals the actual image ID;
- verify the image-manifest and dependency-lock hashes;
- retain the canonical image after Harbor.

Run the review rubric's Docker, image, and anti-hack checks:

- HEAD, branch, remotes, tags, reflogs, and unreachable objects;
- known future commits fail `git cat-file` lookup;
- installed dependencies match the lock and cutoff;
- vLLM imports from the base worktree;
- `/tests`, `/solution`, validation, evidence, and reward are absent;
- image layers contain no deleted but recoverable answers;
- runtime network policy is correct;
- warm-cache and initial-build digests match.

If isolation fails, return to the environment stage. Do not proceed to stability validation.

## 8. Run static checks, first-pass validation, and post-change review

### 8.1 Static checks

- Validate Python, shell, JSON, TOML, and patch syntax.
- Run `git diff --check`.
- Check executable bits.
- Match expected test count to the integrity checker.
- Confirm Oracle and control patches apply to their intended baselines.
- Confirm image digest matches the retained image.

### 8.2 First base run

Run the complete verifier and confirm:

- reward is 0;
- failures come from target behavior, not Golden symbols, missing dependencies, or environment errors;
- controls and regressions that should already work continue to pass;
- E2E reaches the target subsystem and fails on the same bug;
- no unexpected test is skipped.

Not every base case must fail. Tests for already-correct behavior should pass.

### 8.3 First Oracle run

Use the same canonical image and final tests. Confirm:

- reward is 1;
- every case and E2E path executes;
- no test is skipped;
- negative behavior still fails as required;
- E2E aligns with the instruction;
- Oracle does not modify tests, reward, or the verifier environment.

### 8.4 Controls

- Every adversarial patch scores 0 and fails on its planned behavior.
- The alternative implementation scores 1.
- Record passes, failures, E2E exit codes, and reward.

If any result differs from expectation, return to the relevant stage instead of starting repeated runs.

### 8.5 Post-change review

Repeat affected review-rubric checks:

- instruction authenticity, starting point, scope, and reproducibility;
- instruction–verifier mapping;
- implementation independence and the alternative implementation;
- E2E, hidden, regression, and negative coverage;
- Docker, Git, dependency, cache, and hidden-artifact isolation;
- whether planned evidence closes every finding.

Write results back to the remediation matrix. A new blocking finding returns to its corresponding stage even when first-pass tests passed.

## 9. Complete stability validation and Harbor

After the task is final:

- run base five complete rounds, each with reward 0 and a stable pass/fail matrix;
- run Oracle five complete rounds, each with reward 1 and every required layer passing;
- add justified E2E stress runs for concurrency, asynchronous, or race-sensitive tasks;
- use deterministic injection aligned with the Golden boundary rather than natural low-probability races.

Store reconstructed instruction logs with separate provenance. Do not place debug logs from overly strong injection into the instruction.

Run one final Harbor Oracle job with the final task files:

- use the final canonical image;
- hide tests, solution, and validation during the agent phase;
- execute the final verifier files;
- complete the expected number of trials;
- produce zero errored trials;
- produce reward 1;
- return zero unit, behavior, E2E, and integrity exit codes;
- retain the canonical image after the run.

Save job ID, trial ID, input task checksum, runtime, and verifier logs.

## 10. Refresh evidence from actual results

Evidence may contain only actual run results. Update at least:

- source PR or issue, base commit, and task scope;
- final status of every remediation-matrix finding and unresolved limitation;
- hashes for Dockerfile, lock, instruction, Oracle, tests, and helper scripts;
- canonical image tag, ID, size, and retained state;
- behavior count and integrity rules;
- five-round base and Oracle results;
- adversarial and alternative implementation results;
- E2E entrypoint, actual output, substituted boundary, and limitations;
- Harbor version, job ID, trial ID, input checksum, reward, exit codes, runtime, and error count;
- Git, dependency, cache, network, and hidden-artifact isolation gates.

When new output disagrees with old evidence, use the new output. Do not copy stale numbers or write expected results as if they ran.

## 11. Completion gate

Claim completion only when all conditions hold:

- instruction findings are closed with user participation;
- environment findings are closed and instruction reproduction works;
- Oracle satisfies the final contract;
- tests and verifier are implementation-independent and cover E2E, hidden, regression, and negative behavior;
- adversarial and alternative controls behave as expected;
- the final image is retained and passes isolation audits;
- five-round stability and Harbor are complete;
- evidence matches final artifacts and actual runs;
- no blocking finding remains in the remediation matrix;
- deferred findings have user approval and recorded risk;
- staged diff contains only approved changes.

Low remaining budget, a passing single run, or Harbor reward 1 does not replace these conditions.

## 12. Commit and hand off

Before committing:

- inspect staged file names, stat, and full diff;
- compare staged diff with the remediation matrix;
- exclude shared templates and unrelated files;
- preserve executable bits;
- synchronize instruction, test, Oracle, and evidence hashes;
- match task metadata image digest to the retained image;
- stage deleted or renamed validation patches correctly;
- use one commit per task unless the user requests a batch.

Commit only after the user asks. Report commit hash, finding closure, validation results, retained image, known limitations, and remaining dirty files.

Do not push, open a PR, delete tasks, or delete images unless the user explicitly asks.
