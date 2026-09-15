# vLLM multimodal merge memory

## What the Agent does

Eliminate avoidable accelerator memory pressure while merging multimodal embeddings without introducing host-device synchronization. The user-facing contract is in [instruction.md](instruction.md).

## Environment

A digest-pinned vLLM CUDA image with the exact Base source, one A100-class GPU, offline runtime, and a 10-hour Agent budget.

## Verifier

The separate hidden verifier calls the production multimodal interface across dtypes and mask layouts, observes transfers and synchronization, and checks peak allocation. Full credit is binary and is written to `/logs/verifier/reward.txt`.

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
harbor run -p tasks/vllm-multimodal-merge-memory -a oracle
harbor run -p tasks/vllm-multimodal-merge-memory -a terminus-2 -m anthropic/claude-opus-4-8
```

