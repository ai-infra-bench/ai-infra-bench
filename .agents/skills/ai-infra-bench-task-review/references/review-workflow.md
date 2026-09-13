# Fourteen-step task review workflow

Use these steps to conduct task PR reviews. The [review rubric](review-rubric.md) defines the acceptance criteria and finding priorities. Its ten-dimension scorecard is the summary for human readers; it does not replace the work below, and the fourteen steps are not fourteen additional scores.

Work within the authorized review or hardening scope. Keep the three gates in order: statement, environment, then verification. An early blocker permits further read-only diagnosis, but later conclusions remain provisional until the earlier contract is settled. For authorized fixes and final acceptance, also follow the [validation playbook](validation-playbook.md). Record the checkpoints below in existing review notes and evidence rather than creating a separate artifact for every step.

## 1. Fix the revision, workspace, and review scope

- Record the task worktree, branch, HEAD, dirty state, task directory, Base SHA, cutoff, image tag and ID, and applicable skill revision. Hash loaded skill files when they differ from HEAD.
- Inspect existing changes before editing. Use an isolated worktree when needed and preserve unrelated tracked and untracked files.
- Distinguish task review, candidate implementation review, and agent trajectory review. A verifier vulnerability does not establish that an agent exploited it; a passing agent run does not establish verifier quality. Review a trajectory only when it is in scope, using the actual operations and resulting patch.
- Read `instruction.md`, `task.toml`, and environment inputs before the Oracle and verifier. Independently describe the requested behavior, then inspect every artifact affecting build, execution, scoring, or publication.

Checkpoint: identify exactly which snapshot and review scope each later conclusion covers. Do not mix results from different worktrees or uncommitted versions.

## 2. Review the statement as a developer request

Establish who would request the behavior, why it matters, whether the interfaces exist at Base, and whether the expected outcome makes sense. Constructed scenarios may differ from an upstream PR. Historical claims, quoted logs, exact errors, and performance numbers require sources or captured execution.

Write for a developer familiar with the project. Use PP, KV, NCCL, and `mp` directly when appropriate; avoid glossary-style expansions, redundant explanations, and repetitive sentence templates. Keep technical names consistent. Shorten repetition and setup prose while retaining concrete conditions and behaviors. For example, describing requests leaving a batch and remaining requests moving slots is clearer than only saying "handle compaction correctly."

Keep the statement focused on the requested change, observable behavior, and required regressions. Do not expose Harbor, curation details, fixtures, hidden-case inventories, Oracle helpers, or private repair steps. Natural wording must preserve the contract; a stylistic edit still requires a semantic comparison. Detector scores are not evidence of statement quality or a promised outcome.

Checkpoint: a developer can understand the goal and relevant boundaries without unnecessary terminology explanations or guessing omitted requirements.

## 3. Set precise scope, then investigate upstream history

- Record supported backends, modes, inputs, resource preconditions, and adjacent behavior that must remain intact. Preserve quantifiers and distinctions such as "eligible requests may advance" versus "all requests must advance."
- Keep restrictions local to their intended path. A ban on blocking CPU readback during GPU token handoff does not prohibit normal later output collection or every synchronization elsewhere in the system. Multiple steps in flight do not require dependent kernels to execute simultaneously.
- Distinguish a test launcher from the product backend it exercises. Starting workers with `torchrun` does not establish coverage of vLLM's `external_launcher` executor.
- Use PRs, issues, discussions, and later repairs to identify failure mechanisms after deriving the contract. Include a later bug only if it follows from the agreed feature scope and can already occur at the frozen Base; do not import requirements from subsequently added features or interfaces.
- Apply the same contract to the Oracle. Repair applicable defects rather than exempting the historical implementation. Present material scope expansions before adopting them.

Checkpoint: the agreed scope and applicable historical failures are explicit enough to design tests without using Oracle code as the specification.

## 4. Define the smallest complete execution boundary

Write `input or event -> behavior-determining subsystem or state transition -> observable result`. Include the necessary lifecycle, not just an isolated function call.

Classify components as semantic, substitutable, or context-only using rubric section 4.1. A component must run for real if a contract-valid deterministic replacement could remove, reverse, or materially change the target Base-versus-Oracle distinction. For each allowed substitution, explain how it preserves relevant state, cardinality, ordering, timing, and lifecycle.

For an async PP task, controlled model outputs can help component tests isolate token handoff, while an actual mp engine test checks the requested executor lifecycle. Do not replace the scheduler or worker execution responsible for the concurrency property being tested. Conversely, do not require an unrelated HTTP deployment merely because a user story mentions a service.

Checkpoint: document the actual entrypoint, observation boundary, real components, and allowed substitutions with their limitations. A composed E2E is acceptable when its real component and downstream tests preserve compatible semantics.

## 5. Audit solvability, visibility, and runtime conditions

- Start the final image under the agent's actual user, workdir, permissions, network, and resources. Verify the exact Base, dependency versions, import paths, build outputs, and patch application. Confirm candidate edits affect the code that actually executes.
- Check required devices, process startup, communication, CPU, memory, shared memory, storage, and timeouts. Verify models and data are available under the configured network policy rather than relying on reviewer caches, mounts, or manual container changes.
- Apply cutoff to the repository and behavior-affecting dependencies and resources. Pin general benchmark tooling for reproducibility without imposing cutoff on exempt infrastructure; reclassify a tool when its behavior is itself part of the problem.
- Inspect recoverable Git history and objects, secondary checkouts, caches, build context, and image layers. Removing a final answer file does not establish that it never entered an earlier layer.
- Separate agent-phase visibility from candidate-process access during verification. Ordinary upstream tests at Base are not hidden-verifier leaks. Task-specific diagnosis aids, reference repairs, and hidden tests must not enter the agent image.
- Smoke-test the formal harness's resource provisioning early. In particular, confirm actual GPU assignment rather than assuming task metadata makes a Docker backend allocate devices.

Checkpoint: demonstrate that the agent can reconstruct and execute the semantic path using normal development material. Record infrastructure failures separately from candidate failures and apply the rubric's resource and budget rules.

## 6. Build the bidirectional behavior-to-test map

For each requirement, record its preconditions, triggering scenario, real execution path, observed result, and relevant case group. Then trace every reward-affecting assertion back to a statement requirement or justified implication.

Check conditions such as available generation budget and KV capacity before requiring progress. Cover representative interacting dimensions: independently passing prefill, completion, and batch-movement cases do not establish that their interleaving works. Choose combinations from the contract rather than requiring an exhaustive Cartesian product.

Explain implications without silently adding features. Fresh admission after normal completion can check that scheduling remains usable; normal completion does not automatically imply cancellation or fault recovery. Classify fixture sanity and scoring-completion checks as evaluation integrity rather than candidate product features.

Checkpoint: every promised behavior has meaningful coverage and every scored requirement has a basis. Do not fix a mismatch by publishing Oracle internals in the statement. Track the map when either wording or tests change.

## 7. Audit fixtures, lifecycle transitions, and observation points

- Make test inputs valid under the frozen interfaces, including for Base. Missing Oracle symbols, malformed request objects, or invalid arguments cannot establish the target failure.
- Exercise actual admission, execution, completion, removal, and output collection where relevant. Directly changing a private field or deleting a test-local reference may bypass the ownership or lifecycle transition under review.
- Use the complete necessary input-preparation path. A local helper probe can omit normal prompt copying and create a fixture-induced failure.
- Observe the actual model argument or public result rather than assuming a named internal buffer is the final input. Compare by request identity rather than fixed batch row positions, and derive workload events independently of candidate placeholder representations.
- Examine setup, mocks, peers, and assertions for fixed helpers, sentinels, containers, layouts, call order, or validation timing not required by the contract. Private state may assist diagnosis without determining reward.
- An independent peer must not impose an unspecified candidate wire protocol. Let candidate endpoints interoperate and observe the required behavior through a boundary that preserves protocol freedom.

Checkpoint: the fixture reaches the target behavior through valid interfaces, and a legal change of internal representation or repair location does not invalidate the evaluation.

## 8. Test progress and waiting through causal observations

Apply this step when concurrency, nonblocking execution, synchronization, or liveness is part of the contract. Correct final outputs and total runtime alone do not establish those properties.

Temporarily hold the dependency whose necessity is in question and observe whether the permitted next action occurs before release. For async request overlap, hold earlier work and check that another step for the same eligible request can be submitted. For unfinished prefill, withhold discarded sampling results and observe whether the next chunk can advance. Preserve valid resource preconditions, release the hold for cleanup, and use timeouts to bound hangs rather than impose an unstated throughput threshold.

Check implicit runtime waits as well as explicit synchronization calls. Define the measurement interval and separate initialization or legitimate buffer-reuse waits from prohibited handoff dependencies. Event provenance and recording order can distinguish these cases without attribute-name whitelists.

Audit the observer itself: extra device synchronization, token copies, mapping repair, or control communication must not supply missing candidate behavior or accidentally enforce the ordering being checked.

Checkpoint: evidence demonstrates the required causal relationship at the relevant boundary. Retain a control that preserves outputs while violating that relationship when applicable.

## 9. Trace scoring trust and completion integrity

Identify which processes load candidate code, produce expected results, write reports, and decide reward, together with their read/write access. A candidate-written success flag, digest, nonce, or zero exit status cannot independently establish that required behavior occurred.

Exercise applicable early-success exits at reachable boundaries, including both `SystemExit(0)` and `os._exit(0)` for Python. Confirm the scoring parent rejects incomplete checks. A root-owned script or independent container is not by itself sufficient when it executes candidate code.

Protect reference and intermediate answer files before writing answer bytes, and clean up scratch results according to their lifecycle. Verify candidate access rather than inferring isolation from ownership labels. Check that independent observation and completion evidence survive the applicable report-forgery controls.

Checkpoint: the formal scorer requires completed behavioral checks, and the claimed isolation properties have evidence. Keep arbitrary-code tampering claims within the demonstrated boundary.

## 10. Run a compact set of distinguishing controls first

Before an expensive full matrix, challenge the verifier with Base, Oracle, a materially different correct implementation, and a small set of applicable incomplete or adversarial implementations. Prioritize controls likely to expose false acceptance or rejection: partial-path repairs, correct-output serial execution, implicit waits, and report-only or early-exit success where relevant.

Independently derive at least one small contract-valid case not copied from the existing tests or Oracle conditions. Challenge the Oracle and a correct alternative with it. Independently justify the alternative's correctness and material difference; a passing reward can itself expose a coverage gap.

For every rejected control, establish that it reached the target path, satisfied the other relevant conditions, and failed for the intended reason. A serial control rejected for an incomplete report does not establish an overlap check. Correct the control and rerun rather than counting an unrelated failure as success.

Checkpoint: record expected and observed behavior, actual rejection causes, and evidence scope. Use local probes for fast diagnosis, then confirm consequential wrong-reward findings through the full grading entrypoint. Do not describe a local probe as a completed harness run.

## 11. Harden in dependency order and rerun affected checks

Within the authorized scope, repair statement defects first, environment defects second, and Oracle or verifier defects after those contracts are stable. Continue independent diagnosis when useful, but do not certify later stages against an unsettled requirement.

Map each finding to its artifact change and regression evidence. Keep applicable historical implementations as negative controls, replace representation-specific assertions with behavioral observations, and add missing causal tests. Do not weaken agreed requirements merely to preserve the old Oracle's passing score.

Rerun the affected checks and controls after each repair. Changes to report schemas, scoring wrappers, process isolation, or completion handling require updating and rechecking the relevant bypass controls. Preserve the behavior-to-test map through wording and implementation changes.

Checkpoint: distinguish confirmed failures, unresolved risks, fixes, and verified outcomes by version. Use the validation playbook for the hardening details rather than interpreting this workflow as new authorization.

## 12. Measure and optimize validation before the full matrix

Add stage timing before diagnosing cost: separate image preparation, process startup, CUDA/NCCL initialization, model loading, scenario execution, and timeout cleanup. Report single-candidate cost separately from the whole control matrix.

Reuse initialized processes or groups for compatible scenarios while rebuilding request and runner state as needed and checking isolation between cases. Keep deliberate exit, hang, or process-corruption controls isolated. Use small local models when they preserve the target semantics; avoid repeated downloads or oversized arithmetic that add no coverage.

Choose concurrency from available GPUs, CPU, memory, I/O, and existing workloads. Do not infer a speedup from a utilization snapshot or oversubscribe shared devices merely because more runs can be launched. Preserve user resource constraints and other jobs.

Checkpoint: coverage is unchanged, state does not leak across reused scenarios, and observed timing supports the resource plan. Progress reports identify the snapshot, completed stage, remaining work, and whether an ETA concerns one candidate or the entire matrix.

## 13. Validate the final snapshot through the formal entrypoint

Finish changes and run applicable syntax, configuration, collection, patch, repository, and image checks. Complete the required Base, Oracle, alternative, negative-control, and stability runs, then freeze the executable artifacts and perform final Harbor validation as specified in the playbook.

Verify artifact transfer, actual device assignment, isolation, required test completion, reward collection, and errored trials. Manual execution in a development container does not cover all these stages. Oracle and correct alternatives must complete the required checks without skips or errors; Base and incorrect controls must fail for the intended behavior.

Record artifact hashes, image identity, hardware, commands, expected and actual outcomes, rejection causes, run identifiers, and necessary raw logs. Later executable changes invalidate affected results. Statement changes require reassessing alignment; evidence-only documentation changes must be identified separately from executable changes.

Checkpoint: reproducible evidence certifies the final executable snapshot, not an earlier passing revision. Static checks supplement behavioral evidence and cannot establish fairness by themselves.

## 14. Report the disposition, limits, and handoff

Lead with whether the task can be retained and whether it passes, needs hardening, is invalid, or awaits verification. Present the ten-dimension scorecard for human readers, then the gate conclusions, blockers, evidence, and concrete next actions. Preserve the distinction between unknown evidence and a demonstrated failure; no aggregate score overrides a blocker.

For each consequential finding, identify the behavior, contractual basis, evidence, impact, and status. Distinguish code inspection, local reproduction, full-entrypoint verification, and final acceptance. State representative coverage and remaining limitations without claiming universal correctness or tamper resistance.

When trajectory review is requested, inspect the actual commands, edits, and final run evidence separately. Do not infer exploitation from a verifier weakness or equate one successful rollout with task validity.

Before an authorized commit or PR, inspect the staged scope and diff, include only approved paths, and report the exact worktree, branch, commit, and PR state. Distinguish files changed, targeted checks passed, final acceptance passed, and changes committed or published.

Checkpoint: another reviewer can understand the current state at a glance and follow the evidence to reproduce the conclusion. Required validation that was not run remains pending rather than being represented as complete.
