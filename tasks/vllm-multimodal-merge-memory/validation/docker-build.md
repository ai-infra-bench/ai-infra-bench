# Image build and validation (1.3.0)

Built on A100 validation host on 2026-09-18 (Asia/Shanghai), using the pinned official donor, exact Base checkout, and offline hash-pinned test-tool wheels. The source-fetch stage uses the complete pinned Alpine Git image; this fixes missing HTTPS libraries when running its Git inside Ubuntu. The final image retains local Git operations and no remote.

Image: `sha256:9b8b0bfbce07832a29b5831c05726ca795f00eface39d678b9a9aea20646d51b` (11,863,163,512 bytes). Tag: `ai-infra-bench/vllm-multimodal-merge-memory:hardening-1.3.0`. This is a local image ID, not a published registry manifest digest. Build used host networking because Docker default build DNS was unavailable. Runtime validation used disabled networking.

Agent-identity audit passed: exact Base HEAD, clean source, no remotes/refs/reflogs or unreachable future objects, Oracle commit absent, private task files absent, active imports from `/workspace/repo`. The installed donor's related merge source still uses the old masked-scatter implementation. This is a focused material-leak audit, not a claim that every donor file is historically identical to Base. Native donor limitations remain documented in the lock README.

Offline agent-side upstream pytest smoke: 4 passed, 16 warnings. GPU runtime: PyTorch 2.10.0+cu129, NVIDIA A100-SXM4-40GB. Final matrix: 18/18 expected outcomes, including three Oracle and two alternative successes; each successful invocation completed 26 authenticated checks. Independent noncontiguous/zero/singleton challenges passed for both implementations.

Raw commands, input hashes, build output, allocator observations and failure traces are retained in `hardening-evidence.zip`. Formal Harbor results and their input checksums are recorded separately in `e2e-evidence.json`. Older build records are historical only.
