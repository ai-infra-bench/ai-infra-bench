# vLLM DCP slot mapping

## Published revision 1.8.5

The generation verifier now records the case before launch and, on a child
timeout, preserves captured stdout/stderr in `verifier/verifier.log` before
re-raising the original exception. Child Python output is unbuffered. The
300-second per-case limit, 1800-second verifier limit, assertions, checkpoints,
and reward policy are unchanged; there is no automatic retry. This records
output already emitted by the child, not a guarantee of recovering buffered
native-library output or logs from an externally killed container. Existing
validation archives and calibration below belong to their recorded versions;
they are not a new full Harbor acceptance run for 1.8.5.

## Task and environment

Repair Model Runner V2 for ordinary DCP generation with FlashAttention or FlashInfer. The developer request is in [instruction.md](instruction.md).

Instruction clarification (2026-09-18): the example interleave setting is not the only supported setting; the request explicitly covers valid DCP configurations, including the default, subject to backend and cache-block compatibility. No failure location, internal cause or repair strategy was added. Four frozen v1.8.5 GPT-6 Astra/high attempts used this clarified prompt: one completed all 24 checkpoints; three failed with candidate implementation defects reproduced in isolated diagnostic runs. See [latest-rollout-review.md](validation/latest-rollout-review.md). Earlier v1.8.4 calibration used the earlier instruction hash and remains historical evidence, not a new full control calibration for v1.8.5. Original snapshots and scores remain unchanged.

Version 1.8.4 provides two GPUs, 2 GiB shared memory, exact Base source, a digest-pinned offline image, and a small random-weight Qwen3 model/tokenizer at `/opt/models/tiny-qwen3`. This ordinary development resource contains no reproducer or repair hints and does not measure language quality. The Agent budget remains ten hours. Four current full Harbor functional controls passed calibration: Oracle and a distinct curated alternative score 1 (24/24); Base and historical v183 Oracle score 0. Historical passing results are not final v1.8.4 acceptance.

The repository runner schema declares A100 ×2; local calibration uses shared H20 ×2. A100 validation is still pending and is not inferred from H20 results.

## Verifier

The separate hidden verifier requires twenty-four checkpoints:

- Production runner/cache initialization, DCP slot mapping, supported block sizes 16/32, different ranks/interleaving, graph input updates, block replacement and non-DCP preservation.
- Real runner/sampler request lifecycles with independent deterministic consumers, complemented by real FlashAttention CUDA arithmetic and graph replay.
- Non-DCP Eagle preservation and sixty local FlashInfer decode steps covering growth, replacement, reordering and graph replay.
- Full-engine TP2/DCP2 generation for both FlashAttention and FlashInfer, each in eager and decode-graph modes, explicitly selecting both NHD and HND in fresh processes (eight combinations). Three requests have different completion times; a new request joins while an earlier one is still decoding across cache-block boundaries. Real model weights, KV writes, attention, independent worker processes and collectives run. All 256 output log probabilities at each of nineteen generated tokens per combination are compared with a separate CPU Transformers implementation using the same model weights.
- Four additional FlashInfer combinations force partial-prefill context with a 32-token budget, 32-token cache pages and new 13/62/63-token prompts (32 generated tokens per combination). Both layouts and eager/graph modes use the same independent full-distribution check.
- Two FlashAttention graph combinations use interleave 1 and 32-token cache pages with NHD/HND. These include ordinary engine startup/sampler warmup and subsequent real request graph replay; custom all-reduce stays enabled.

The older component tests still use local rank metadata and deterministic inputs where documented. In v1.8.1 the synthetic consumer checks request/token/position/slot association without requiring runner-populated optional local-length metadata; real attention and full-engine tests validate that length conversion actually works, wherever implemented. The engine tests do not replace groups or prepopulate caches. They use the normal `LLMEngine` admission/step interface, not candidate-added helpers or field names. Numerical tolerances allow FP16 GPU versus FP32 CPU rounding and near-tied greedy choices.

This is generation-engine coverage, not HTTP, production-model quality or a throughput benchmark. Model calls and passing rewards alone do not establish grading integrity; that separate review remains open.

The v1.8.4 changes follow actual GPT-6 rollout review: the prior Oracle mixed base-2 and natural-log attention statistics when a prompt was partially cached. A second issue reused captured attention during a dummy run whose attention inputs were not refreshed. The verifier tests public generation outcomes, not either internal repair. The unchanged v1.8.3 Oracle and original GPT-6 answer remain negative controls; a curator-modified GPT-6 answer refreshes dummy metadata as an alternative to the Oracle's eager skip-attention warmup. That modified control is explicitly not a new or unchanged agent success. The four v1.8.4 functional controls were calibrated before subsequent model attempts; the v1.8.5 logging revision has separate logging regression and rollout evidence, not a newly repeated full control matrix.

In v1.8.3 the Eagle component check enters through `execute_model`, `sample_tokens` and `take_draft_token_ids`, not private preparation/proposal signatures. Deterministic target/draft weights, a known cache and a permissive scheduler grammar mask isolate ordinary non-DCP attention behavior; this is runner integration coverage, not full Eagle model/grammar compilation coverage. The normal sampler, request updates, draft proposal and CPU draft transport execute. Exact draft outputs are matched by request ID for short, block-crossing and reversed-length batches. No candidate-specific argument adapter is used. The independent full-engine layout matrix is unchanged.

The v1.8.2 layout matrix addresses a demonstrated false positive: the earlier Oracle passed the default-layout suite but generated incorrect results with FlashInfer HND. Its unchanged patch is retained as a negative control. The repaired Oracle keeps the paged-cache layout separate from the token-major uncached K/V input layout. A saved GPT answer served as that version's alternative positive; its historical score is not inherited by v1.8.4.

The full-engine FlashAttention graph cases use `flash_attn_max_num_splits_for_cuda_graph=1`, also disclosed in the instruction. Larger split limits trigger a separate FA3 scheduler-metadata startup incompatibility in this image, reproduced on unmodified Base with the original runner. The task does not require fixing that unrelated compatibility issue. Real graph capture/replay and collectives remain enabled; no backend is substituted to bypass it.

## Layout

- `instruction.md`: Agent-visible developer request.
- `task.toml`: Harbor resources, isolation and collection metadata.
- `environment/`: image recipe, pinned dependencies and ordinary model-resource provenance.
- `solution/`: curator-only reference patch.
- `tests/`: hidden separate-verifier entrypoint and checks.
- `validation/`: control patches, current review/index and compact evidence archives.

## Evidence and running

See [review-report.md](validation/review-report.md), [latest-rollout-review.md](validation/latest-rollout-review.md), [remediation-matrix.md](validation/remediation-matrix.md) and [e2e-evidence.json](validation/e2e-evidence.json). The evidence index distinguishes the published task identity from historical calibration identities. Results must not be relabeled as belonging to another version. Original model scores remain unchanged; regrading a saved answer is not a new model attempt. Previous positive controls without current-layout validation are preserved under `validation/history/v181-positive-controls/`, not silently treated as current acceptance evidence.

`validation/evidence.zip` contains scoring/calibration records, not full model trajectories. Historical records are in `validation/history/curation-history.zip`. Extract archives separately; paths in original reports refer to their original campaigns.

Run with the pinned image and two available GPUs:

```bash
harbor run -p tasks/vllm-dcp-slot-mapping -a oracle
```

For a local shared host, bind an explicitly selected GPU pair in a frozen run copy's Compose files and record that binding. Harbor 0.22 deployments that do not advertise GPU allocation require the explicit Compose reservation; metadata alone is not sufficient.
