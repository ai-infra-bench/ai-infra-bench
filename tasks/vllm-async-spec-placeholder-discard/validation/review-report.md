# Review and validation: async speculative reset accounting (0.0.2)

Retain the task after hardening. The task statement remains unchanged: its Qwen,
async scheduling, ngram speculation, reset endpoint and observed underflow match
the recorded upstream scenario. The repaired verifier scores the observable
lifecycle without requiring the Oracle's private request field.

## Semantic boundary and environment

The required boundary is:

real scheduler admission and speculative schedule -> forced prefix-cache reset
while output is queued -> FIFO stale output return -> resumed request state and
subsequent speculative progress.

The real `AsyncScheduler`, request queues, KV block manager, `schedule()`,
`reset_prefix_cache()` and `update_from_output()` execute in the pinned image.
The CPU verifier supplies deterministic draft and sampled token IDs in place of
the GPU model runner. These IDs are introduced at the same side of `schedule()`
as the corresponding production state: draft IDs exist before scheduling, while
sampled IDs return afterward. This preserves the state, width, ordering and
lifecycle semantics that determine placeholder accounting.

Base commit: `641cb595928a8914a7020e60125ed94496421801`.
Image: `sha256:4f29dae6b97d4d6fcbc7e8eb7238e71e95823e14aac1868c393678df5aa52496`.
The image and environment inputs were unchanged.

## Scored behavior

The 16 cases cover six stale speculative widths and partial/full rejection,
four ordinary no-reset acceptance patterns, a reset after a fully drained
frame, a non-speculative frame, three overlapping-reset variants, and a
three-request stale batch followed by a separately scheduled current batch.
No case writes `async_tokens_to_discard` or any candidate-added generation,
frame, callback or width field.

The longer lifecycle schedules 24 requests, queues one speculative frame and
ten subsequent non-speculative resumed frames across eleven forced resets,
delivers all 264 stale request frames in FIFO order, then requires 24 normal
progress events. A verifier-owned parent checks the child's exact completion
record, so a successful child exit before the final assertions is rejected.

## Correct alternatives and historical candidates

The Oracle uses accumulated token-slot debt. Four alternatives use early
whole-frame discard, a scheduler-output reset generation, per-request callback
counts, and exact per-frame scheduled widths. All five implementations pass
16/16 cases, the long lifecycle, and the final Docker and Harbor grading paths.
The generation, callback and width alternatives also pass an independent
five-request challenge with unseen widths six and four.

The eight historical gpt-5.6-sol patches that received reward 0 under version
0.0.1 were replayed unmodified against the 0.0.2 verifier. All eight now receive
reward 1. This does not rewrite their historical records; it demonstrates that
their previous failures were verifier false negatives and that they require a
versioned rerun for benchmark reporting.

## Negative and integrity controls

Base and the underflow-only guard, non-accumulating width fix, visible-width
special case, zero clamp, placeholder-only guard and candidate-conftest skip
receive reward 0. The `SystemExit(0)` and `os._exit(0)` controls reach the
eleventh reset after all 16 pytest cases have passed, terminate before the
lifecycle completion record, and receive reward 0.

The final Harbor 0.22.0 matrix contains 14 cases, matches all 14 expected
rewards and has zero Harbor exceptions. The final Oracle trial receives reward
1 with 16 passed, zero failed/skipped/error tests, and a completed long
lifecycle. Raw Docker, independent and Harbor logs are retained under
`runs/async-spec-hardening-20260907-171600`.

## State

Task version is 0.0.2. Validation was performed on local, uncommitted changes;
the user later authorized a local commit. No image rebuild, push or PR was
performed during validation. Existing changes outside this task were not
modified.
