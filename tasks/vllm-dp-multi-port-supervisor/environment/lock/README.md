# Environment lock

This environment packages survey item `vllm__pr__40841` at the exact base
revision. Final measured image/build facts are recorded in
`validation/docker-build.md`.

## Source

- Upstream: `https://github.com/vllm-project/vllm.git`
- PR: `https://github.com/vllm-project/vllm/pull/40841`
- Issue: `https://github.com/vllm-project/vllm/issues/40814`
- Base commit: `9b9d5dbaab852a1c615fe83a7f92881d353503db`
- Base commit date: `2026-05-21T14:28:34Z`
- Base subject: `[CI] Fix CPU tests failing on tl.exp2 import (#43311)`
- Head commit inspected: `d5ed61238528c4b753bceb761db91318b0d442fb`
- Exact base codeload archive SHA-256:
  `cc81853110ee854c6c64cbfc9bca8d75887d48ea6bc27c38f63131ce0a71f1f7`
- Canonical forced-add source tree: `94c86336cf2ea962766d00bb389d43a4d6aaf697`
- Runtime Git: one synthetic commit, branch `benchmark-base`, no remote

The base falls after v0.21.0 (published 2026-05-15) and before v0.22.0
(published 2026-05-29). The Dockerfile therefore uses the official v0.21.0
amd64 image manifest by digest. Exact base Python sources replace the release
sources; native/generated artifacts come from the official donor because the
PR changes only Python frontend orchestration and tests.

## Base image and runtime

- Image: `vllm/vllm-openai:v0.21.0`
- amd64 manifest digest / donor image ID:
  `sha256:4ac9b7c6dabc3ec762c0edef4e9245abe98373844da91cc53ee42e5c58280c5b`
- Donor image size: `8,669,305,249` bytes
- Python: 3.12
- vLLM donor version: 0.21.0
- PyTorch: `2.11.0+cu130`
- CUDA reported by PyTorch: 13.0
- Accelerator probe: NVIDIA A100-SXM4-40GB, physical GPU 2,
  UUID `GPU-3815a178-ad22-4b81-5669-0533760a7e6b`
- Runtime user: `agent` (UID 1000)
- Runtime network: disabled with `--network none`
- `VLLM_TARGET_DEVICE`: not set

The build layer adds the following exact packages from Ubuntu 22.04:

- `git=1:2.34.1-1ubuntu1.17`
- `git-man=1:2.34.1-1ubuntu1.17`
- `liberror-perl=0.17029-1`

The copied donor artifact whitelist observed in the built image is:

```text
_C.abi3.so
_C_stable_libtorch.abi3.so
_flashmla_C.abi3.so
_flashmla_extension_C.abi3.so
_moe_C.abi3.so
_version.py
cumem_allocator.abi3.so
third_party/deep_gemm/_C.cpython-310-x86_64-linux-gnu.so
third_party/deep_gemm/_C.cpython-311-x86_64-linux-gnu.so
third_party/deep_gemm/_C.cpython-312-x86_64-linux-gnu.so
third_party/deep_gemm/_C.cpython-313-x86_64-linux-gnu.so
third_party/deep_gemm/_C.cpython-314-x86_64-linux-gnu.so
vllm_flash_attn/_vllm_fa2_C.abi3.so
vllm_flash_attn/_vllm_fa3_C.abi3.so
```

There is no model, tokenizer, dataset, or Kubernetes asset in the image. Build
networking is used only for the pinned Git packages; the exact source archive
was served from A100 loopback after its host-side SHA-256 was recorded.

## Verification scope

No reproduction or verifier code is copied into this Agent environment. The
runtime-mounted hidden verifier uses the production supervisor/process launcher
with two real spawned HTTP children and three loopback ports. It checks
aggregate readiness and child-crash cleanup without source-text inspection,
model downloads, or Kubernetes. Full Kubernetes routing, multi-node rank
assignment, and real model serving remain outside the task.
