# vLLM remote-KV idle scheduling

## What the Agent does

Keep scheduler ticks inexpensive while requests wait asynchronously for remote KV data, while preserving completion, ordering, accounting, and abort behavior. The user-facing contract is in [instruction.md](instruction.md).

## Environment

A digest-pinned vLLM CPU image with the exact Base source, offline runtime, and a 10-hour Agent budget. Its image must be rebuilt after removing task-specific assets.

## Verifier

The separate hidden verifier supplies its own minimal KV connector and exercises the production Scheduler with small and large blocked populations. Full credit is binary and is written to `/logs/verifier/reward.txt`.

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

