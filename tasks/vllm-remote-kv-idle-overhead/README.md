# vLLM remote-KV idle scheduling

## What the Agent does

Keep scheduler ticks inexpensive while requests wait asynchronously for remote KV data, while preserving completion, ordering, accounting, and abort behavior. The user-facing contract is in [instruction.md](instruction.md).

## Environment

A digest-pinned vLLM CPU image with the exact Base source, offline runtime, and a 10-hour Agent budget. Version 1.3.0 includes pinned pytest/tblib and pre-cutoff OPT and LLaVA config/tokenizer metadata needed by normal upstream scheduler tests, without weights or task-specific reproducer scripts. The core scheduler suite passed 91 tests with one skip as the normal agent user in the final offline image; this is not a claim that every upstream test works offline. The donor Python source is removed and the final image excludes donor layers; see [environment provenance](environment/lock/README.md).

## Verifier

The hidden verifier supplies a minimal KV connector and exercises the production Scheduler with small and large blocked populations, staggered completion events, new arrivals, cancellation races, mixed blocked reasons, accounting, and FCFS behavior. Lifecycle tests feed deterministic model results through real `schedule()` and `update_from_output()`: local work while transfers are pending, out-of-order remote readiness, chunked prefill, generated tokens, terminal outputs, capacity pressure, later admission, and connector-disabled regression. Streaming wait is entered by ending a real output segment and resumed by `add_request`, not by changing a private status field. Mixed remote/streaming idle cost and independent repeated streaming resumption are checked. Full credit requires thirteen checkpoints and is written to `/logs/verifier/reward.txt`.

This is scheduler-subsystem end-to-end coverage: request admission through client-facing engine outputs and normal cleanup. Transport events and model token generation are deterministic substitutes. No HTTP server, actual NIXL/RDMA transfer, or full model accuracy benchmark is claimed. See [the current review and limitations](validation/repair-review-2026-09-17.md). Twelve Harbor controls matched expectations on the v1.3.0 image; fresh model rollouts and the unresolved grading-trust review remain pending. This is a repair submission, not a declaration of final acceptance.

## Layout

- `instruction.md`: user-facing behavioral request.
- `task.toml`: Harbor metadata, resources, isolation, and artifact paths.
- `environment/`: exact Base source image and dependency provenance.
- `solution/`: Oracle patch and application script, hidden from the Agent.
- `tests/`: separate-verifier entrypoint and behavioral checks.
- `validation/`: control manifest and evidence for the frozen snapshot.

## Running

After the pending image and validation records are finalized:

```bash
harbor run -p tasks/vllm-remote-kv-idle-overhead -a oracle
harbor run -p tasks/vllm-remote-kv-idle-overhead -a terminus-2 -m anthropic/claude-opus-4-8
```
