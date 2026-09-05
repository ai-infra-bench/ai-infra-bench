# Environment lock

This environment packages the survey base for `vllm__pr__39337`.

## Source cutoff

- Upstream repository: `https://github.com/vllm-project/vllm.git`
- Survey base: `c7560af42487b1570c4e6f4cea5df1605a4d59fc`
- Canonical root tree: `00dedbf38a187d7be24007ab92ce0158c646d024`
- Commit date: `2026-05-14T14:12:30Z`
- Commit subject: `[RFC] Replace shared-memory routed experts with ModelRunnerOutput transfer and HTTP support (#39568)`
- Archive SHA-256: `b88f58e5acd39d0b0c98e008635d48fcde8ed1b0d4d6c698a9b4fa59aa44352f`
- Runtime Git: one synthetic commit, branch `benchmark-base`, no remote

The closest official release available before this cutoff is v0.20.2,
published 2026-05-10. It uses the same PyTorch 2.11 / CUDA 13 family pinned by
the candidate source.

## Base image and native binding

- Image: `vllm/vllm-openai:v0.20.2`
- Repository digest: `sha256:70a098d90dbab428a001d9e852fc0fc8d67da5beb03e7851a22247653bf35923`
- Local image size: `8,231,364,540` bytes
- Python: 3.12
- PyTorch: `2.11.0+cu130`
- Accelerator probe: NVIDIA A100-SXM4-40GB, GPU 0
- `VLLM_TARGET_DEVICE`: not overridden

Exact base Python source is first on `PYTHONPATH`. Ten release artifacts are
copied into that tree only after the canonical synthetic commit: nine regular
ELF shared objects plus generated `_version.py`. Their explicit relative paths
and SHA-256 hashes are locked in `native.sha256`; the Dockerfile rejects a
missing, symlinked, non-ELF, additional, or hash-mismatched `.so`. No release
Python directory or staging directory is added to `PYTHONPATH`.

This is a nearest-pre-cutoff source/native approximation, not an exact build of
the survey SHA. The official image passed `vllm._C`, `vllm._custom_ops`, and a
real A100 CUDA allocation before overlay. The target workload itself is
host-side configuration logic and executes no model/native kernel.

Build networking is needed only for apt and the digest-checked source archive.
Runtime is offline and has no model, tokenizer, dataset, or external service
dependency.

The environment layer installs the Ubuntu 22.04 packages needed to synthesize
the Git state:

- `git=1:2.34.1-1ubuntu1.17`
- `git-man=1:2.34.1-1ubuntu1.17`
- `liberror-perl=0.17029-1`

## Verification scope

No reproduction or verifier code is copied into this Agent environment. The
runtime-mounted hidden verifier dynamically executes the real environment
accessor, `VllmConfig` selection/validation methods, and the production
GPUWorker constructor. It checks explicit `0/1`, unset tri-state, the synthetic
model matrix, unsupported fallback, and consumer propagation without source
inspection or model weights. Scheduler and Distributed FlashInfer are excluded
from the focused Oracle.
