This task fixes multimodal encoder-cache accounting when a media item spans more prompt positions than encoder output rows. It covers chunked prefill, lookahead inputs, bounded cached embedding payloads and consistent profiling.

Version 1.4.1 fixes two verifier issues without changing the statement or Oracle. Repeated real request lifecycles now check that retired encoder payload does not accumulate, including copies retained outside the ordinary cache. Storage observation distinguishes metadata allocated with tensor-template factories from actual embedding-value copies. Correct mask allocation alternatives and reusable backing buffers are accepted.

All 41 full-entrypoint cases matched their expected rewards (15 positive, 26 Base/negative). Nine Harbor trials completed with expected rewards and no trial errors; 13 observer/completion unit tests passed. The environment remains CPU-only and offline, using the documented static Docker network adapter. No new model calls were made.

Results, executable identities and limits are recorded in `validation/final-review.md`, `validation/semantic-boundary.md` and `validation/e2e-evidence.json`. Historical 1.4.0 counterexamples and validation records are preserved separately.

The original [Astra/high trajectory](https://github.com/ouycc/ai-infra-bench/blob/08ee4f8/trajectories/vllm-multimodal-encoder-cache-accounting/gpt-6-astra-high-20260912/pr8-gpt-6-astra-high-once.zip) earned reward 1 under 1.2.8. Its original score is preserved; current checks reject the remaining Qwen3-VL video-estimation error, as described in `validation/attached-trajectory-review.md`.
