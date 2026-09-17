# Behavioral contract and validation boundary (1.3.0)

CPU or CUDA placeholder mask + CUDA text/multimodal embeddings -> real production merge and model-interface preparation -> ordered in-place output, count errors, synchronization and temporary CUDA allocation.

The CPU-mask valid-input path must not synchronize CUDA. A CUDA mask may synchronize to validate its cardinality; both paths have bounded temporary memory. This makes the previously ambiguous resource scope explicit. The task does not prescribe mask representation, an indexing algorithm, helper names, or prohibit an otherwise valid asynchronous mask copy.

| Requirement | Scored cases | Real boundary / substitutions |
| --- | --- | --- |
| Ordered values, preserved dtype, unchanged text positions, in-place identity | 12 merge combinations; each runs twice | Real production merge and CUDA; unique per-row values reveal within-segment reorderings |
| Nested and batched tensor input | Two forms × three dtypes × both mask devices | Existing flattening forms at Base; deterministic values replace model forward |
| CPU-mask asynchronous execution | All six CPU-mask merge combinations; both interface cases | Real CUDA synchronization debug guard; it is not a complete detector for every possible native synchronization |
| Bounded memory for both mask devices | All 12 merge cases, two measurements each | Real PyTorch peak allocator statistics; pre-existing tensors excluded, peak includes live temporaries; threshold <4× destination bytes |
| Useful count errors | Five mismatches × both devices | Existing merge API; errors are an explicit part of the contract. Singleton and zero cases supplement non-broadcastable mismatches |
| Empty identity | Both mask devices | Empty list and zero mask; independent challenge also uses a zero-row tensor |
| Model input preparation | In-vocabulary and OOV multimodal placeholders | Real SupportsMultiModal methods and actual embedding lookup; small fixed weights substitute model parameters |
| Completion integrity | All 26 ordered authenticated checkpoints plus successful child exit | Root parent grades; stdout never authenticates completion |

Masks and tensors in valid cases follow the production interface: a boolean mask of destination row count, with one embedding row for each true entry. The malformed-count cases intentionally enter the existing merge boundary that owns the requested error handling; they do not claim that normal Qwen preprocessing necessarily produces malformed counts. The OOV case exercises the existing `_has_oov_mm_tokens` branch with out-of-range placeholder IDs and legal text IDs.

Full Qwen weights, image decoding and HTTP serving do not determine this primitive's indexing or allocator behavior and are not claimed as executed. Independent challenges cover noncontiguous destinations and zero/singleton valid input sizes, rather than copying the scored inventory.

The native checkpoint emitter captures the trusted suite's code object and a key before candidate imports, then the process drops to `agent`. The parent validates authentication, sequence, case identity, observation shape and completion. Controls cover exit-without-output, forged stdout plus exit, and a direct call to the emitter from candidate code. This is bounded protection against these Python-level attacks, not a sandbox against arbitrary native memory access or all possible mutation of an in-process Python observer. Reference calculations and allocator observations still execute in a Python process that imports candidate code; that limitation is explicit.

The 4× allocator limit is a broad regression bound, not a universal optimality or throughput claim. Stability records and negative allocation controls must accompany acceptance. CPU-mask sync-debug checks do not prove the absence of every possible custom native synchronization.
