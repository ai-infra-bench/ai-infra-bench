# vLLM KV connector lifecycle

## What the Agent does

Move the external KV connector lifecycle to the current constructor contract without masking connector-internal errors. The user-facing contract is in [instruction.md](instruction.md).

## Environment

A digest-pinned vLLM CPU-compatible image with the exact Base source, offline runtime, and a 10-hour Agent budget.

## Verifier

The separate hidden verifier registers independent connectors and exercises factory creation, global lifecycle initialization, shutdown, and error propagation. Full credit is binary and is written to `/logs/verifier/reward.txt`.

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
harbor run -p tasks/vllm-kv-connector-lifecycle -a oracle
harbor run -p tasks/vllm-kv-connector-lifecycle -a terminus-2 -m anthropic/claude-opus-4-8
```

