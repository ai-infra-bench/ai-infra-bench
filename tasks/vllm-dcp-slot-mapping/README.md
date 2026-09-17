# vLLM DCP slot mapping

## What the Agent does

Repair Model Runner V2 behavior for deployments using Decode Context Parallelism. The user-facing contract is in [instruction.md](instruction.md).

## Environment

A digest-pinned vLLM CUDA image with the exact Base source, one A100-class GPU, an offline runtime, and a 10-hour Agent budget.

## Verifier

The separate hidden verifier exercises production Model Runner initialization, paged-KV slot mapping, DCP layouts, and CUDA graph replay. Block sizes 16 and 32 are separate supported deployments: real cache configuration generation groups two full-attention layers together, and the production scheduler KV manager accepts the resulting configuration. It also drives eight successive scheduler messages through the real runner and sampler: prefill, reordered decode, block growth, finishing requests, adding a prompt, reusing request capacity, and an empty final tick. Each block size uses a prompt just below its logical block boundary. Per-request generated token IDs are checked against an independent deterministic consumer model, in eager, graph, and non-DCP graph modes. The suite retains real FlashAttention metadata/cache initialization and paged-attention CUDA computation through those runner lifecycles, plus non-DCP two-step Eagle preservation using real FlashInfer planning and decode computation. Version 1.7.0 adds 12 configurations with five successive real FlashInfer native decode steps each: rank-local cache means, page growth, reordered/replaced requests, and graph replay. Full credit requires seventeen checkpoints and is written to `/logs/verifier/reward.txt`.

This is composed subsystem coverage, not HTTP, NCCL multi-rank generation, or model-accuracy benchmarking. The original synthetic-consumer checks remain; the real-backend checks keep backend metadata construction and CUDA attention arithmetic real. Deterministic Q/K/V and local group metadata replace weights and communications, allowing an independent uniform-attention reference. The new FlashInfer DCP checks start at backend metadata planning with an already populated cache: they do not execute KV writes, full FlashInferImpl.forward, or cross-rank collectives. DCP real-backend graphs use the supported decode-only mode; no new mixed-prefill-graph performance requirement is imposed. No candidate-added argument or helper name is inspected or supplied. Validation uses shared H20 GPUs; the declared A100 environment remains unverified. See [the FlashInfer repair and calibration record](validation/review-report.md). This is a repair proposal, not final task acceptance; fresh model trials and grading-trust review remain separate gates.

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
- [Current evidence ZIP](validation/evidence.zip): original calibration results and scoring outputs; not full model trajectories.
- [Historical evidence ZIP](validation/history/curation-history.zip): superseded reports and calibration records, not current model scores.
- `validation/ci-cases.json` and `validation/*.patch`: executable control definitions; unexecuted security controls remain explicitly pending.

The evidence index links the historical Opus trajectory archive at its immutable Git commit. Extract ZIPs into a separate directory; original paths inside reports refer to their recorded campaigns. Runtime inputs are unchanged by consolidation.

## Running

Run with the pinned image available to the selected Docker daemon; the documented validation limitations remain open:

```bash
harbor run -p tasks/vllm-dcp-slot-mapping -a oracle
harbor run -p tasks/vllm-dcp-slot-mapping -a terminus-2 -m anthropic/claude-opus-4-8
```
