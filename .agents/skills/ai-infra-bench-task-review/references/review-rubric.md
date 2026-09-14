# Task Review Rubric

This is the complete reference for task PR review: fifteen execution steps with their acceptance criteria, followed by the ten-dimension scorecard for human readers. Completing the scorecard does not replace carrying out the review. Evaluate only the task's applicable contract; examples of GPU, concurrency, or service behavior are not universal task requirements.

A valid task presents a realistic problem, lets a strong solver reconstruct the behavior-determining path in a normal development environment, and rewards observable behavior without requiring the Oracle's implementation. The statement defines correctness; upstream PRs, issues, and incidents provide context.

Work within the authorized review or hardening scope. Keep three gates in order: statement, environment, then verification. An early blocker permits further read-only diagnosis, but prevents final approval of later gates until the earlier contract is settled. During hardening, fix and freeze earlier gates before changing later ones. Record the checkpoints in existing review notes and evidence rather than creating a separate artifact for every step.

## 1. Fix the revision, workspace, and review scope

- Record the task worktree, branch, HEAD, dirty state, task directory, Base SHA, cutoff, image tag and ID, and applicable skill revision. When loaded skill content differs from HEAD, hash `SKILL.md` and every reference or script actually used.
- Inspect existing changes before editing. Use an isolated worktree when needed and preserve unrelated tracked and untracked files.
- Distinguish task review, candidate implementation review, and agent trajectory review. A verifier vulnerability does not establish that an agent exploited it; a passing agent run does not establish verifier quality. Review a trajectory only when it is in scope, using the actual operations and resulting patch.
- Read `instruction.md`, `task.toml`, and environment inputs before the Oracle and verifier. Independently describe the requested behavior, then inspect every artifact affecting build, execution, scoring, or publication.

When a particular branch, commit, or worktree version of the skill is requested, initialize that worktree safely, then reread its skill and references before reviewing. Record absolute skill and task paths and candidate or instance identifiers when present. Use SHA-256 for the required file hashes; HEAD alone does not identify dirty contents. Never mix rules from one revision with artifacts from another.

Read text, configuration, code, and patches completely. For large or binary resources, record at least type, size, and hash and inspect content when it affects the conclusion.

Checkpoint: identify exactly which snapshot and review scope each later conclusion covers. Do not mix results from different worktrees or uncommitted versions.

## 2. Review the statement as a developer request

Establish who would request the behavior, why it matters, whether the interfaces exist at Base, and whether the expected outcome makes sense. Constructed scenarios may differ from an upstream PR. Historical claims, quoted logs, exact errors, and performance numbers require sources or captured execution.

Write for a developer familiar with the project. Use PP, KV, NCCL, and `mp` directly when appropriate; avoid glossary-style expansions, redundant explanations, and repetitive sentence templates. Keep technical names consistent. Shorten repetition and setup prose while retaining concrete conditions and behaviors. For example, describing requests leaving a batch and remaining requests moving slots is clearer than only saying "handle compaction correctly."

Keep the statement focused on the requested change, observable behavior, and required regressions. Do not expose Harbor, curation details, fixtures, hidden-case inventories, Oracle helpers, or private repair steps. Natural wording must preserve the contract; a stylistic edit still requires a semantic comparison. Detector scores are not evidence of statement quality or a promised outcome.

Treat first-person wording such as "our service" or "I observed" as a constructed scenario unless it explicitly identifies or cites an actual organization, person, incident, date, deployment, measurement, or source record. A realistic constructed scenario needs no public incident as provenance.

| Content | Required support |
|---|---|
| Historical claim, verbatim log, exact error, response, event sequence, or performance number | A source or captured execution record |
| Newly constructed business context, prompt, example input, or user goal | Realistic product semantics; no public incident required |
| Deterministic or mocked verifier input for an unavailable boundary | A documented substitution preserving the target semantics |

Requests and commands must conform to the interfaces at Base. Quoted logs must be producible on the corresponding real path; do not combine lines that never coexist there. Record verifier substitutions and missing-resource tradeoffs in validation evidence, not the statement. Code reading can establish interfaces and mechanisms; actual output, failure, ordering, and metric claims need execution or an original captured record.

Do not disclose root-cause details unavailable to the user that reveal the repair. Difficulty and interest improvements remain non-blocking unless the current task is invalid, unrealistic, or trivial because it leaks the answer.

Checkpoint: a developer can understand the goal and relevant boundaries without unnecessary terminology explanations or guessing omitted requirements.

## 3. Set precise scope, then investigate upstream history

- Record supported backends, modes, inputs, resource preconditions, and adjacent behavior that must remain intact. Preserve quantifiers and distinctions such as "eligible requests may advance" versus "all requests must advance."
- Keep restrictions local to their intended path. A ban on blocking CPU readback during GPU token handoff does not prohibit normal later output collection or every synchronization elsewhere in the system. Multiple steps in flight do not require dependent kernels to execute simultaneously.
- Distinguish a test launcher from the product backend it exercises. Starting workers with `torchrun` does not establish coverage of vLLM's `external_launcher` executor.
- Use PRs, issues, discussions, and later repairs to identify failure mechanisms after deriving the contract. Include a later bug only if it follows from the agreed feature scope and can already occur at the frozen Base; do not import requirements from subsequently added features or interfaces.
- Apply the same contract to the Oracle. Repair applicable defects rather than exempting the historical implementation. Present material scope expansions before adopting them.

Differences in prompts, models, datasets, business settings, command sequences, deployment narratives, or repair approaches do not by themselves invalidate the task. Investigate a source difference when the task claims historical identity, uses nonexistent interfaces or operations, changes the behavior-determining mechanism, or quotes observations the real subsystem cannot produce.

**Gate 1 decision:** block when the workflow is implausible, interfaces do not exist, historical or quoted claims lack support, the claimed mechanism is unreachable, private solution information is exposed, or essential information cannot be discovered in the image. A constructed scenario differing from its inspiration is not a blocker.

Checkpoint: the agreed scope and applicable historical failures are explicit enough to design tests without using Oracle code as the specification.

## 4. Define the smallest complete execution boundary

Write `input or event -> behavior-determining subsystem or state transition -> observable result`. Include the necessary lifecycle, not just an isolated function call.

Enter reward-bearing tests through a public or stable subsystem interface and observe user-visible outputs, state, side effects, persistence, errors, or lifecycle behavior. Private helpers and intermediate state may assist diagnosis but must not determine reward unless they are themselves part of the stated contract.

Classify components as semantic, substitutable, or context-only. A component must run for real if a contract-valid deterministic replacement could remove, reverse, or materially change the target Base-versus-Oracle distinction. For each allowed substitution, explain how it preserves relevant state, cardinality, ordering, timing, and lifecycle.

For an async PP task, controlled model outputs can help component tests isolate token handoff, while an actual mp engine test checks the requested executor lifecycle. Do not replace the scheduler or worker execution responsible for the concurrency property being tested. Conversely, do not require an unrelated HTTP deployment merely because a user story mentions a service.

A semantic component determines the target distinction and must execute for real. A substitutable boundary only supplies valid input or consumes output without determining that behavior. Context-only components make the scenario realistic but are unnecessary to execute its target path.

Run the real tokenizer when tokenization determines the result; the target device and runtime for kernel, CUDA Graph, collective, DMA, or placement problems; and independent processes or nodes when isolation or network timing matters. A model forward may be replaced for parsing, serialization, routing, or device-independent orchestration. HTTP can be omitted as a mere trigger but must run when its request, streaming, cancellation, or lifecycle semantics determine the outcome. Mentioning a technology does not automatically make it semantic.

Preserve other explicit downstream output contracts through real tests without automatically adding the entire production stack. The image must allow a strong solver to construct missing inputs or valid substitutes from the statement and normal source, without preinstalled task-specific mocks, fixtures, trace injectors, or one-command reproducers.

Checkpoint: document the actual entrypoint, observation boundary, real components, and allowed substitutions with their limitations. A composed E2E is acceptable when its real component and downstream tests preserve compatible semantics.

## 5. Audit solvability, visibility, and runtime conditions

Start the final image under the agent's actual user, workdir, permissions, network, and resources. Verify the exact Base, dependency versions, import paths, build outputs, and patch application. Confirm candidate edits affect the code that actually executes. Do not depend on reviewer-only caches, mounts, or manual container changes.

### 5.1 Repository metadata and resources

Check every relevant `task.toml` field and run the repository validator:

- The task directory uses meaningful lowercase kebab-case without PR, issue, candidate, or instance identifiers; `[task].name` is `ai-infra-bench/<task-directory>`.
- The description is non-empty and suitable for publication. `base_commit` is a full immutable SHA consistent with Docker, locks, images, and evidence.
- Record `[agent].timeout_sec`. Below `36000` seconds, report a non-blocking warning that solvers may need more time, even if the repository validator does not check it. Do not require an exact budget or warn for budgets of 10 hours or longer.
- Check CPU, memory, shared memory, disk, build and verifier timeouts, network policy, device visibility, process startup, and communication. CPU tasks request no GPUs or topology; GPU tasks identify the actual accelerator and use a supported topology.
- Confirm models and data are available under the configured network policy. Smoke-test formal harness provisioning early: metadata alone does not prove a Docker backend assigns GPUs.

### 5.2 Natural development paths and visibility

Place real source, semantic dependencies, configuration, tools, and resources in normal repository, cache, installation, or configuration paths. Avoid task slugs, candidate IDs, and curator-oriented locations such as `/assets`, `/reproducer`, `/fixtures`, `/solution`, or `/validation` in the agent environment.

| Artifact | Default visibility | Review treatment |
|---|---|---|
| `instruction.md` | Agent-visible | Check for answer and test hints |
| Base repository, image filesystem, Git objects, caches, environment | Agent-visible | Check for future source and diagnosis aids |
| `task.toml` | Harness metadata, not agent-visible | Validate metadata; do not label it a solver leak |
| Task `tests/`, `solution/`, and `validation/` | Verifier/CI-only | Ensure they never enter the agent image or its layers |

Inspect the actual harness and update this visibility model if it differs. Information is a solver leak only when visible during the agent phase and materially revealing the answer, tests, or investigation path. Ordinary upstream tests at Base are not hidden-verifier leaks. Separately assess candidate-process access during verification in step 10.

### 5.3 Cutoff and image audit

Apply cutoff to the target repository Base, retained history and source objects; models, tokenizers, templates, data and supplied runtime resources; required external services or protocols; and runtime dependencies whose behavior affects the target boundary.

General benchmark infrastructure is exempt unless its behavior is part of the task. Base images, operating-system plumbing, Python, Rust, uv, nextest, Harbor, compilers, and test tools still need reproducible versions or digests. Do not reject an exempt tool merely for a later release date. Reclassify it when a GC, compiler, driver, or runtime defect is itself part of the target behavior.

Inspect the Dockerfile, build context, final filesystem, and image history, including:

```bash
docker image inspect "$image_tag"
docker history --no-trunc "$image_tag"
```

Verify HEAD, clean status, installed semantic dependency versions and import paths. The checkout must be at the exact Base and stripped of remotes, remote refs, tags, reflogs, fetch metadata, future reachable or unreachable objects, packs, bundles, alternates, caches, and secondary checkouts that could recover future source. Task tests, solutions, validation evidence, reward logic, and task-specific diagnosis aids must never enter agent-visible image layers. Deleting a final file alone does not establish this.

**Gate 2 decision:** block if the semantic path cannot execute, a required component is missing or unusable, material answer information is agent-visible, future source is recoverable, a cutoff-sensitive dependency is too new, or the environment selects incompatible hardware semantics. An exempt tool's release date or a valid non-semantic substitution outside the agent image is not a blocker.

Checkpoint: demonstrate solvability using the agent's normal development materials and actual resource conditions. Record infrastructure failures separately from candidate failures.

## 6. Build the bidirectional behavior-to-test map

For each requirement, record its preconditions, triggering scenario, real execution path, observed result, and relevant case group. For directly constructed internal fixtures, link the reachability evidence checked in step 8. Then trace every reward-affecting assertion back to a statement requirement or justified implication.

Check conditions such as available generation budget and KV capacity before requiring progress. Cover representative interacting dimensions: independently passing prefill, completion, and batch-movement cases do not establish that their interleaving works. Choose combinations from the contract rather than requiring an exhaustive Cartesian product.

Explain implications without silently adding features. Fresh admission after normal completion can check that scheduling remains usable; normal completion does not automatically imply cancellation or fault recovery. Classify fixture sanity and scoring-completion checks as evaluation integrity rather than candidate product features.

Map every reward-affecting behavior and every collected case group, including parameterized dimensions and counts. Source-line mapping is optional and cannot replace behavioral coverage. Protect existing adjacent behavior explicitly required by the statement, while varying meaningful values, lengths, shapes, batches, modes, backends, ordering, cold/warm state, repeated calls, recovery, and isolation only where they follow from the contract.

Checkpoint: every promised behavior has meaningful coverage and every scored requirement has a basis. Do not fix a mismatch by publishing Oracle internals in the statement. Track the map when either wording or tests change.

## 7. Audit fixtures, lifecycle transitions, and observation points

- Make test inputs valid under the frozen interfaces, including for Base. Missing Oracle symbols, malformed request objects, or invalid arguments cannot establish the target failure.
- Exercise actual admission, execution, completion, removal, and output collection where relevant. Directly changing a private field or deleting a test-local reference may bypass the ownership or lifecycle transition under review.
- Use the complete necessary input-preparation path. A local helper probe can omit normal prompt copying and create a fixture-induced failure.
- Observe the actual model argument or public result rather than assuming a named internal buffer is the final input. Compare by request identity rather than fixed batch row positions, and derive workload events independently of candidate placeholder representations.
- Examine setup, mocks, peers, and assertions for fixed helpers, sentinels, containers, layouts, call order, or validation timing not required by the contract. Private state may assist diagnosis without determining reward.
- An independent peer must not impose an unspecified candidate wire protocol. Let candidate endpoints interoperate and observe the required behavior through a boundary that preserves protocol freedom.

Assess validation timing and failure behavior at the observable boundary. Automatic selection need not expose a `None` accessor; an invalid configuration may be rejected at different startup stages when permitted by the public contract. Successful cleanup and a successful exit status are different requirements. Require a particular exit code only when the contract entails it.

For retention or cleanup, execute creation and use, the applicable completion/cancellation/stream-end event, and owner release before checking reclamation. Include a still-live case where retention is required. Callback counts or sentinel results alone do not establish real hashing or cache behavior.

Checkpoint: the test executes the necessary lifecycle and observes the actual behavior without depending on a particular internal representation. Check the reachability of constructed states in step 8.

For resource-cleanup contracts, observe the resources that must be released. Service unreachability does not establish cleanup: an HTTP timeout or failed health probe cannot prove that a listening socket closed or a process exited. Check listener state and relevant process identities separately when both are required. Retain identities before shutdown so reparented children remain observable. Include an applicable incorrect control that stops responding while retaining resources. Record direct resource-state observations, and confirm that verifier teardown removes test resources after both successful and failing checks; cleanup performed by verifier teardown must not be mistaken for candidate cleanup success. Apply these checks only to resources within the task contract.

## 8. Verify fixture reachability

Hidden tests must be concrete consequences of the public task contract under supported inputs and lifecycle transitions at the frozen Base. Deliberately chosen rare edge cases are valid; impossible internal states and unstated defensive requirements are not. Invalid external inputs may be tested when rejection or recovery is part of the contract, through the boundary that accepts those inputs rather than by bypassing its validation. An agent missing a case does not make it unfair, and many agents failing it does not make it valid.

When a fixture directly constructs or mutates internal objects, establish how the tested state can arise within the stated workflow. Constructor success, correct field types, and a local function reproducer are insufficient on their own. Check constraints imposed by preprocessing, validation, scheduling, and earlier lifecycle transitions, including relationships between fields that cannot vary independently. For example, moving a media range while keeping token IDs fixed needs evidence that the supported processor can produce that combination; a cache collision in a hand-built Request alone does not establish it.

Record a supported input or event sequence, the path that produces the relevant state, and the evidence connecting it to the fixture. A clear source-level derivation can establish straightforward invariants. When preprocessing or another disputed transformation determines whether the state can occur, run that transformation on representative valid input and inspect the resulting state. Reviewers must independently check this connection rather than infer reachability from an upstream merge or an Oracle pass. Keep reproduction evidence curator-only; do not expose hidden cases or add internal defensive requirements to the statement merely to justify a fixture.

Once reachability is established, a smaller behavioral test may reuse or reconstruct the state while preserving the relevant constraints and real behavior-determining components. This does not require running the entire service for every case or every scoring run. Mark unresolved reachability as unverified and keep the case diagnostic-only until resolved; do not use it to deduct reward, approve the task, or attribute failure to agent capability. If it currently affects reward, resolve the evidence gap or revise the case before acceptance. Remove or replace cases shown to be unreachable under the contract. Rare but reachable cases remain eligible even without a reported production incident.

Checkpoint: each reward-affecting fixture has evidence connecting it to supported inputs and lifecycle transitions, preserves the constraints of that path, and reaches the target behavior through valid interfaces. A legal change of internal representation or repair location must not invalidate the evaluation. Record unresolved reachability in the behavior-to-test map and the affected scorecard dimensions before acceptance.

## 9. Test progress and waiting through causal observations

Apply this step when concurrency, nonblocking execution, synchronization, or liveness is part of the contract. Correct final outputs and total runtime alone do not establish those properties.

Temporarily hold the dependency whose necessity is in question and observe whether the permitted next action occurs before release. For async request overlap, hold earlier work and check that another step for the same eligible request can be submitted. For unfinished prefill, withhold discarded sampling results and observe whether the next chunk can advance. Preserve valid resource preconditions, release the hold for cleanup, and use timeouts to bound hangs rather than impose an unstated throughput threshold.

Check implicit runtime waits as well as explicit synchronization calls. Define the measurement interval and separate initialization or legitimate buffer-reuse waits from prohibited handoff dependencies. Event provenance and recording order can distinguish these cases without attribute-name whitelists.

Audit the observer itself: extra device synchronization, token copies, mapping repair, or control communication must not supply missing candidate behavior or accidentally enforce the ordering being checked.

Checkpoint: evidence demonstrates the required causal relationship at the relevant boundary. Retain a control that preserves outputs while violating that relationship when applicable.

## 10. Trace scoring trust and completion integrity

Identify which processes load candidate code, produce expected results, write reports, and decide reward, together with their read/write access. A candidate-written success flag, digest, nonce, or zero exit status cannot independently establish that required behavior occurred.

Check verifier permissions under the actual host and container identities. Candidate code must not modify trusted grading scripts or final rewards, but Harbor must be able to traverse/read the collected output paths. A non-root owner on a trusted read-only harness mount is not by itself a trust failure; root ownership alone is not proof of effective isolation. If files are staged, verify their trusted origin and protection before candidate execution. Record relevant owners, modes, and mount restrictions for failures. Separate permission/setup/collection failures from behavioral reward 0, and require collection evidence with the intended non-root host when applicable. Root-only local success does not establish non-root CI compatibility. Do not remove completion safeguards to make collection pass.

When candidate code can terminate a process participating in verification, require early-success-exit controls at reachable boundaries, including both `SystemExit(0)` and `os._exit(0)` for Python when applicable. Catching the former does not protect against the latter. Confirm the scoring parent rejects incomplete checks. A root-owned script or independent container is not by itself sufficient when it executes candidate code.

Protect reference and intermediate answer files before writing answer bytes, and clean up scratch results according to their lifecycle. Verify candidate access rather than inferring isolation from ownership labels. Check that independent observation and completion evidence survive the applicable report-forgery controls.

An exit-code-only scoring pattern is a review lead, not by itself a demonstrated P0. Confirm a reachable bypass through the actual grading entrypoint and final reward before claiming that result. If a probe extracts or relocates code, identify the substitutions and missing container or Harbor checks.

For applicable early-exit controls, prove that the control reaches the intended import or execution boundary and terminates before required checks complete, while final reward is 0. An unrelated import error is not evidence of completion integrity. Keep control patches in curator-only validation artifacts; the scorer must not read them or compare candidate code with the Oracle.

Run each required early-exit control through the actual grading entrypoint on the final task image, including artifact transfer, verifier isolation, and reward collection. If that path is unavailable, record the narrower probe and leave full-entrypoint validation pending; a local rejection alone does not satisfy this requirement.

Checkpoint: the formal scorer requires completed behavioral checks, and the claimed isolation properties have evidence. Keep arbitrary-code tampering claims within the demonstrated boundary.

## 11. Run a compact set of distinguishing controls first

Before an expensive full matrix, challenge the verifier with Base, Oracle, a materially different correct implementation, and a small set of applicable incomplete or adversarial implementations. Prioritize controls likely to expose false acceptance or rejection: partial-path repairs, correct-output serial execution, implicit waits, and report-only or early-exit success where relevant.

Other plausible controls include special-casing examples, returning constants, swallowing errors, using an incorrect fallback, corrupting required output, or leaking state between requests. Select controls from the task's actual failure modes.

Independently derive at least one small contract-valid case not copied from the existing tests or Oracle conditions. Challenge the Oracle and a correct alternative with it. Independently justify the alternative's correctness and material difference; a passing reward can itself expose a coverage gap.

For every rejected control, establish that it reached the target path, satisfied the other relevant conditions, and failed for the intended reason. A serial control rejected for an incomplete report does not establish an overlap check. Correct the control and rerun rather than counting an unrelated failure as success.

Correct alternatives must differ materially in algorithm, data representation, or repair location; patch similarity alone is not evidence of a semantic difference. If an alleged correct alternative violates the contract, reclassify it as an incorrect control, repair the gap, and provide a genuinely correct alternative before acceptance.

Challenge implicit runtime behavior as well as explicit error branches. When shape or cardinality matters, select applicable empty, singleton, broadcastable-mismatch, and non-broadcastable-mismatch cases. Check promised device/backend paths, including same- and cross-device behavior where relevant; CPU probes do not establish CUDA correctness. Exercise interacting configurations such as TP/PP values, rank offsets, and visibility restrictions only when in scope. Do not impose a universal matrix on unrelated tasks.

Checkpoint: record expected and observed behavior, actual rejection causes, and evidence scope. Use local probes for fast diagnosis, then confirm consequential wrong-reward findings through the full grading entrypoint. Do not describe a local probe as a completed harness run.

## 12. Harden in dependency order and rerun affected checks

Within the authorized scope, repair statement defects first, environment defects second, and Oracle or verifier defects after those contracts are stable. Continue independent diagnosis when useful, but do not certify later stages against an unsettled requirement.

Map each finding to its artifact change and regression evidence. Keep applicable historical implementations as negative controls, replace representation-specific assertions with behavioral observations, and add missing causal tests. Do not weaken agreed requirements merely to preserve the old Oracle's passing score.

Rerun the affected checks and controls after each repair. Changes to report schemas, scoring wrappers, process isolation, or completion handling require updating and rechecking the relevant bypass controls. Preserve the behavior-to-test map through wording and implementation changes.

Freeze the agreed statement before changing the environment or verifier. Add or repair only the components needed for its semantic path. Rebuild the image only when environment inputs change, then confirm it works with agent-phase settings and without verifier mounts. Preserve the independent scenario rather than forcing it to match upstream source material.

**Gate 3 decision:** block when a required behavior lacks coverage, reward depends on undisclosed or Oracle-specific internals, no test executes the semantic boundary, a semantic component is mocked away, Base or Oracle fails for an unrelated reason, an incorrect implementation receives 1, or a correct implementation receives 0. Diagnose against the actual contract rather than changing expected rewards to hide a mismatch.

Checkpoint: distinguish confirmed failures, unresolved risks, fixes, and verified outcomes by version. This process does not expand the authorization already given.

## 13. Measure and optimize validation before the full matrix

Add stage timing before diagnosing cost: separate image preparation, process startup, CUDA/NCCL initialization, model loading, scenario execution, and timeout cleanup. Report single-candidate cost separately from the whole control matrix.

Reuse initialized processes or groups for compatible scenarios while rebuilding request and runner state as needed and checking isolation between cases. Keep deliberate exit, hang, or process-corruption controls isolated. Use small local models when they preserve the target semantics; avoid repeated downloads or oversized arithmetic that add no coverage.

Choose concurrency from available GPUs, CPU, memory, I/O, and existing workloads. Do not infer a speedup from a utilization snapshot or oversubscribe shared devices merely because more runs can be launched. Preserve user resource constraints and other jobs.

Checkpoint: coverage is unchanged, state does not leak across reused scenarios, and observed timing supports the resource plan. Progress reports identify the snapshot, completed stage, remaining work, and whether an ETA concerns one candidate or the entire matrix.

## 14. Validate the final snapshot through the formal entrypoint

Use this final-validation order within the authorized scope:

1. Finish instruction, task configuration, environment, solution, tests, verifier, and control changes.
2. Run the repository validator and applicable static audit layers. Check syntax, test collection, patch applicability, artifact hashes, image identity, Git isolation, and agent visibility. JUnit checks are optional until a run record exists.
3. Run Base, Oracle, correct alternatives, incorrect controls, and appropriate stability or stress trials. Confirm the expected behavior and actual failure reason for each.
4. Freeze executable artifacts. Any later executable change invalidates the affected behavioral and Harbor results.
5. Run the final Harbor Oracle trial. Require reward 1, zero errored trials, and completion of the expected test layers.
6. Update evidence and remediation records using only runs that actually occurred. Run the final artifact audit with `--strict-evidence` and `git diff --check`.

Verify artifact transfer, actual device assignment, isolation, required test completion, reward collection, and errored trials. Manual execution in a development container does not cover all these stages. Base must receive 0 because of the target behavior, not an import, fixture, dependency, or hardware error. Oracle and correct alternatives must receive 1 at the required semantic boundary with no skipped or errored checks; incorrect controls must receive 0 for the intended violation. The verifier must distinguish implementations through behavior alone.

Keep evidence concise and machine-checkable. Record final task and Base identities, cutoff, image identity, executable hashes, hardware, commands, semantic boundary and substitutions, expected and actual outcomes, failure causes, stability results, and necessary raw logs. Support historical and quoted observations. For early-exit controls, also retain the patch hash, process exit status, completed-check evidence, and final reward. Record final Harbor identifiers, reward, errors, and input checksum. If the full entrypoint is unavailable, leave that validation pending and label any narrower probe accurately.

The Harbor input checksum identifies the task snapshot before final evidence is written. Evidence-only or remediation-documentation updates can change the directory checksum without invalidating executable results; record this self-reference. Instruction, task configuration, environment, solution, tests, or control changes are not evidence-only. Reassess alignment after statement edits and rerun affected checks rather than carrying old passing results forward.

Checkpoint: reproducible evidence certifies the final executable snapshot. Static checks supplement behavioral evidence and cannot establish authenticity, fairness, or actual control behavior by themselves.

## 15. Report the disposition, limits, and handoff

Lead with whether the task can be retained and whether it passes, needs hardening, is invalid, or awaits verification. Present the ten-dimension scorecard for human readers, then the gate conclusions, blockers, evidence, and concrete next actions. Preserve the distinction between unknown evidence and a demonstrated failure; no aggregate score overrides a blocker.

For each consequential finding, identify the behavior, contractual basis, evidence, impact, and status. Distinguish code inspection, local reproduction, full-entrypoint verification, and final acceptance. State representative coverage and remaining limitations without claiming universal correctness or tamper resistance.

When trajectory review is requested, inspect the actual commands, edits, and final run evidence separately. Do not infer exploitation from a verifier weakness or equate one successful rollout with task validity.

Distinguish files changed, targeted checks passed, final acceptance passed, and changes committed or published. A review may conclude with findings or pending verification; that is not final task acceptance and does not authorize otherwise unrequested fixes or publication.

### 15.1 Finding priorities and evidence

- **P0:** false task premise, material agent-visible answer leakage, direct verifier bypass, or fabricated evidence.
- **P1:** wrong reward, Oracle contract violation, correct alternative rejected, Base failing for an unrelated reason, or the core semantic path being unreachable.
- **P2:** metadata, traceability, stale evidence, reproducibility, or publication completeness that must be resolved before release.
- **Non-blocking:** improvements that do not affect authenticity, solvability, scoring fairness, or release integrity.

P0 and P1 require a reproducible counterexample, actual failure, material visible leak, unreachable path, or explicit contract contradiction. Do not promote unsupported suspicion to a blocker.

The report must cover the realistic workflow and evidence classification; unsupported historical or quoted claims; the semantic boundary, real components, substitutions and solver reconstruction path; cutoff and visibility; bidirectional coverage, E2E composition and regressions; independent Oracle challenges and actual Base/Oracle/control results; findings, affected artifacts and non-blocking improvement proposals. Do not add a source-difference table unless the statement claims historical identity.

### 15.2 Acceptance and publication

Before an authorized commit or PR, run the staged-scope audit, inspect the staged diff, and preserve unrelated tracked and untracked changes. Report final hashes, image identity, validation results, and the exact worktree, branch, commit and PR state. Commit, push, or create a PR only with explicit authorization.

Final task acceptance requires all three gates to pass, no open blocker, repository checks to pass, expected Base/Oracle/control behavior, successful final Harbor validation, and evidence matching the executable artifacts. An agent timeout below 10 hours remains a reported non-blocking warning.

Checkpoint: another reviewer can understand the current state at a glance and follow the evidence to reproduce the conclusion. Required validation that was not run remains pending rather than being represented as complete.

## Ten-dimension scorecard

Include all ten dimensions, in this order, in every task PR review and updated review report. This is a task-quality scorecard, not the candidate reward. Use the user's language for the report while preserving the dimension numbers and meanings. Evaluate only the task's applicable contract; examples such as GPU execution or asynchronous scheduling are not requirements for unrelated tasks.

| Score / status | Meaning |
|---|---|
| 2 — Pass | Available evidence establishes the dimension's applicable criteria; no known requirement gap remains. This is scoped assurance, not exhaustive proof. |
| 1 — Partial | Evidence establishes some criteria and a concrete shortfall remains. Name the shortfall and whether it blocks acceptance. |
| 0 — Fail | Evidence establishes a fundamental failure of the dimension. Identify the failing requirement and finding. |
| U — Unverified | Evidence is insufficient to assign a score. State what needs inspection or execution; do not infer success or treat unknown as failure. |

A known failure can receive 0 even when other checks remain pending. A confirmed absence of required coverage is a finding, not merely U. Missing execution evidence must not be converted into a numeric score solely to complete the table. Static inspection can substantiate wording and explicit contract findings; actual behavior or reward claims require the corresponding execution evidence.

| # | Dimension | Criteria to assess |
|---|---|---|
| 1 | Is the task realistic and clear? | A plausible developer request with valid interfaces, clear scope, preconditions and boundaries. Use concise, natural language and familiar terms such as PP, KV and NCCL without unnecessary expansion; retain concrete behavior and edge conditions. Support historical or quoted observations when claimed. |
| 2 | Is correctness independent of the source PR? | The statement defines correctness; upstream material provides context without prescribing the historical implementation. Later fixes are included only when within the agreed scope and already possible at the frozen Base. |
| 3 | Can the agent solve the task in the environment? | The agent's actual user, permissions, network and resources support reconstructing the semantic path from normal source and components. No reviewer-only dependency, material answer leak or recoverable future source; apply the cutoff rules above. |
| 4 | Are the statement and tests aligned in both directions? | Every promised behavior has coverage and every reward-affecting requirement has a contractual basis or justified implication. Scored cases follow from supported inputs and lifecycle transitions, with reachability evidence for constructed internal states; they impose no unstated defensive requirements. Cover representative interactions without an exhaustive product of cases or publishing Oracle internals. |
| 5 | Do tests exercise the actual behavior-determining path? | Semantic components and lifecycle transitions run for real; substitutions preserve relevant semantics, including input preparation and relationships between fields. Simplified fixtures retain the constraints of the evidenced product path. Observe actual inputs, outputs and state transitions, with causal checks for progress or waiting when required. Instrumentation must not perform missing candidate work. |
| 6 | Can different correct implementations pass? | No unjustified dependence on private helpers, sentinels, containers, storage order or unspecified protocols. A materially different correct alternative passes, and its correctness is justified independently of its reward. |
| 7 | Are incorrect implementations rejected for the right reasons? | Base and applicable incomplete or adversarial controls fail for the intended contract violation after reaching the target path, rather than malformed reports, invalid fixtures or infrastructure failures. |
| 8 | Is the Oracle independently validated? | Independently derived invariants and at least one contract-valid challenge not copied from the existing test inventory assess the Oracle. Applicable historical defects are addressed; the Oracle completes the same required checks without exemptions. |
| 9 | Is the grading result trustworthy? | Trust and read/write boundaries are explicit. Required checks demonstrably complete; reports, early successful exits or copied reference answers cannot establish success by themselves. Security claims remain limited to demonstrated evidence. |
| 10 | Is acceptance reproducible and the handoff clear? | Evidence matches the final artifacts and environment; the formal grading path runs, resource use and timeouts are justified, and reproduction details, failure causes, coverage limits and worktree/commit state are accurate. Distinguish inspection, local probes and final-entrypoint validation. |

Use a compact report table with columns `# | Dimension | Score / status | Key evidence or gap | Next action`. Link evidence or finding IDs rather than repeating full findings. Keep all ten rows even in an interim review; use U for unfinished dimensions. For an updated review, identify the task snapshot and explain changed scores from new evidence or artifact changes. Earlier-revision results do not automatically certify the current revision.

Report fixture reachability under dimension 4 (contract and supported scenarios) and dimension 5 (input path and substitutions), citing the same finding when both are affected. If the evidence cannot justify a scored case, use U for the unresolved assessment rather than treating an Oracle pass or candidate failures as proof. A demonstrated unreachable scored case is a verifier defect, not merely U; apply the failure criteria above. Do not count the same issue twice as separate blockers.

Above the table, show the overall disposition, scored dimensions (`k/10`), unverified dimensions, and blocking findings. When all ten dimensions are scored, show the sum out of 20. If any dimension is U, show only the scored subtotal `S/(2k)` alongside the coverage count and explicitly leave the overall score pending; do not normalize it to a full-task percentage or present it as a completed score. When k is zero, omit the subtotal.

Retain the three-gate decisions and the priorities in step 15. A high aggregate score never offsets a blocker in any dimension, and incomplete required verification prevents a final pass. A minor non-blocking shortfall may remain a 1 with an explicit explanation; no numerical threshold replaces the acceptance criteria. Follow the table with the blocking issues and smallest concrete next actions. Avoid duplicating the same finding in the total blocker count when it affects several dimensions.
