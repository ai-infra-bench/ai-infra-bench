# Behavioral contract and validation boundary (1.3.3)

CPU or CUDA placeholder mask + CUDA text/multimodal embeddings -> real production merge and model-interface preparation -> ordered in-place output, count errors, synchronization and temporary CUDA allocation.

The CPU-mask valid-input path must not synchronize CUDA. A CUDA mask may synchronize to validate its cardinality; both paths have bounded temporary memory. This makes the previously ambiguous resource scope explicit. The task does not prescribe mask representation, an indexing algorithm, helper names, or prohibit an otherwise valid asynchronous mask copy.

| Requirement | Scored cases | Real boundary / substitutions |
| --- | --- | --- |
| Ordered values, preserved dtype, unchanged text positions, in-place identity | 12 merge combinations; each runs twice | Real production merge and CUDA; unique per-row values reveal within-segment reorderings |
| Correct successive calls after input contents change | Two mask devices, three calls each; same buffer shapes and placeholder counts, different positions, source values and text rows | Real merge with reused input buffers; only returned identity, dtype and output values are inspected, with the existing CPU-mask synchronization guard |
| Nested and batched tensor input | Two forms × three dtypes × both mask devices | Existing flattening forms at Base; deterministic values replace model forward |
| CPU-mask asynchronous execution | All six CPU-mask merge combinations; the in-vocabulary CPU-mask interface case; repeated CPU-mask calls | Real CUDA synchronization debug guard; it is not a complete detector for every possible native synchronization |
| Bounded memory for both mask devices | All 12 merge cases, two measurements each | Real PyTorch peak allocator statistics; pre-existing tensors excluded, peak includes live temporaries; threshold <4× destination bytes |
| Useful count errors | Five mismatches × both devices, plus empty list/tuple/tensor × both devices | Existing merge API; errors are an explicit part of the contract. Singleton and zero cases supplement non-broadcastable mismatches |
| Empty identity | Both mask devices | Empty list and zero mask; independent challenge also uses a zero-row tensor |
| Model input preparation | In-vocabulary CPU-mask and OOV CUDA-mask placeholders | Real SupportsMultiModal methods and actual embedding lookup; small fixed weights substitute model parameters |
| Completion integrity | All 34 ordered authenticated checkpoints plus successful child exit | Root parent grades; stdout never authenticates completion |

Masks and tensors in valid cases follow the production interface: a boolean mask of destination row count, with one embedding row for each true entry. The malformed-count cases intentionally enter the existing merge boundary that owns the requested error handling; they do not claim that normal Qwen preprocessing necessarily produces malformed counts. The OOV preservation case uses the normal CUDA mask and public `configure_mm_token_handling` initialization. CPU-mask OOV preprocessing is outside the stated Qwen3-VL merge repair: Qwen3-VL never configures the OOV branch at Base, while both production runners send device-local masks. Version 1.3.0 incorrectly combined the requested CPU-mask merge support with an additional OOV preprocessing extension. Its original rewards remain historical; saved answers are regraded separately.

Full Qwen weights, image decoding and HTTP serving do not determine this primitive's indexing or allocator behavior and are not claimed as executed. Independent challenges cover noncontiguous destinations and zero/singleton valid input sizes, rather than copying the scored inventory.

The native checkpoint emitter captures the trusted suite's code object and a key before candidate imports, then the process drops to `agent`. The parent validates authentication, sequence, case identity, observation shape and completion. Controls cover exit-without-output, forged stdout plus exit, and a direct call to the emitter from candidate code. This is bounded protection against these Python-level attacks, not a sandbox against arbitrary native memory access or all possible mutation of an in-process Python observer. Reference calculations and allocator observations still execute in a Python process that imports candidate code; that limitation is explicit.

The 4× allocator limit is a broad regression bound, not a universal optimality or throughput claim. Stability records and negative allocation controls must accompany acceptance. CPU-mask sync-debug checks do not prove the absence of every possible custom native synchronization.

Version 1.3.2 adds empty outer list/tuple/tensor cardinality regressions at the same merge boundary. Full-state replay of flash-r03 GPU0/GPU2 showed these forms silently accepted nonzero placeholders despite passing the previous [zero-row tensor] case. This enforces the existing incorrect-count requirement; it does not require empty-container behavior to change in higher-level model wrappers.

Version 1.3.3 covers the existing repeated-call contract. Equal-length requests or chunks with the same number of multimodal rows may place those rows at different offsets. The merge API accepts a fresh Boolean mask and matching source rows on each call; neither their shapes nor their counts constrain later positions or values. Reusing buffers with changed contents checks this behavior without requiring any internal cache representation or banning caching. The curated stale-placement control is only a validation input and is never read by the scorer.
