# Review remediation matrix

Historical review version: `fa13f4541d1da9d42dc400e4468178ce6b00b8da`.

The table and runtime results below describe the original PR #9 snapshot.
The current verifier additionally requires explicit TCP refusal and checks retained
descendant identities after shutdown. Runtime revalidation, including a
nonresponsive-listener negative control, was deferred at the maintainer's request.
See `e2e-evidence.json` for the current pending status and historical evidence link.

| Review finding | Remediation | Validation | Current state |
| --- | --- | --- | --- |
| P1: verifier required supervisor exit code 0 after child crash or unhealthy child shutdown, but the instruction only requires stopping the group, propagating failure, and cleaning processes/ports. | Removed the success-exit-code assertion from child-death, unhealthy-child, and SIGTERM cleanup checks. The verifier now scores the public lifecycle outcome: parent process exits, sibling ranks stop, and all sockets close. Invalid CLI still must fail non-zero before leaving endpoints behind. | Oracle reward 1. The correct alternative also passes while allowing failure exits. Base and wrong-CLI incomplete remain reward 0. | Fixed |
| P1: previously accepted alternative only sliced devices by TP and ignored PP; verifier fixed TP=PP=1, so the bug was not detected. | Added a hidden E2E case through public `vllm serve` with `data_parallel_size=4`, `data_parallel_size_local=2`, `data_parallel_start_rank=2`, `tensor_parallel_size=2`, `pipeline_parallel_size=2`, and eight visible devices. The verifier observes child `/rank` and `/device` over HTTP. | Correct alternative reward 1 with device slices `0,1,2,3` and `4,5,6,7`; old TP-only alternative is now `tp-only-device-slice-incomplete.patch` and scores reward 0 at the device assertion. | Fixed |
| Positive/negative controls needed to match the final verifier. | Updated `alternative-agent-implementation.patch` to account for TP*PP device slices and to expose supervisor health before slow child startup finishes. Added the old TP-only implementation as a separate negative control. | Direct Docker final matrix: Base=0, Oracle=1, alternative=1, TP-only incomplete=0, wrong-CLI incomplete=0. | Fixed |
| Evidence must be bound to the final task files rather than the pre-review snapshot. | Refreshed `ci-cases.json` hashes and `e2e-evidence.json` with final file hashes, direct Docker results, and a new Harbor Oracle run. | Harbor 0.22.0 Oracle: reward 1, job `5b129b95-3014-4a0d-978e-ad41ee1d8cd3`, trial `973c52f6-4131-47b7-acb9-3f08e1ac8a50`, task checksum `90bca2f00bb9d0b6c0f58f40681469ababc4e98d08b4a1fcb4469988d82f2e9d`. | Fixed |

## E2E boundary

The verifier enters through the public `vllm serve` CLI. Heavy model serving is
replaced by verifier-owned loopback HTTP handlers, but CLI parsing, supervisor
dispatch, rank/port/device derivation, child process management, health probing,
signal forwarding, and socket cleanup all run through the candidate code.

## Historical controls (before TCP/process cleanup changes)

| Candidate | Expected reward | Observed reward | Notes |
| --- | ---: | ---: | --- |
| Base | 0 | 0 | Required CLI flags are absent. |
| Oracle | 1 | 1 | Passes readiness, child death, unhealthy shutdown, TP/PP rank-device mapping, SIGTERM, and socket cleanup. |
| Correct alternative | 1 | 1 | Different supervisor implementation; passes the full public behavior contract. |
| TP-only device-slice incomplete | 0 | 0 | Fails the TP=2, PP=2 device assignment case. |
| Wrong-CLI incomplete | 0 | 0 | Implements different flag names, so the public requested mode is absent. |
