# Review remediation

This hardening starts from PR #62 at `53b18f099c41f82db137325e829ffd27627b6382`. The earlier review and run records remain historical; the current executable hashes and results belong to `e2e-evidence.json`.

| Finding | Change | Validation |
| --- | --- | --- |
| P0: forged completion marker earns reward without running checks | A root parent drives every public operation, evaluates raw observations and writes reward. Candidate stdout and aggregate success reports are never used for scoring. | Bare SystemExit/os._exit, a printed success report, and correctly framed but behaviorally empty responses are negative controls. |
| P1: copied or discarded configuration passes | Constructor callbacks identify the exact engine-side object by `is`, with two distinct nonempty cache layouts and both roles. | Copy and empty-replacement controls must fail; correct implementations must pass. |
| P1: initialization and shutdown gaps | Exercise repeated initialization, real shutdown, repeated shutdown and a second lifecycle with a different configuration. Inspect public accessors and callbacks. | Duplicate-initialization and shutdown-noop controls must fail. |
| P1: only internal TypeError is covered | Add ordinary argument-binding errors and internal TypeError, ValueError and RuntimeError in both roles, checking single invocation and unchanged propagation. | Swallowed ValueError/RuntimeError and retried TypeError controls must fail. |
| P1: fixed diagnostic strings reject equivalent guidance | Check migration concepts without the fixture class name, a fixed parameter spelling or a prescribed exception class. | Equivalent prose and an alternative diagnostic exception type must pass; a message with no migration guidance must fail. |
| P2: stale evidence and inaccurate environment documentation | Archive prior records, describe the actual full-history Git checkout, and record current artifacts and results separately. | Final static audit checks recorded hashes; actual environment and Harbor results are required for publication. |
| Harbor result format and CI compatibility | Separate numeric reward from the behavioral report. Repository-wide parsing of `reward_stats.reward` was already merged in PR #75 and is not part of this task PR. | The final Harbor matrix passes through the merged reader. |
| Independent positive control and existing consumer forwarding | The alternative uses argument binding, keeps the original lookup helper and uses a base sentinel. The Oracle also forwards cache configuration through MoRIIO's existing base call. | Both reference implementations run through the same behavioral checks. The MoRIIO edit is a constructor forwarding repair; distributed MoRIIO transport is outside this CPU task. |

The developer request now distinguishes a single constructor invocation from worker lifecycle idempotence. It explicitly covers both roles, inheritance/forwarding, shutdown and reinitialization, without prescribing helper names or internal storage. [coverage.md](coverage.md) maps every assertion back to that contract.

Validation status: the final original-image Harbor matrix completed all 18 cases with zero errored trials. Oracle and three correct controls receive 1; Base and thirteen negative controls receive 0. The exact results, rejection reasons, image identity and executable hashes are recorded in `run-results.json` and `e2e-evidence.json`; the corresponding raw Harbor artifacts are retained in `harbor-run-artifacts.tar.gz`. Earlier diagnostic runs do not certify this snapshot.
