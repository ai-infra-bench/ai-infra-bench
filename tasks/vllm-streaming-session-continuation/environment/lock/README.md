> Historical environment-build record. Hardware indices and verifier descriptions
> below describe the earlier build validation, not the current review. Current
> hardware assignment, behavioral coverage and measured results are recorded in
> `validation/review-report.md` and `validation/e2e-evidence.json`. This README is
> not copied by the Dockerfile and does not change the image build inputs.

# Environment lock

This environment packages the survey base state for `vllm__pr__28973`.

## Source

- Upstream repository: `https://github.com/vllm-project/vllm.git`
- Survey base commit: `0118cdcc02ae16a137645e2289bf41f5e3da9d80`
- Canonical root tree: `eb2267901a78dcd021c505f5a6bd50ccc6632a9b`
- Commit date: `2026-01-23T22:53:10Z`
- Commit subject: `[fix] add VLLM_OBJECT_STORAGE_SHM_BUFFER_NAME to compile factors (#32912)`
- Acquisition: SHA-256-checked codeload archive of the exact commit during
  image build (`75b2632ec1ea5f92539b9c5f6a7e3cd3357874f04cfd6953c9ae851f1b992957`)
- Runtime Git state: exact upstream Base at `HEAD` with its parent history,
  branch `benchmark-base`, no upstream remote, remote refs, tags, reflogs,
  fetch metadata, shallow boundary, or future objects

The base falls after v0.14.0 and before v0.14.1. The official v0.14.0 image is
the newest release image available before the survey base and uses the same
PyTorch 2.9.1 and CUDA 12.9 family pinned by the candidate source. A later
image is not used because installed post-base Python code could leak the
target implementation.

The candidate source added native operator bindings after v0.14.0, so its
Python `_custom_ops` module cannot bind against the v0.14.0 extension. The
adjacent v0.14.1 native extension was tested but still did not provide the
required operator. A multi-stage donor therefore uses v0.15.1 solely to
extract seven native `.so` files. No donor Python source is copied into the
final image; the final lower layers remain v0.14.0 and `PYTHONPATH` resolves
the candidate tree. This is a practical ABI bridge, but because v0.15.1 is
well after the source cutoff, it remains an explicit approximation and a
material publication risk rather than an exact source build. The donor is not
scanned recursively: `native-donor.sha256` is an explicit seven-path manifest,
and `final-native.sha256` locks those seven regular ELF objects plus v0.14.0's
generated `_version.py`. The final stage asserts the manifest and exact `.so`
count, then removes donor staging.

## Base image and runtime

- Image: `vllm/vllm-openai:v0.14.0`
- Multi-platform manifest digest:
  `sha256:1d6866b87630d94f5e0cdae55ab5abb4ce0b03fcb84d9d10612f9d518d19d4fd`
- Linux/amd64 image digest:
  `sha256:48a03c91eaa04fb7e71c77121a85e661d62de1b2207edf591aea6a05d779f9ef`
- Linux/amd64 compressed size reported by Docker Hub: `9,000,863,638` bytes
- Native-only donor: `vllm/vllm-openai:v0.15.1`
- Native donor multi-platform manifest digest:
  `sha256:8c9aaddfa6011b9651d06834d2fb90bdb9ab6ced4b420ec76925024eb12b22d0`
- Native donor Linux/amd64 image digest:
  `sha256:06f9f0d5c7cb079504615c51dab70cd18abbf609d1358b940172181ac0a92efa`
- Platform: `linux/amd64`
- Python: 3.12.12
- vLLM version metadata: 0.14.0
- PyTorch/CUDA: 2.9.1+cu129 / CUDA 12.9
- Ubuntu packages added at build time:
  - `ca-certificates=20260601~22.04.1`
  - `git=1:2.34.1-1ubuntu1.17`
  - `git-man=1:2.34.1-1ubuntu1.17`
  - `liberror-perl=0.17029-1`
- Target verifier: CPU-only (`gpus = 0`); no model or CUDA kernel is executed
- Independent native-integrity accelerator: NVIDIA A100-SXM4-40GB, GPU 7
- Runtime network: disabled with `--network none`
- `VLLM_TARGET_DEVICE`: not overridden

The build needs network access only for Ubuntu apt metadata/packages and the
exact Git commit archive. Runtime verification has no model, tokenizer,
dataset, or network dependency.

## Harbor boundary

The image contains only the exact candidate source and locked runtime
artifacts. Agent instructions, accepted solution, and hidden verifier live
outside the `environment` build context and are mounted by Harbor. The scoped
behavior is the production GPU-runner continuation path for an already cached
request, not the large PR's missing public symbol.
