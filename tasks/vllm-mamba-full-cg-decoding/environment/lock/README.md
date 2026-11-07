# Environment lock

Survey item: `vllm__pr__42430`.

## Source

- Upstream: `https://github.com/vllm-project/vllm.git`
- PR: `https://github.com/vllm-project/vllm/pull/42430`
- Linked roadmap: `https://github.com/vllm-project/vllm/issues/33702`
- Base: `737bfa3a43ce386bd1894792f3302d9f3f9d73fa`
- Base date: `2026-05-18T11:54:00Z`
- Base subject:
  `[Bugfix][Hybrid][NemotronH] Fix mamba_cache_mode=all + speculative decoding crash (#41233)`
- Head inspected: `7e6eadcf30fe8405db6eea184cd8444743316e7f`
- Base archive SHA-256:
  `4269a850e2ed7fcf4213bde48556eccdcaeca0266e4668e0ec64e3d69d785761`
- Head archive SHA-256:
  `b81a05f3fed3fd77d7cd2fe87d9df9b2f6c134d64775da623b71e590bbefdc14`
- Canonical forced-add base tree:
  `f1ee5dc01c843ebb52d20e1714a93f96ec07cb96`
- Runtime Git: one synthetic commit, branch `benchmark-base`, no remote

## Official runtime donor

- Image: `vllm/vllm-openai:v0.21.0`
- Linux/amd64 digest:
  `sha256:4ac9b7c6dabc3ec762c0edef4e9245abe98373844da91cc53ee42e5c58280c5b`
- Published: `2026-05-15T08:44:26Z`, three days before the base cutoff
- Runtime: Torch `2.11.0+cu130`, CUDA `13.0`
- Exact Git packages: `git=1:2.34.1-1ubuntu1.17`,
  `git-man=1:2.34.1-1ubuntu1.17`, `liberror-perl=0.17029-1`

Exact base Python/Triton source replaces the donor package. Only artifacts in
`native-donor.json` are copied from the ABI-compatible donor; the PR's sole
production file is Python and has no native intersection.

## Validation scope

The hidden verifier constructs real `CommonAttentionMetadata` on CUDA, uses the
real Mamba metadata builder in `CUDAGraphMode.FULL`, and invokes the production
`build_for_cudagraph_capture` path. It checks the silent classification bug:
a one-token row with prior Mamba state must be decode metadata, while a true
first-token prompt must remain prefill metadata.

This focused environment does not claim the original end-to-end setup. Full
acceptance requires a NIXL prefill/decode topology, a Mamba model, full CUDA
graphs, and paired GSM8K accuracy measurements.
