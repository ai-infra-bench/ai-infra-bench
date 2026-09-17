# Runtime encoder-cache storage must be covered during profiling

**Behavior / contract.** A valid sparse media item is encoded and cached;
decoder profiling with that same maximal output must account for at least the
live encoder storage it will coexist with. The instruction explicitly asks to
keep profiling and the model runner consistent. At Base, GPUModelRunner's
profile_run pads and retains encoder outputs before its decoder dummy run.
That is independent discoverable support for the expected memory coverage.
The Oracle is a comparison implementation, not the specification.

**Legal inputs.** One image placeholder at offset 3 with 37 positions, four
embedded positions and width 3; a second has 61 positions, six rows and width 5.
SchedulerConfig uses one sequence, chunked prefill and normal multimodal limits.
Non-embedding positions are ordinary text within the placeholder. No cache
representation, helper name or new private field is prescribed.

**Boundary.** Scheduled encoder inputs -> actual batching/encoding/cache writer
-> live tensor storage after the returned temporary list is discarded. Then
actual MultiModalBudget and profile_run -> live tensor storage at the existing
_dummy_run decoder boundary. Weak references do not extend tensor lifetimes;
unique backing storage is counted once. Pre-existing input/mask storage is
excluded. The invariant is profiled storage >= live-per-item storage * the number
of actual profile items. Exact equality is deliberately not required.

**Substitutions.** Dummy media preprocessing provides PlaceholderRange metadata;
external model inference clones deterministic output rows. Real registry,
profiler, worker budget, batching producer, cache writer and profiling lifecycle
remain connected. Decoder work and device synchronization are replaced because
the observation occurs immediately before decoder execution. CPU payload bytes
are observed; CUDA allocation rounding/peak behavior is not claimed. No
candidate-specific adapter or inspection of a new cache layout is involved.

**Gap and differential evidence.** Original accounting/gather tests correctly
allowed dense storage, but never compared runtime storage with profiling.
Historical dense-cache control allocated 444/1220 live bytes yet reserved only
48/120 while profiling; it passed the original grader. Compact alternatives
cover 48/120 respectively. A corrected dense control covers its dense runtime
storage and passes all scoring. tBc overprofiles compact storage and also passes
this property, despite independently failing video estimation and lookahead.
The unmodified Base may pass this preservation property while failing the
complete repair contract; that is expected.

**Validation / promotion.** Diagnostic v2 used exact equality and rejected tBc;
that expectation was discarded rather than promoted. v3 changed to coverage and
proved Base/Oracle/direct-mask/distinct-accessor/dense-consistent positives and
the underprofiled dense negative. The complete 1.3.3 grader adds
`profile_runtime_coverage` to the authenticated required-stage inventory, after
preloading the worker with the other trusted modules. Actual Harbor canary05
and 27/27 complete Docker scoring controls passed with pre/post frozen input
checks. All four captured original answers regraded to 0; each passes this new
property, and each has independently reproduced remaining defects. New test
cases are development evidence, not held-out model evaluation.

Relevant executable files: `tests/encoder_profile_worker.py`,
`tests/verify_encoder_cache.py`, `tests/encoder_capacity_worker.py`.
Evidence: `evidence/rollout-hardening-1.3.3/full-control-matrix`,
`canary05-experiment.json`, `canary05-post-run-input-check.json` and the saved
answer replay directories. Historical matrices and patches remain unchanged.
