I am profiling the native `_moe_C.moe_permute` aligned-routing path on an A100.
Its results are correct, but latency rises disproportionately as the routed
token batch grows. Please diagnose and remove that scaling bottleneck without
changing the operator's observable behavior.

Preserve exact expert offsets, inverse and permuted mappings, expert ranges,
payload bytes, and sentinel handling for both aligned and unaligned cases. The
internal algorithm, helper names, and kernel decomposition are not prescribed.

Work in `/app`. Rebuild the focused native `_moe_C` extension from the repo
(the CUDA toolchain, CUTLASS sources, and cmake build flow are available in the
environment) and use the rebuilt candidate for correctness and timing.
The timed workload uses 64 experts, top-k 6, hidden width 2048, FP8 E4M3
payload storage, and expert ranges aligned to 128 rows. For reproducible profiling, distribute
routes cyclically across experts; one such pattern assigns token t and top-k
slot k to expert (17*t + 7*k) mod 64.
On one NVIDIA A100-SXM4-40GB, use 20 warmups, five trials, and 50
iterations for token counts `1, 32, 128, 512, 1024, 2048, 4096`. Correctness
must pass first. The median latency at 4096 tokens must then be below `250 us`,
and the `4096/512` latency ratio must be below `3.5`. Record the
candidate extension's SHA-256 and verify its cold-import path before timing.
