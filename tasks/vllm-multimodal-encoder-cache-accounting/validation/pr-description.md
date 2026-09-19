This task fixes multimodal encoder-cache accounting when media spans more prompt positions than encoder output rows, including chunked prefill, lookahead, bounded cached payloads and profiling.

Version 1.4.3 fixes host-memory scoring with matched request lifecycles. It accepts equivalent lazy and preallocated position metadata, including diagnostics that grow with hidden width. Initial allocations are subtracted per run, so a fixed unrelated buffer cannot hide payload leakage. Width pairs plus a row-count contrast separate background growth from the demonstrated payload-retention defects; uncorroborated single-dimension growth remains diagnostic.

All 56 full-entrypoint cases matched their expected rewards: 24 positive implementations and 32 Base/negative controls. Thirteen Harbor trials completed with expected rewards and zero trial errors; 25 observer, comparison, completion and diagnostic unit tests passed. The environment remains CPU-only and offline, using the documented static Docker adapter. No model rollout was run.

The statement, Oracle and image are unchanged. F3 concerning `disable_chunked_mm_input=True` remains explicitly deferred; this revision adds no scoring requirement for it. Frozen identities, individual results and limits of allocation attribution are documented in `validation/final-review.md`, `validation/semantic-boundary.md` and `validation/e2e-evidence.json`.

The original [Astra/high trajectory](https://github.com/ouycc/ai-infra-bench/blob/08ee4f8/trajectories/vllm-multimodal-encoder-cache-accounting/gpt-6-astra-high-20260912/pr8-gpt-6-astra-high-once.zip) and its historical score remain intact. Its reassessment is in `validation/attached-trajectory-review.md`.
