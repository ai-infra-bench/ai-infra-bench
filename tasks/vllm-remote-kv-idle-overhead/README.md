# vLLM remote-KV idle scheduling

## What the Agent does

Keep scheduler ticks inexpensive while requests wait asynchronously for remote KV data, while preserving completion, ordering, accounting, and abort behavior. The user-facing contract is in [instruction.md](instruction.md).

## Environment

A digest-pinned vLLM CPU image with the exact Base source, offline runtime, and a 10-hour Agent budget. Version 1.2.1 includes pinned pytest/tblib and immutable OPT config/tokenizer metadata needed by normal upstream scheduler tests. Eight selected upstream tests passed offline as the agent user in the final image. This focused smoke check is not a claim that every upstream test runs without additional model weights. The donor Python source is removed and the final image excludes donor layers; see [environment provenance](environment/lock/README.md).

## Verifier

The separate hidden verifier supplies its own minimal KV connector and exercises the production Scheduler with small and large blocked populations, staggered completion events, new arrivals, cancellation races, mixed blocked reasons, accounting, and FCFS behavior. Lifecycle tests then feed deterministic model results through real `schedule()` and `update_from_output()`: local work while transfers are pending, out-of-order remote readiness, chunked prefill, multiple generated tokens, terminal client outputs, capacity pressure, later admission, and connector-disabled regression. Full credit requires eleven authenticated checkpoints and is written to `/logs/verifier/reward.txt`.

This is scheduler-subsystem end-to-end coverage: request admission through client-facing engine outputs and normal cleanup. Transport events and model token generation are deterministic substitutes. No HTTP server, actual NIXL/RDMA transfer, or full model accuracy benchmark is claimed. See [the current review](validation/instruction-e2e-review-2026-09-16.md).

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
