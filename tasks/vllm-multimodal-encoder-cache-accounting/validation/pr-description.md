This task fixes multimodal encoder-cache accounting when media spans more prompt positions than encoder output rows, including chunked prefill, lookahead, bounded cached payloads and profiling.

Version 1.4.2 fixes the F1, F2 and F4 review findings. Capacity checks observe real admission and profiling instead of named budget fields. Host-allocation checks reject Python/NumPy payload expansion and retirement leaks while accepting compact representations, position metadata and reusable buffers. Independent diagnostic entrypoints now distinguish behavioral failures from missing files, imports and setup errors.

All 52 full-entrypoint cases matched their expected rewards: 21 positive implementations and 31 Base/negative controls. Sixteen Harbor trials completed with expected rewards and zero trial errors; 17 observer, completion and diagnostic-reporting unit tests passed. Existing allocation tracing is preserved, with both a compatible positive and a matching leak control. Oracle took 44.3 seconds per verifier run; ordinary positives averaged 46.7 seconds and the tracing-enabled positive took 102.6 seconds, excluding startup and independent challenges. The environment remains CPU-only and offline, with the documented static Docker network adapter. No model rollout was run.

The statement, Oracle and image are unchanged. F3 concerning `disable_chunked_mm_input=True` was explicitly deferred; this revision does not add that requirement to scoring or claim to fix it.

Frozen executable identities, individual outcomes and limitations are in `validation/final-review.md`, `validation/semantic-boundary.md` and `validation/e2e-evidence.json`. Earlier validation and the original Astra/high trajectory reward remain historical; the saved answer is still rejected for its missed Qwen3-VL analytical estimate.

The original [Astra/high trajectory](https://github.com/ouycc/ai-infra-bench/blob/08ee4f8/trajectories/vllm-multimodal-encoder-cache-accounting/gpt-6-astra-high-20260912/pr8-gpt-6-astra-high-once.zip) and its reassessment are described in `validation/attached-trajectory-review.md`.
