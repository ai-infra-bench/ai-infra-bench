# Semantic boundary — vllm-moe-permute-batch-scaling

expert routing and FP8 storage payload -> freshly rebuilt native _moe_C.moe_permute -> exact offsets/mappings/payload/sentinels and public A100 latency/scaling limits

## Components executed for real

- Actual A100 kernels
- Candidate _moe_C rebuilt from candidate sources and staged with recorded SHA256
- Public native operator with correctness before timing
- Actual CUDA event timing

## Allowed substitutions and their limits

- Synthetic routing and payload bytes replace upstream model/router execution. Expert count, top-k, hidden width, storage type, alignment and balanced routing are preserved.
- Full MoE network, serving HTTP and tokenizer are outside the permutation/timing boundary.

For performance tasks, workload dimensions that influence latency remain fixed
to the public timing contract. A different valid correctness input does not
establish performance equivalence. Fresh independent cases exercise the same
production boundary; they do not replace the production implementation.

## Coverage

- Nine token counts times aligned/unaligned modes: 18 correctness cases covering exact offsets, inverse/permuted maps, expert ranges, byte payload and sentinels.
- Seven public timing sizes plus two diagnostic sizes. Only public 4096 latency and 4096/512 ratio determine numerical performance acceptance.
- 64 experts, top-k 6, hidden 2048, FP8 E4M3 storage, alignment 128; 20 warmups, 50 iterations, five repeats.
- Parent validates sample completeness, positivity/finiteness, timing protocol and recomputes medians/ratio; there is no unmeasured +/-5% condition.
- Different correct CUDA scaling implementation, incorrect linear scan, immediate/delayed native exits and root-startup control.

Independent routing/input variation executes freshly rebuilt native code and checks correctness plus the public workload limits.

## Cutoff and provenance

Exact Base/history and candidate native source. Torch/CUDA and native build inputs are locked; unrelated model/tokenizer behavior does not determine these operator results.

See `e2e-evidence.json` for actual run identities and `final-review.md` for the
current review outcome. Earlier build notes are historical observations.

Eight additional FP16 correctness cases use 64/1023/1024/1025 experts, seven tokens, hidden size 128, top-k 2 and both alignment modes. Every output buffer, including untouched padding, is compared against CPU grouping; the trusted stdlib parent independently derives the full-buffer digests. The timing workload and gates are unchanged. The expert-count-cap control changes only a legal-input rejection in the otherwise-correct Oracle. It is a diagnostic control, not a complete replay of the missing Opus final archive.

The routing IDs in the eight expert-count cases are distinct, so exact map comparisons do not prescribe tie ordering among equal expert keys.
