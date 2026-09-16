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

For performance tasks, workload dimensions that influence latency remain fixed to the public timing contract. A different valid correctness input does not establish performance equivalence. Fresh independent cases exercise the same production boundary; they do not replace the production implementation.

## Coverage

- Thirty-two correctness cases: nine token counts times aligned/unaligned modes (18), four expert counts times both modes (8), and three expert-partition routing patterns times both modes (6). Correctness FP8 inputs include all 256 byte encodings.
- Seven public timing sizes plus two diagnostic sizes. Only public 4096 latency and 4096/512 ratio determine numerical performance acceptance.
- 64 experts, top-k 6, hidden 2048, FP8 E4M3 storage, alignment 128; 20 warmups, 50 iterations, five repeats.
- Parent validates sample completeness, positivity/finiteness, timing protocol and recomputes medians/ratio; there is no unmeasured +/-5% condition.
- Different correct CUDA scaling implementation, incorrect linear scan, immediate/delayed native exits and root-startup control.

Independent routing/input variation executes freshly rebuilt native code and checks correctness plus the public workload limits.

## Cutoff and provenance

Exact Base/history and candidate native source. Torch/CUDA and native build inputs are locked; unrelated model/tokenizer behavior does not determine these operator results.

See [tests-hardening.md](tests-hardening.md) for the current validation status and [README.md](README.md) for evidence locations. Earlier run identities and reviews describe previous task revisions and have been removed from this directory; see the README for the local recovery backup.

Eight additional FP16 correctness cases use 64/1023/1024/1025 experts, seven tokens, hidden size 128, top-k 2 and both alignment modes. Valid payload rows and all required mapping/sentinel outputs are compared against CPU grouping; the trusted stdlib parent independently derives the digests. Version 1.3.4 excludes unused payload rows and unaligned m_indices, matching the other correctness groups. The timing workload and gates are unchanged. The expert-count-cap control changes only a legal-input rejection in the otherwise-correct Oracle. It is a diagnostic control, not a complete replay of the missing Opus final archive.

The routing IDs in the eight expert-count cases are distinct, so exact map comparisons do not prescribe tie ordering among equal expert keys.

Version 1.3.3 adds mixed, all-local and all-remote routing through a noncontiguous global-to-local expert map. Local destinations must bijectively fill each expert's payload rows, forward and inverse maps must round-trip, and local FP8 payloads must match byte for byte. Remote inverse destinations retain the aligned terminal sentinel or occupy the unaligned skipped range. Canonical output digests allow different within-expert ordering. These cases do not constrain unused payload bytes or unaligned `m_indices`. See `tests-hardening.md` for validation status; older GPU evidence does not certify this revision.
