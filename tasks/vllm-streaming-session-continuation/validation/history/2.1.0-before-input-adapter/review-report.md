# Review report

Final validation: 13/13 full-entrypoint controls match their expected rewards. Oracle and three correct alternatives receive 1; Base and eight negative controls receive 0. The final Harbor Oracle receives reward 1 with zero errored trials. Correct Docker evaluations take 41.18–41.73 seconds (mean 41.37) with one A100. Oracle also passes a second independent fresh-model execution through Harbor.

Task 2.1.0 keeps the original instruction unchanged and replaces the fixed chunk-class import and self-consistency-only scoring with public behavior tests and an independent model reference. Final measured results are recorded in `e2e-evidence.json` and `local-regressions.json`; this document does not certify an earlier task snapshot.

The original 2.0.0 grading entrypoint gave reward 1 to four incorrect controls: constant output without a model or GPU, dropping all later chunks in a real engine, disabling ordinary generation, and fabricating observations before a successful process exit. Its Oracle also leaked an old explicit stop reason into a later completion. The new controls and checks target those demonstrated failures.

No named new input type is required. Correct controls cover a renamed public type, raw text input streams, and a different generated-context retention policy. The statement's unspecified budget semantics are not converted into hidden requirements: streaming stops are chosen while generation budget is ample. Closure through generator exhaustion is accepted.

The complete public input-to-output lifecycle runs through a real engine, with independent expected token sequences and completion metadata. Input delays are ordered by actual completed output, concurrent sessions are compared with separate runs, reused IDs are compared with fresh sessions, and ordinary prompts run before and after streaming. See `semantic-boundary.md` for the requirement map and allowed representations.

The reference patch fixes stop metadata capture/reset and prevents late decode results from an early-stopped segment crossing into its continuation. The latter was exposed by the new causal stop case under default asynchronous scheduling; it was not hidden by disabling asynchronous scheduling.

The unchanged environment remains the documented native ABI bridge rather than a newly rebuilt Base-native image. Its byte identity and exercised runtime path are checked; a claim of exact cutoff-native build provenance remains outside these verifier changes. Full malicious-code resistance and exhaustive coverage of every possible public API design or lifecycle combination are also not claimed.

The local Harbor adapter allocates exactly one GPU and enforces Docker `network_mode=none`; the final running verifier container's network mode and GPU assignment were independently inspected and archived. It changes no task input, candidate code, scoring logic or reward. Initial local attempts failed before execution due to offline-policy support and an undiscovered Docker Compose plugin; these infrastructure failures are separate from candidate results. The final run used Harbor 0.22.0 and Docker Compose 5.5.1 with a task-local plugin configuration.

This report records the validated task snapshot for PR #71. Executable identities are recorded in `e2e-evidence.json`; publication state is tracked by the PR's commits.
