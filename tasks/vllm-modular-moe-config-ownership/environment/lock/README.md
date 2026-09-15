> Historical environment-build record. Hardware indices and verifier descriptions
> below describe the earlier build validation, not the current review. Current
> hardware assignment, behavioral coverage and measured results are recorded in
> `validation/review-report.md` and `validation/e2e-evidence.json`. This README is
> not copied by the Dockerfile and does not change the image build inputs.

# Environment lock

This environment packages the survey base state for `vllm__pr__30282`.

## Source

- Upstream repository: `https://github.com/vllm-project/vllm.git`
- Survey base commit: `e2ed238885be6af358be1851cd43105b7d036c49`
- Commit date: `2025-12-15T00:33:41Z`
- Commit subject: `Revert "[Fix]Load kv-cache dtype from hf_quant_config.json automatically" (#30653)`
- Acquisition: SHA-256-checked codeload archive of the exact commit
- Archive SHA-256:
  `b3abf42611917bf610cfe2c543961ba38a7b9e6e1a3a6774287d5e3f4aa932c2`
- Canonical upstream root tree:
  `75491c7db4e75808a6bfe937322d3839a619ecdf`
- Runtime Git state: exact upstream Base at `HEAD` with parent history, branch
  `benchmark-base`, and no remote, remote refs, tags, reflogs, fetch metadata,
  shallow boundary, unreachable objects, or known future commit

The archive tree is checked against the exact upstream Base index after the
sanitized `.git` directory is copied from a Base-only history stage. Ignored
generated metadata and native artifacts are installed only after that check.

The base falls after v0.12.0 (published 2025-12-03) and before v0.13.0
(published 2025-12-19). v0.12.0 is the latest official release at the source
cutoff. Both the source and release pin PyTorch 2.9.0; the official image uses
the CUDA 12.9 build.

## Base image and runtime

- Image: `vllm/vllm-openai:v0.12.0`
- Repository digest / local image ID:
  `sha256:6766ce0c459e24b76f3e9ba14ffc0442131ef4248c904efdcbf0d89e38be01fe`
- Local image size: `8,931,755,554` bytes
- Platform: `linux/amd64`
- Python: `3.12.12`
- PyTorch: `2.9.0+cu129`
- CUDA reported by PyTorch: `12.9`
- Accelerator: NVIDIA A100-SXM4-40GB, GPU 0
- Runtime network: disabled with `--network none`
- `VLLM_TARGET_DEVICE`: not overridden

The exact base archive supplies all Python code. Generated `_version.py` comes
from the digest-pinned v0.12.0 runtime image. That release's extensions cannot
load the exact candidate `_custom_ops.py`: the candidate registers
`_C::cutlass_encode_and_reorder_int4b_grouped`, which is absent from the v0.12
binary. The failure occurs before the verifier workload, while unmodified v0.12
imports its own `_custom_ops` and allocates on A100 successfully.

Native extensions therefore come from a separate, digest-pinned v0.13.0 stage:

- Image: `vllm/vllm-openai:v0.13.0`
- Digest / local image ID:
  `sha256:d623253f2ba246378421c9642e20885e65257f38418ff26d48c81aea1702521b`
- Local image size: `8,944,175,827` bytes
- Published: `2025-12-19`, four days after the source cutoff
- PyTorch/CUDA: `2.9.0+cu129` / `12.9`, matching the candidate's Torch pin and
  the runtime image family

The donor stage contributes only the seven explicit relative paths and hashes
in `native-v0.13.0.sha256`. The build verifies each is a regular, non-symlink
ELF `.so`, verifies all hashes, and asserts the staging directory contains no
other object. Its `_version.py`, Python modules, and site-packages directory are
not copied or placed on `PYTHONPATH`; final staging is removed. This is a
post-cutoff ABI approximation and will be accepted only if candidate-path
imports and the real Triton MoE workload pass.

Packages added or confirmed by the environment layer are:

- `ca-certificates=20260601~22.04.1`
- `git=1:2.34.1-1ubuntu1.17`
- `git-man=1:2.34.1-1ubuntu1.17`
- `liberror-perl=0.17029-1`

## Harbor verifier boundary

The verifier is deliberately outside the Agent image. It first executes the
no-config compatibility entry through a real batched CUDA Triton MoE, then
checks explicit configuration identity, ordinary versus DP+EP behavior,
numerical preservation, two production consumers, and rejection of the
superseded keyword. The image contains neither tests nor solution assets.
