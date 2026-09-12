# Curator source-provenance audit (out-of-image)

The former in-image `environment/source_gate.py` was removed so no agent-visible
provenance gate ships in the image (canonical review standard). The Base/source
provenance it enforced is now a **curator audit performed outside the image**,
before build and during review. Run these checks against the byte-locked
candidate source tree (the `/app` extraction of the digest-locked
`VLLM_SOURCE_URL` tarball, base commit `dc917cceb877dfd13f98c538c4c96158047d98bd`).

## Expected file hashes (sha256)

| path | sha256 |
|------|--------|
| `CMakeLists.txt` | `4b0ea617c2e85e74c753b8a4451f2bc0caeb00b354d832c207dff84fbd38cacb` |
| `requirements/cuda.txt` | `0b5b8a88c16ef7d371f30b6db61de17b49c251cda4b785213ecfc2b935f9c1c7` |
| `csrc/moe/moe_permute_unpermute_op.cu` | `dfd8d82095c87a020ec099a31aecb18319c88271c010fdd69952424ece2d2fa1` |
| `csrc/moe/permute_unpermute_kernels/moe_permute_unpermute_kernel.h` | `36f006c95cb687fcd557ea5e9cd7038619c6e5a1f10b09fd9ece9282e3c7ff24` |
| `csrc/moe/permute_unpermute_kernels/moe_permute_unpermute_kernel.inl` | `72d01a06ad565226ba680dbbb1fcd20bd3177fb3b9fa4386ebdd98a4d1906e16` |

## Structural assertions (pre-PR Base confirmed)

- `csrc/moe/moe_permute_unpermute_op.cu` contains `moe_permute kernels require at least CUDA 12.0`
- `..._kernel.inl` contains `extern __shared__ int64_t smem_expert_first_token_offset[]`
- `..._kernel.inl` does NOT contain `aligned_expert_first_token_offset` (post-PR symbol)

## Provenance facts

- `base_sha`: `dc917cceb877dfd13f98c538c4c96158047d98bd`
- `canonical_git_tree`: `89beecb205e031cbb82e2eea9d2cd0f350135b8c`
- `cuda_minimum`: `12.0`
- `pre_pr_linear_expert_scan_present`: true
- `structural_base_confirmed`: true

These are curator/reviewer checks. They are intentionally NOT reproduced by any
agent-visible script inside the image.
