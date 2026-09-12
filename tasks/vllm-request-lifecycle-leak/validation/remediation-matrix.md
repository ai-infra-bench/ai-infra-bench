# Hardening scope

| Review finding | Change | Verification |
| --- | --- | --- |
| Redundant workspace instruction and hard wrapping | Remove workspace directive, use logical paragraphs, simplify final constraint | Read instruction.md |
| Native Scheduler SIGILL and missing platform metadata | Select pinned donor AVX2 binary, install minimal CPU metadata, expose venv PATH | Agent-user offline imports |
| Normal completion bypassed | Construct Scheduler and use schedule/update_from_output with deterministic model outputs | Base and external-finish-only controls fail release |
| Private helper dependency | Drive streaming via outputs and add_request | Renamed-helper control passes |
| Hash shape instead of cache semantics | Real KVCacheManager allocation, cache and lookup | Ordinal-hash control fails different-token lookup |
| Oracle streaming stale hash | Rebuild hashes when continuing after removing an uncomputed sampled token | Equal prefix reuse and changed last-block non-reuse |
| Forced GC accepted | GC callback checked after each lifecycle before cache regressions | Explicit-GC control fails GC assertion |
| Forged observation report | Require parent-observed RSS workload and stable retained-memory trend as well as behavior completion | Updated valid-protocol no-workload control fails external observation |

The semantic boundary is request input/model output/cancel/stream end -> real scheduler ownership and real cache transitions -> object reclamation, retained live data, emitted tokens and correct cache lookup. Model shapes are supplied by a deterministic provider; model math, HTTP and GPU execution do not determine the tested transition. No candidate-private helper or hasher representation is required.

RSS is supplemental evidence, not proof of object identity or a strong anti-tampering boundary. Python-level GC/weakref observations can be manipulated by arbitrary code in the same process. The external observer cannot by itself distinguish real lifecycle work from deliberately simulated allocations. Publication remains pending broader review of this explicitly limited threat model and validation scope.

Each memory batch has twelve touched 4 MiB payloads; four rounds reuse one scheduler and process. The parent requires at least 32 MiB of observed growth during the live workload and allows 16 MiB post-warmup growth. These margins must be checked on additional supported CPU runners before broad publication. Correct implementation and alternative measurements, rather than RSS dropping to zero, are the calibration evidence.
