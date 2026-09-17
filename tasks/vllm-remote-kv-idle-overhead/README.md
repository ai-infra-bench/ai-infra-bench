# vLLM remote-KV idle scheduling

## What the Agent does

Keep scheduler ticks inexpensive while requests wait asynchronously for remote KV data, while preserving completion, ordering, accounting, and abort behavior. The user-facing contract is in [instruction.md](instruction.md).

## Environment

A digest-pinned vLLM CPU image with the exact Base source, offline runtime, and a 10-hour Agent budget. Version 1.3.0 includes pinned pytest/tblib and pre-cutoff OPT and LLaVA config/tokenizer metadata needed by normal upstream scheduler tests, without weights or task-specific reproducer scripts. The core scheduler suite passed 91 tests with one skip as the normal agent user in the final offline image; this is not a claim that every upstream test works offline. The donor Python source is removed and the final image excludes donor layers; see [environment provenance](environment/lock/README.md).

## Verifier

The hidden verifier supplies a minimal KV connector and exercises the production Scheduler with small and large blocked populations, staggered completion events, new arrivals, cancellation races, mixed blocked reasons, accounting, and FCFS behavior. Lifecycle tests feed deterministic model results through real `schedule()` and `update_from_output()`: local work while transfers are pending, out-of-order remote readiness, chunked prefill, generated tokens, terminal outputs, capacity pressure, later admission, and connector-disabled regression. Streaming wait is entered by ending a real output segment and resumed by `add_request`, not by changing a private status field. Mixed remote/streaming idle cost and independent repeated streaming resumption are checked. Version 1.4.0 adds repeated cache-reset/preemption with runnable backlogs for both local and remote-origin streams, and 512 sequential completions per local/remote mode on a long-lived scheduler. Version 1.5.0 adds local/remote retained-memory checks against an explicitly published 32 MiB budget. Full credit requires eighteen checkpoints (seventeen behavioral groups plus suite completion) and is written to `/logs/verifier/reward.txt`.

This is scheduler-subsystem end-to-end coverage: request admission through client-facing engine outputs and normal cleanup. Transport events and model token generation are deterministic substitutes. No HTTP server, actual NIXL/RDMA transfer, or full model accuracy benchmark is claimed. See [the current review and limitations](validation/review-report.md). The v1.3.0 image is unchanged; earlier Harbor results remain historical, not v1.5.0 acceptance. Saved-answer regrading is not a fresh model rollout. Three subsequent fresh v1.5.0 DeepSeek trials each completed 18/18 checks; their results are recorded separately. This is a repair proposal, not a declaration of final acceptance.

Long-lived lifecycle tests score actual client tokens, exactly one terminal output per request, unfinished counts, later admission and absence of resurrected work. Weak-reference retention at 16/128/512 completed requests remains **non-scored telemetry**. The separate v1.5.0 resource check measures retained Python allocations after warm-up during 16,384 sequential short requests, with normal empty ticks and GC before each sample. It scores additional live allocations, not immediate object destruction, peak memory, GPU memory or RSS. Bounded-cache and batched-reclamation positive controls accompany the check; no private queue or helper is inspected. The finite load does not prove memory bounds for arbitrary future workloads. The separate grading-trust review remains open; reward 1 is not a blanket correctness certificate.

## Layout

- `instruction.md`: user-facing behavioral request.
- `task.toml`: Harbor metadata, resources, isolation, and artifact paths.
- `environment/`: exact Base source image and dependency provenance.
- `solution/`: Oracle patch and application script, hidden from the Agent.
- `tests/`: separate-verifier entrypoint and behavioral checks.
- `validation/`: control manifest and evidence for the frozen snapshot.

## Validation evidence

- [Current review](validation/review-report.md) and [remediation matrix](validation/remediation-matrix.md): scope, controls and unresolved gates.
- [Evidence index](validation/e2e-evidence.json): image identity, execution provenance, results and current artifact hashes.
- [Current evidence ZIP](validation/evidence.zip): original calibration results and scoring outputs, plus three fresh-trial summaries and trajectory-review reports; not full model trajectories.
- [Historical evidence ZIP](validation/history/curation-history.zip): superseded reports and calibration records, not current model scores.
- `validation/ci-cases.json` and `validation/*.patch`: executable control definitions; unexecuted security controls remain explicitly pending.

The evidence index links the historical Opus trajectory archive at its immutable Git commit. Extract ZIPs into a separate directory; original paths inside reports refer to their recorded campaigns. Runtime inputs are unchanged by consolidation. Offline tokenizer/configuration files in environment/lock/hf-cache are required upstream-test dependencies, not public reproducer scripts.

## Running

Run with the pinned image available to the selected Docker daemon:

```bash
harbor run -p tasks/vllm-remote-kv-idle-overhead -a oracle
harbor run -p tasks/vllm-remote-kv-idle-overhead -a terminus-2 -m anthropic/claude-opus-4-8
```
