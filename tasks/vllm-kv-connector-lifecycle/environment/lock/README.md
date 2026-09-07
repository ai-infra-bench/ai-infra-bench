# Environment lock

This environment packages the survey base state for `vllm__pr__39832`.

## Source

- Upstream repository: `https://github.com/vllm-project/vllm.git`
- Survey base commit: `f80aa53c9dc2273a19a6855092069db7e1306fff`
- Canonical root tree: `2af517bd7880077a9fed9a39dc0e8b1e244a48b1`
- Commit date: `2026-05-09T21:46:52Z`
- Commit subject: `[Refactor] Nixl util using lazy init (#41392)`
- Acquisition: SHA-256-checked codeload archive of the exact commit
- Archive SHA-256:
  `a2923ff0ff39b1c32b18ba6eb6255c646e2fc49280552d0637d522e9434baebe`
- Runtime Git state: one synthetic commit, branch `benchmark-base`, no remote

The base falls after v0.20.1 (published 2026-05-04) and before v0.20.2
(published 2026-05-10). The official v0.20.1 image is therefore the newest
release image available at the source cutoff. The candidate and release both
use the PyTorch 2.11 / CUDA 13 family.

## Base image and runtime

- Image: `vllm/vllm-openai:v0.20.1`
- Repository digest / local image ID:
  `sha256:9eff9734a30b6713a8566217d36f8277630fd2d31cec7f0a0292835901a23aa4`
- Local image size: `8,230,603,218` bytes
- Platform: `linux/amd64`
- Python: `3.12.13`
- PyTorch: `2.11.0+cu130`
- CUDA reported by PyTorch: `13.0`
- Accelerator probe: NVIDIA A100-SXM4-40GB, GPU 7
- Constructor workload: CPU-only; it creates no model or CUDA tensor
- Runtime network: disabled with `--network none`
- `VLLM_TARGET_DEVICE`: not overridden

The exact source tree supplies all Python code. Native extensions and the
generated `_version.py` are copied from the digest-pinned v0.20.1 image into
that tree. `native-paths.txt` is the machine-readable whitelist; the Dockerfile
rejects missing, symlinked, non-ELF, or additional shared objects. The locked
paths are:

```text
_C.abi3.so
_C_stable_libtorch.abi3.so
_flashmla_C.abi3.so
_flashmla_extension_C.abi3.so
_moe_C.abi3.so
_version.py
cumem_allocator.abi3.so
third_party/deep_gemm/_C.cpython-312-x86_64-linux-gnu.so
vllm_flash_attn/_vllm_fa2_C.abi3.so
vllm_flash_attn/_vllm_fa3_C.abi3.so
```

This is a same-release native binding, not a post-cutoff donor. Future Python
site-packages remain behind `/workspace/repo` on `PYTHONPATH`; runtime probes
confirm both `vllm` and `vllm._C` resolve from the candidate tree.

Packages added or confirmed by the environment layer are:

- `ca-certificates=20260601~22.04.1`
- `git=1:2.34.1-1ubuntu1.17`
- `git-man=1:2.34.1-1ubuntu1.17`
- `libcurl3-gnutls=7.81.0-1ubuntu1.26`
- `liberror-perl=0.17029-1`

Build networking is needed only for apt and the exact source archive. The
runtime workload has no model, tokenizer, dataset, or network dependency.

## Harbor boundary

No instruction, solution, public locator, or verifier is copied into the
image. Those assets are outside the `environment` build context and are mounted
by Harbor. The hidden verifier exercises the real KV-transfer initialization
consumer, factory/base lifecycle, and connector-internal `TypeError` boundary;
it does not inspect source text.
