# Semantic boundary — 1.2.9

Prompt windows + media embedding rows -> real scheduler admission and full-item
reservation -> encoder output writes -> ordered main/shifted gather, cache hits
and eviction -> observable rows, masks and available capacity.

The new shifted chain calls the real scheduler with shift_computed_tokens=1,
then observes both [a,b) and [a+1,b+1) from the same cache. It stays inside the
37-token prompt. Media geometry, model embedding production and batching are
controlled; scheduling, reservation, cache writes and selection remain candidate
code. The independent challenge uses a different offset/mask and six shifted
windows; it passed on Oracle and five valid alternatives in the fixed image.

Video geometry -> real Qwen3VLProcessingInfo.get_max_video_tokens and inherited
modality mapping -> profiler/registry -> compute_encoder_budget and
MultiModalBudget -> scheduler and runner capacities. Geometry returns 16/48
actual rows; the one-token decoder batch floor remains in force. This supplements
the existing dummy-profile fallback path. Model inference is outside this CPU
boundary. No particular new accessor name is required from the candidate.

The trusted root parent preloads the suite without candidate imports, forks,
configures a native completion channel and drops the worker to nobody. Candidate
stdout is diagnostic only. The root parent compares all stages and fresh values;
only the root shell writes reward. Native completion requires an offline C
compiler and active Python headers; availability and compilation in the pinned image were verified on A100.
This is scoped completion authentication, not arbitrary-code sandboxing.

Local extracted-method probes use real torch but simplified surrounding objects.
Linux entrypoint smoke uses an import-only torch stub, so it proves completion
and reward behavior only. Neither substitutes for full vLLM/Harbor acceptance.

A100 final validation used the actual pinned image, with full suite execution.
25 rewards and 12 positive challenge results matched expectations. Geometry
for the direct video cases was aligned with the controlled encoder row counts.
Raw results are archived separately from narrower local probes and earlier
driver failures. No Harbor orchestration execution is claimed.
