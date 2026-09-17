# vLLM DCP slot mapping

## What the Agent does

Repair Model Runner V2 behavior for deployments using Decode Context Parallelism. The user-facing contract is in [instruction.md](instruction.md).

## Environment

A digest-pinned vLLM CUDA image with the exact Base source, one A100-class GPU, an offline runtime, and a 10-hour Agent budget.

## Verifier

The separate hidden verifier exercises production Model Runner initialization, paged-KV slot mapping, DCP layouts, and CUDA graph replay. Block sizes 16 and 32 are separate supported deployments: real cache configuration generation groups two full-attention layers together, and the production scheduler KV manager accepts the resulting configuration. It also drives eight successive scheduler messages through the real runner and sampler: prefill, reordered decode, block growth, finishing requests, adding a prompt, reusing request capacity, and an empty final tick. Each block size uses a prompt just below its logical block boundary. Per-request generated token IDs are checked against an independent deterministic consumer model, in eager, graph, and non-DCP graph modes. Full credit requires eleven checkpoints and is written to `/logs/verifier/reward.txt`.

This is a subsystem end-to-end test, not an HTTP or multi-GPU model-accuracy benchmark. The model arithmetic, attention backend consumer, KV storage allocation, scheduler messages, and distributed group metadata are substituted; configuration generation, request state, input preparation, block-table kernels, CUDA graphs, forward context, and sampling remain real. No candidate-added argument or helper name is inspected or supplied. Validation uses an H20; the declared A100 environment remains unverified. See [the current review and remaining gates](validation/repair-review-2026-09-17.md). This is a repair submission, not final task acceptance; fresh model trials and grading-trust review are pending.

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
harbor run -p tasks/vllm-dcp-slot-mapping -a oracle
harbor run -p tasks/vllm-dcp-slot-mapping -a terminus-2 -m anthropic/claude-opus-4-8
```
