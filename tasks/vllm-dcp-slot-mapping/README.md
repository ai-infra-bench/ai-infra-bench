# vLLM DCP slot mapping

## Task and environment

Repair Model Runner V2 for ordinary DCP generation with FlashAttention or FlashInfer. The developer request is in [instruction.md](instruction.md).

Version 1.8.2 provides two GPUs, 2 GiB shared memory, exact Base source, a digest-pinned offline image, and a small random-weight Qwen3 model/tokenizer at `/opt/models/tiny-qwen3`. This ordinary development resource contains no reproducer or repair hints and does not measure language quality. The Agent budget remains ten hours.

The repository runner schema declares A100 ×2; local calibration uses shared H20 ×2. A100 validation is still pending and is not inferred from H20 results.

## Verifier

The separate hidden verifier requires twenty-one checkpoints:

- Production runner/cache initialization, DCP slot mapping, supported block sizes 16/32, different ranks/interleaving, graph input updates, block replacement and non-DCP preservation.
- Real runner/sampler request lifecycles with independent deterministic consumers, complemented by real FlashAttention CUDA arithmetic and graph replay.
- Non-DCP Eagle preservation and sixty local FlashInfer decode steps covering growth, replacement, reordering and graph replay.
- Full-engine TP2/DCP2 generation for both FlashAttention and FlashInfer, each in eager and decode-graph modes, explicitly selecting both NHD and HND in fresh processes (eight combinations). Three requests have different completion times; a new request joins while an earlier one is still decoding across cache-block boundaries. Real model weights, KV writes, attention, independent worker processes and collectives run. All 256 output log probabilities at each of nineteen generated tokens per combination are compared with a separate CPU Transformers implementation using the same model weights.

The older component tests still use local rank metadata and deterministic inputs where documented. In v1.8.1 the synthetic consumer checks request/token/position/slot association without requiring runner-populated optional local-length metadata; real attention and full-engine tests validate that length conversion actually works, wherever implemented. The engine tests do not replace groups or prepopulate caches. They use the normal `LLMEngine` admission/step interface, not candidate-added helpers or field names. Numerical tolerances allow FP16 GPU versus FP32 CPU rounding and near-tied greedy choices.

This is generation-engine coverage, not HTTP, production-model quality or a throughput benchmark. Model calls and passing rewards alone do not establish grading integrity; that separate review remains open.

The v1.8.2 layout matrix addresses a demonstrated false positive: the earlier Oracle passed the default-layout suite but generated incorrect results with FlashInfer HND. Its unchanged patch is retained as a negative control. The repaired Oracle keeps the paged-cache layout separate from the token-major uncached K/V input layout. A saved, independently produced GPT answer is the current alternative positive control; the verifier checks outputs, not this implementation choice.

The full-engine FlashAttention graph cases use `flash_attn_max_num_splits_for_cuda_graph=1`, also disclosed in the instruction. Larger split limits trigger a separate FA3 scheduler-metadata startup incompatibility in this image, reproduced on unmodified Base with the original runner. The task does not require fixing that unrelated compatibility issue. Real graph capture/replay and collectives remain enabled; no backend is substituted to bypass it.

## Layout

- `instruction.md`: Agent-visible developer request.
- `task.toml`: Harbor resources, isolation and collection metadata.
- `environment/`: image recipe, pinned dependencies and ordinary model-resource provenance.
- `solution/`: curator-only reference patch.
- `tests/`: hidden separate-verifier entrypoint and checks.
- `validation/`: control patches, current review/index and compact evidence archives.

## Evidence and running

See [review-report.md](validation/review-report.md), [remediation-matrix.md](validation/remediation-matrix.md) and [e2e-evidence.json](validation/e2e-evidence.json). The evidence index is authoritative about which task version each run covers. Earlier results must not be presented as v1.8.2 results. Original model scores remain unchanged; regrading a saved answer is not a new model attempt. Previous positive controls without current-layout validation are preserved under `validation/history/v181-positive-controls/`, not silently treated as current acceptance evidence.

`validation/evidence.zip` contains scoring/calibration records, not full model trajectories. Historical records are in `validation/history/curation-history.zip`. Extract archives separately; paths in original reports refer to their original campaigns.

Run with the pinned image and two available GPUs:

```bash
harbor run -p tasks/vllm-dcp-slot-mapping -a oracle
```

For a local shared host, bind an explicitly selected GPU pair in a frozen run copy's Compose files and record that binding. Harbor 0.22 deployments that do not advertise GPU allocation require the explicit Compose reservation; metadata alone is not sufficient.
