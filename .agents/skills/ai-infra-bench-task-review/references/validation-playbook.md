# Hardening and Validation Workflow

Use this workflow after the user authorizes changes, validation, a commit, or a
PR. The review rubric defines correctness; this file defines execution order and
evidence discipline.

## 1. Confirm revision, scope, and authorization

- Continue from the reviewed version in the same isolated worktree.
- If the user selected a remote or worktree version of the skill, reread the
  skill and references from that revision before changing the task.
- Record the skill worktree path, HEAD, and dirty state together with the task
  HEAD, target directory, Base, cutoff, image, and dirty state. If the skill is
  dirty, record SHA-256 for `SKILL.md` and every loaded reference or script so
  the reviewed rules are not misidentified by HEAD alone.
- Preserve unrelated tracked and untracked changes.
- Commit, push, or create a PR only with explicit authorization.

Map every approved finding to its artifact change. Before editing behavior,
confirm the task name, repository, directory layout, resources, accelerator,
topology, network policy, and `[agent].timeout_sec = 36000`.

## 2. Fix the gates in order

### 2.1 Task statement

Keep the statement as an independent realistic scenario. Do not rewrite it to
match a source issue or PR. Those sources are inspiration for real interfaces,
mechanisms, and stronger task directions.

Classify proposed facts before editing:

- newly constructed business context, prompts, and user goals need realistic
  product semantics, not public provenance;
- historical claims and quoted logs, errors, responses, event sequences, and
  performance numbers need sources or captured execution;
- deterministic verifier inputs may replace an unavailable boundary when they
  preserve the target mechanism.

Treat first-person wording as part of a constructed scenario unless the
statement explicitly identifies or cites an actual historical event, source,
deployment, measurement, organization, or person.

Keep only user context, public operations, observable behavior, expected
outcomes, and behavior that must remain intact. Remove curation, mocks,
reproducers, environmental tradeoffs, Oracle internals, and hidden-case hints.

Freeze the task statement before changing the environment or verifier. If a
stronger related scenario would materially improve realism or difficulty,
present it to the user before expanding scope.

### 2.2 Environment

Write the target semantic boundary and classify story components as semantic,
substitutable, or context-only. Add or repair only the real components needed to
execute the behavior-determining path. A strong solver may construct substitutes
for unavailable non-semantic boundaries; do not put task-specific substitutes
or reproduction scripts in the agent image.

A component is semantic when replacing it with contract-valid deterministic
input could remove, reverse, or materially alter the Base-versus-Oracle
distinction at the target boundary. Do not require a complete production stack
merely because its components can affect unrelated final output.

Apply cutoff to the repository, models, tokenizers, data resources, required
external protocols, and semantic runtime dependencies. Pin general benchmark
infrastructure for reproducibility, but do not require the base image, Python,
Rust, uv, nextest, Harbor, compilers, or test tooling to predate cutoff unless
their behavior is part of the task.

Keep paths natural and remove agent-visible tests, solutions, validation
artifacts, reward logic, future source, and diagnosis aids from every image
layer. Strip remotes, remote refs, tags, reflogs, fetch metadata, and recoverable
future objects from the Base checkout.

Rebuild the image only when environment inputs change. Start the final image
with agent-phase user, workdir, resources, and network settings and confirm the
semantic path is reachable without verifier mounts.

### 2.3 Oracle and verifier

Use the statement and semantic boundary as the contract. Do not preserve an
Oracle-specific assertion by publishing implementation details.

- Enter through a public or stable subsystem boundary.
- Run every component whose contract-valid substitution could remove, reverse,
  or materially alter the Base-versus-Oracle distinction for real.
- Permit a composed E2E when the real target-boundary test and downstream
  contract test preserve compatible semantics.
- Map reward-affecting behaviors and collected case groups in both directions.
- Add regressions for required existing behavior and hidden variations within
  the contract.
- Add plausible adversarial controls and a semantically different correct
  alternative.

Before accepting the Oracle, derive the behavioral invariants independently and
construct at least one small contract-valid case that was not copied from the
Oracle or existing test inventory. Run it against the Oracle and a correct
alternative when practical.

For the fairness checks in rubric sections 5.1–5.4, record the public contract,
actual entrypoint and lifecycle transitions, exercised parameter combinations,
and expected versus observed behavior for the Oracle and each alternative.
Where an assertion rejects a contract-valid representation, repair location,
or failure exit status, replace it with an observable contract check. Retain
counterexamples for lifecycle gaps, implicit broadcasting, and interacting
configuration dimensions as applicable verifier-side regressions or controls.
Keep these artifacts out of the agent image. Distinguish function-level probes
from final grading runs and re-run affected cases and controls after fixes;
an earlier reward of 1 does not certify a control's correctness.

When fixing verifier permissions, retain write isolation from candidate code and
check that Harbor can collect rewards/logs using the intended host identity.
Record relevant owners, modes and mount restrictions for failures. Do not treat
root-only local success as evidence of non-root CI compatibility, or remove
completion safeguards to make collection pass.

Base must receive 0 because of the target behavior. Oracle and correct
alternatives must receive 1 with no skips or errors. Incorrect controls must
receive 0 through behavior alone.

For the early-exit controls required by rubric section 5.5, keep the control
patches in curator-only validation artifacts. Run each through the actual
grading entrypoint, including artifact transfer, verifier isolation, and
reward collection, on the final task image. Confirm that the control reaches
the intended candidate-code boundary and exits before required checks
complete, with final reward 0. An unrelated import failure is not evidence
that early termination is handled correctly.

Record the control patch hash, image identity, command, process exit status,
completed checks or completion evidence, and final reward. If the full
grading path is unavailable, report the narrower probe and leave this
validation pending. Re-run affected controls after changes to the grading
wrapper, process isolation, or completion checks.

## 3. Validate and freeze

Use this order:

1. Finish all executable changes: instruction, task configuration, environment,
   solution, tests, verifier, and controls.
2. Run the repository validator and the applicable static audit layers. JUnit
   is optional until a run record exists.
3. Check syntax, artifact hashes, test collection, patch applicability, image
   identity, Git isolation, and agent visibility.
4. Run Base, Oracle, adversarial controls, correct alternatives, and appropriate
   stability or stress trials.
5. Freeze executable artifacts. Any later executable change invalidates the
   affected behavioral and Harbor results.
6. Run the final Harbor Oracle trial and confirm reward 1, zero errored trials,
   and the expected test layers.
7. Update evidence and remediation documentation with only results that were
   actually run.
8. Run the final artifact audit with `--strict-evidence` and run
   `git diff --check`.

The Harbor input checksum identifies the task snapshot before the final evidence
write. Evidence-only or remediation-documentation updates may change the task
directory checksum without invalidating executable results. Record this
self-reference explicitly. A control, test, instruction, environment, solution,
or task configuration change is not evidence-only.

## 4. Evidence requirements

Keep evidence concise and machine-checkable. Record:

- final task, Base, cutoff, image, and executable artifact hashes;
- semantic boundary and substitutions, including why they preserve behavior;
- support for historical and quoted observations;
- actual Base, Oracle, control, alternative, stability, and Harbor results;
- final Harbor identifiers, reward, errors, and input checksum.

Do not infer missing runs, copy results from an earlier executable revision, or
claim that a generic static check establishes authenticity or verifier fairness.
Retain raw logs when they are needed to reproduce a conclusion.

## 5. Commit and handoff

Before an authorized commit or PR:

- stage only approved paths;
- run the staged-scope audit and inspect the staged diff;
- confirm no unrelated tracked or untracked changes are included;
- report the final hashes, image, validation results, and exact worktree,
  commit, branch, and PR state.

The task is complete only when all three gates pass, no blocker remains, the
10-hour budget and repository contract pass, Base/Oracle/controls behave as
expected, final Harbor succeeds, and evidence matches the executable artifacts.
