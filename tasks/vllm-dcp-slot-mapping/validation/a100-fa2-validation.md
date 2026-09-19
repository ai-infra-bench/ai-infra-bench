# v1.8.6 A100 / FlashAttention 2 validation — 2026-09-19

## Scope

This validation addresses the hardware mismatch discovered after the earlier H20 calibration. The task declares two A100 GPUs; A100 selects FlashAttention 2, while H20 selects FlashAttention 3 by default. The previous Oracle stopped at 10/24 checkpoints on A100 with a device-side index assertion in the verifier's first real-backend eager case.

The failure had two layers. The component verifier directly submitted zero-context and mixed zero/nonzero-context rows to the FA2 paged-varlen kernel. The production Oracle also submitted the same unsupported shapes, and its single-request decode graph captured a zero-context query-only branch that could not gain context attention during replay.

## Revision

The v1.8.6 Oracle skips DCP context attention when the whole batch has no prior context, separates FA2 decode and context-bearing prefill rows from zero-context pure prefill rows, uses stable workspace-backed outputs for graph capture, and gives DCP graph capture a small legal context so the captured branch matches real decode execution.

The verifier preserves the same behavioral expectations, checkpoint count, numerical thresholds, and full-engine matrix. Its local FA2 arithmetic fixture evaluates mixed prefills per request instead of invoking an unsupported batched kernel shape. Full TP2/DCP2 engine cases still exercise production batching, KV writes, collectives, eager execution, CUDA graph replay, NHD/HND layouts, interleave values 1 and 2, and independent CPU reference comparisons.

## Results

The final run used the pinned image `sha256:462fc769cac14468d0c1a7128eb17116c728e12e31efaee14b9ea7fd6c3e9868`, Base `be3af2d29e2507f32b2190fe015cd6609b348caa`, and two NVIDIA A100-SXM4-40GB GPUs. The official verifier entrypoint `/tests/test.sh` ran inside the frozen environment.

- Required checkpoints: 24
- Completed checkpoints: 24
- Failures: 0
- Reward: 1
- Worker exit status: 0
- Unmodified Base: reward 0, 2/24 checkpoints, worker exit status 256
- Full-engine combinations completed: 14
- FlashAttention NHD eager maximum log-probability error: 0.0024518966674804688
- FlashAttention NHD graph maximum log-probability error: 0.0024518966674804688
- Final FlashAttention HND/interleave-1 graph maximum log-probability error: 0.0024700164794921875
- Additional FlashAttention NHD chunked-prefill eager maximum log-probability error: 0.0023326873779296875
- Additional FlashAttention NHD chunked-prefill graph maximum log-probability error: 0.0023326873779296875
- Numerical threshold: absolute tolerance 0.02, relative tolerance 0

Before the graph-capture metadata correction, the isolated A100 graph diagnostic failed 252/256 vocabulary entries with maximum absolute error 1.844747543334961. After capture was changed to include legal DCP context, the same case passed at 0.0024518966674804688. This before/after isolates the graph control-flow problem rather than hiding it with a wider tolerance or eager fallback.

## Evidence boundary

This was a direct execution of the official verifier in the pinned task image, not a Harbor wrapper run. It provides fresh v1.8.6 Oracle and unmodified Base results. Historical Oracles, saved model answers, curated alternatives, security probes, and the complete control matrix were not rerun. Existing H20 results remain evidence for the default FA3 path and are not relabeled as A100 validation. This run does not certify throughput, HTTP serving, production-model quality, every supported model shape, grading trust, or the existing native-donor dependency boundary.

## Integrity

- Instruction SHA256: `2884d6c2f1e6cb53c8d0e6be7765017df43e51d89d013ee479ed716d7d81a25a`
- Main verifier SHA256: `4caf84170c53adab508b3654cae3966f6769b6ad357016f428bb19cdbc8be1b2`
- Distributed verifier SHA256: `c32b446a9ab2f9dd51ce0f874b1487b617c575d49a5739d568f4b8f554872a0a`
- `task.toml` SHA256: `4968625c4c4f84ede15bca74ea6a681acd2016068165dba6e9472663ed5a2d75`
- Oracle patch SHA256: `f18207a7d105c3199dbe2683a99e80541d3408add8aa9ac7dfc76bf4d93567fd`
- Local full verifier log SHA256: `15cbf685b5826f9c7faacd8c70d8abb379fbcc32c323f79ed27acd2321be8911` (2.5 MB local artifact; not committed)
- Local Base verifier log SHA256: `07567f4ab76370c5ab1f3ea9fb7c81a7c8c80c21126de5e0cde9e1e12df743ab` (local artifact; not committed)
- Additional FA2 chunked-prefill eager log SHA256: `d66578ccbb6622b10500ca75661599623f5c17f5f2cbb005bbce4dbf11e53b9d` (local artifact; not committed)
- Additional FA2 chunked-prefill graph log SHA256: `b4870861f6e7c4d0f3b38f2063a648c0c88f9950bbf7ccf33dba29a1bdbcb2b9` (local artifact; not committed)
