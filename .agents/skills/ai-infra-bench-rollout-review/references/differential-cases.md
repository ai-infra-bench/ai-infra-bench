# Behavioral cases derived from rollouts

Use this procedure when a rollout reveals a suspected coverage gap or when
several wrong attempts fail in different ways. The aim is a valid behavioral
regression, not a predetermined distribution of rewards.

## 1. State the hypothesis independently

Read the actual patches and trajectories, then translate the difference into a
user-observable hypothesis. For example: 'after the final request finishes, a
remaining load must complete without a new request arriving.' Do not state the
hypothesis as 'candidate A has a helper that candidate B lacks.'

Derive the expected result from the task and normal product contract. A
majority of candidates, the best-scoring model, and an observed reference output
are not independent specifications. Follow the main skill's contract-evidence
rules: reference behavior is normative only within an explicitly specified
compatibility requirement. If the desired behavior is ambiguous, record a
contract question; do not install a failing assertion to settle it implicitly.

Check both reward-1 and reward-0 answers. Failed answers can be better than
passing ones on an untested dimension. If all eight answers fail the current
suite, a new case can still distinguish which handle that dimension correctly.

## 2. Prove that the case belongs in the task

For each proposed case record:

| Item | Required evidence |
|---|---|
| Contract basis | A statement clause or a necessary implication supported by normal source/docs available to the solver. |
| Legal input | A public input, configuration, event, or lifecycle sequence valid in the pinned environment and task scope, including a feature the task asks to add. |
| Expected result | An invariant or observable outcome justified by the contract, not by the observed candidate/reference split. Separate structural validation from semantic requirements. |
| Boundary | Input/event -> real behavior-determining transition -> observable result. |
| Substitutions | Which producers/consumers are replaced and why state, cardinality, ordering, timing class, and lifecycle remain valid. |
| Coverage gap | Why existing tests miss this property, including whether they fail earlier and mask it. |
| Comparison conditions | Effective inputs/configuration/lifecycle on both sides, and whether reference-positive selection is a user-imposed experimental restriction. |

Reject tests of unrelated edge cases, undocumented new policies, or impossible
states. A case may reveal that the initial review missed a real contract or
environment defect; reopen that defect rather than hardening around it.

## 3. Enforce implementation independence

A scored case may enter via an existing or task-specified public API or stable
subsystem boundary. It must exercise the code that determines the behavior.
It must not import a solution-specific helper, read a newly introduced private
field, compare code to the Oracle, inspect an algorithm, require a particular
constructor signature, or dispatch on candidate
identity to fill implementation-specific fields.

Avoid dynamic 'compatibility adapters' that inspect each patch to discover its
new helper or config field. They merely hide solution coupling. Move the test
input upstream to normal configuration/requests and observe the outcome
downstream. If no faithful stable boundary is available, keep the probe as
diagnostic evidence until the verifier design is repaired.

Preserve freedom to rename all newly introduced internals, move the fix, and
choose a different algorithm or representation without changing the test. Exact
values remain legitimate when the product contract fixes them: for example,
published wire fields or a required legacy artifact. Candidate-chosen directory
hashes, internal counters, and helper names are not such contracts.

| Suspected gap | Suitable scored observation | Unsuitable solution constraint |
|---|---|---|
| Final transfer stalls after requests finish | Run the real request/transfer lifecycle; observe completion and successful reset retry without another user request. | Require a newly added `pending_loads()` helper or exact private dictionary contents. |
| Persistent cache loses upgrade compatibility | Place a contract-valid legacy artifact, restart through normal config, and check hit plus loaded data. | Assert the candidate's new namespace field, helper, or selected digest format. |
| Streams corrupt or omit deltas | Feed valid event sequences through the real parser; inspect client-visible deltas and terminal result. | Invoke a solution-defined parser helper or assert an exact internal branch/call count. |

Assertions on a pre-existing hook can still be too prescriptive if another
correct implementation can satisfy the public behavior elsewhere. Public
behavior is the acceptance criterion unless the hook itself is explicitly the
task contract. Use private assertions only for clearly labeled diagnosis.

## 4. Run the differential experiment

- Use a frozen case and record input hashes before execution, then check them
  afterward. Apply each complete saved answer to the same compatible Base/image
  in a fresh workspace/container; restore untracked artifacts and relevant
  runtime changes. Missing final artifacts limit replay claims; reconstructed
  code is a separate diagnostic experiment.
- Run the case independently of earlier suite failures when those would mask
  the result. Keep the original suite too. Capture actual output, first causal
  failure, data/state effects, and whether the target boundary executed.
- Select controls under the approved validation mode and the property being
  tested. Where the mode requires them, use the Oracle and a semantically
  different correct alternative, independently justified by the contract.
  For verifier-only tasks, use contract evidence and relevant boundary controls
  without demanding a complete solution. Record what full-task solvability
  remains unproven. Base may pass a preservation case; its full-suite failure
  should expose the target defect or missing feature, not an invalid fixture.
- Compare effective semantic conditions rather than flag spelling. Investigate
  configuration differences before attributing a failure. A reference failure
  does not disqualify an otherwise contract-valid case; a user-requested
  reference-positive experiment narrows this comparison, not the task contract.
- Vary a relevant nontrivial input after the minimal reproducer succeeds, such
  as another request identity, width, mode, topology, or lifecycle ordering.
  Avoid exhaustive combinations unrelated to the demonstrated concern.
- Produce a matrix with columns for the original suite and each new case.
  Passing/failing splits must follow observed behavior. Do not select arbitrary
  constants, identities, or timing to hit a desired split, and retain useful
  contract-valid cases even if all candidates agree on them.

If a new case rejects an Oracle or other reference implementation, diagnose
both the case and the reference. If the reference violates the contract, keep
the valid case and record the reference limitation or required correction.
Do not weaken an assertion merely to keep a reference solution green.
Likewise, a candidate rejected only for missing a solution-specific helper is
evidence against the test, not against the candidate.

## 5. Promote with validation proportional to the change

Resolve contract ambiguities before changing scoring. Within authorized
hardening scope, add the smallest behavior-only case that catches the missing
property. Preserve valid requirements; correcting a faulty test is a separately
documented change.

| Work stage or change | Validation scope |
|---|---|
| Diagnose a suspected behavior | Minimal reproducer and relevant positive/negative controls; do not rerun every qualification gate. |
| Edit a behavioral case or fixture | Affected cases, affected saved candidates, and relevant controls while iterating. Shared-fixture changes may affect more than the new case. |
| Change collection, startup, or scoring integration | An actual Harbor integration check for the changed path, including produced artifacts or final rewards; a direct shell smoke test/config parse alone is insufficient. No new model rollout is required merely to test collection. |
| Change only documentation or evidence indexing | Check references, result identity, and consistency. Do not rerun inference or an unchanged full suite solely to refresh reporting hashes. |
| Accept the final executable revision | Freeze the revision and consolidate complete-scoring checks for affected deliverables and mode-appropriate controls; reuse attributable unchanged evidence. Passing an isolated new case does not prove the revised full score. |

Use the task's approved validation mode at every stage. Full-scoring checks for
verifier-only tasks do not implicitly require creating a complete Oracle or
alternative implementation. Retain explicit solvability and coverage limitations.
After final acceptance, rerun only when subsequent executable changes, failures,
or unresolved concerns justify it; reporting edits alone do not reset validation.

When scoring/completion is affected, check that required checks actually finish,
including when candidate code raises `SystemExit(0)`, calls `os._exit(0)`,
suppresses failures, or leaves children alive. Use corresponding controls for
other runtimes. Neither exit code zero nor a candidate-writable success marker
proves completion. Demonstrate claimed bypasses through the actual final reward
path; an exit-code-only pattern alone is a lead, not a confirmed exploit.

### Bind results to the executed snapshot

Before execution, freeze and identify tests, fixtures, scoring code, candidate
artifacts, effective configuration, and the image. Keep running snapshots
immutable; edit a separate worktree or next snapshot during iteration. Verify
input hashes afterward and bind each result to those inputs and the cases
actually executed.

If inputs changed while a process was running, do not stamp the final worktree
hash onto the result. Use a captured immutable snapshot if available; otherwise
mark provenance uncertain and rerun the affected checks from frozen inputs.
Do not combine partial runs from different revisions into a claimed complete
pass of the final revision without establishing which evidence still applies.

Update test inventory and task version when behavior/scoring changes. Evidence
documents may be generated after the run, but they must reference the pre-run
executable hashes. Hashing a report later is distinct from proving which tests
ran; avoid self-referential evidence hashes that cause needless reruns.

Do not claim the revised task was always fair, rewrite historical reward zeros
as successes, or describe these development cases as held-out tests. Recommend
fresh rollouts on the frozen revision when needed; run them only within the
user's authorized model/count/budget settings.
