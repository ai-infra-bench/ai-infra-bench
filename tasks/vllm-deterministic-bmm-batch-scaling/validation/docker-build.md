# Docker build and A100 validation: vLLM PR #29345

> Historical v1.0 validation. Task v1.1 removes the private-symbol gate and
> changes stage/error reporting; it has not yet been rerun.
>
> Provenance supersession: task v1.2.1 now retains the exact upstream Base at
> `HEAD` with sanitized parent history. Image IDs and Git assertions below are
> historical and are not evidence for the current environment; rebuild and
> `image-check` remain mandatory.

## Status

**Environment/runtime validated; A100 kernel-level correctness and relative
performance reproduced; full-system benchmark not reproduced.**

The original PR reports an eight-GPU DeepSeek-V3.1 serving benchmark. This
validation was allocated one A100 GPU, so it does not generalize the PR's
throughput or TTFT percentages. It directly exercises the changed
`bmm_batch_invariant` function on A100 and compares base versus the official PR
patch under the same process, shapes, warmup, iterations, and rounds.

No model or dataset is required for this isolated Triton-kernel task. Inputs
are deterministic generated CUDA tensors, so model/data cache digests are not
applicable.

## Host and immutable inputs

- GPU: physical GPU 1, NVIDIA A100-SXM4-40GB
- Isolated daemon:
  `DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock`
- Daemon data-root:
  `/data/yaoyaoyao/pr34183-cuda-build/docker-data`
- Remote directory:
  `/data/ai-infra-bench/survey-builds/vllm-pr-29345`
- Final tag: `ai-infra-bench/vllm-pr-29345:base`
- Official runtime:
  `vllm/vllm-openai:v0.11.1@sha256:d5b12dfb74d605615f8b29ebafaa52294c118bcac7bc9e941785c4108fdb913a`
- Runtime image bytes: `13997461686`
- Git helper:
  `alpine/git:2.49.1@sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26`
- Exact base source: `b07555d26f4c7ad9a2d1ec45428a9d4287db612c`
- Source archive SHA-256:
  `5f5d48bb58d898d89d65bb4310b916f3472f84db0cb17f994203084e3aafce1f`
- Source archive bytes: `17447112`

All Docker commands used the isolated daemon. No prune or unrelated-image
deletion was performed. Build and runtime used `--network none`; proxy values
are host/daemon state only. `docker history --no-trunc` found no proxy host,
proxy variable, or credential-placeholder match.

## Exact-native attempt and constrained fallback

The v0.11.1 release commit is 283 commits behind the exact base, and GitHub's
compare response includes changes under `csrc/`. Therefore native ABI reuse
cannot be assumed silently.

A full exact-SHA editable native build was attempted with the official image's
nvcc, CUDA 12.9 dev packages, cmake, ninja, torch 2.9.0, and all pyproject build
dependencies:

```bash
python3 -m pip install --no-build-isolation --no-deps -e /workspace/repo
```

With Docker build networking disabled, it failed after 384 seconds during
CMake configure when `FetchContent` tried to clone CUTLASS v4.2.1. Inspection
of exact-base CMake found four additional unconditional CUDA external projects:
Triton kernels v3.5.0, FlashMLA, QuTLASS, and vLLM flash-attention. Their source
caches are not retained in the official image. Failure log:
`/data/ai-infra-bench/survey-builds/vllm-pr-29345/docker-build.log`.

The accepted constrained fallback overlays the **entire** exact-base source
tree, then fills only absent wheel/native/generated files with
`cp --no-clobber`. A `.pth` prepends `/workspace/repo`; both `vllm.__file__` and
the discoverable `vllm._C` resolve there. This is not the rejected v0.11.0
wheel plus single-file symlink construction. However `_C` originates from the
official v0.11.1 release commit, recorded in the image label:

```text
ai-infra-bench.vllm-native-origin=v0.11.1:439368496db48d8f992ba8c606a0c0b1eebbfa69
```

The evaluated code is Python/Triton JIT and PR #29345 changes no native source,
so the BMM path is directly executable. The image must not be described as a
general exact-base native build.

## Final cold build

```bash
export DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock
cd /data/ai-infra-bench/survey-builds/vllm-pr-29345/context
DOCKER_BUILDKIT=0 docker build --no-cache --network none \
  -t ai-infra-bench/vllm-pr-29345:base .
```

```text
BUILD_STATUS=0
BUILD_SECONDS=513
image ID: sha256:905933384528422b6b7958af874997d3bf5334af069cde5748c6819fa5848d1a
image bytes: 14870493633
configured user: agent
```

Log and timing summary:
`docker-build-cold-final.log` and `docker-build-cold-final-summary.txt` in the
remote task directory.

Build-time module discovery printed:

```text
0.11.1 /workspace/repo/vllm/__init__.py /workspace/repo/vllm/_C.abi3.so
```

GPU runtime then actually imported `_C` and reported:

```text
True NVIDIA A100-SXM4-40GB
/workspace/repo/vllm/__init__.py
/workspace/repo/vllm/_C.abi3.so
```

The final container runs as UID/GID 1000 `agent`. Its writable repository has
one synthetic commit, zero remotes, and clean status; a disposable write smoke
created `.agent-write-smoke`, which `git status` correctly reported as
untracked.

## Correctness and batch invariance

Both base and patched implementations passed six cases:

| dtype | `(B, M, N, K)` shapes |
|---|---|
| float16 | `(1,17,19,23)`, `(5,33,29,41)` |
| bfloat16 | `(3,31,37,43)`, `(8,64,48,80)` |
| float32 | `(2,15,21,27)`, `(4,32,24,40)` |

For every case:

- one batched call was bitwise identical (`torch.equal`) to concatenated B=1
  calls;
- `out=` returned the exact supplied storage and was bitwise identical to the
  normal result;
- the result was numerically close to `torch.bmm` at 0.02 relative/absolute
  tolerance. The loose numerical check accounts for the deterministic Triton
  reduction order versus cuBLAS/TF32; bitwise batch invariance is the hard gate.

## A100-local relative performance

Timing uses bf16, 5 warmups, 20 iterations per sample, five samples, and CUDA
events. Values below are medians from the final cold-built image. The official
PR diff was mounted from outside the image and applied only in a disposable
`--network none` container; its SHA-256 is
`117d496bfbece47e1c4885b49b6fb6abe8697aaa1006a0933acd1588670c1c7c`.

| `(B, M, N, K)` | base ms | patched ms | A100 speedup |
|---|---:|---:|---:|
| `(8,512,512,2560)` | 0.6225 | 0.0912 | 6.83x |
| `(32,512,512,2560)` | 2.3986 | 0.3863 | 6.21x |
| `(8,1280,1280,2560)` | 0.6602 | 0.4143 | 1.59x |

Both runs printed `BMM_PROBE=PASS`. Raw outputs are retained as
`bmm-base-final.log` and `bmm-patched-final.log`. These are A100-local
microbenchmark results, not H20 anchors and not end-to-end throughput/TTFT
claims.

## Construction-guide feedback

- A pure Python/Triton PR can still sit on a base with native drift. Compare
  the exact base to the release-native commit; either rebuild exact native or
  label and document the fallback origin and scope explicitly.
- For exact offline native builds, audit CMake `FetchContent` dependencies
  before starting. Pin/cache every external source archive, including nested
  submodules, or classify the native build as blocked rather than discovering
  network dependencies late.
- Performance baselines are hardware-local. Never score A100 candidates
  against frozen H20 absolute milliseconds; rerun base and candidate with the
  same process, shapes, warmups, iterations, and aggregation.
- Performance tasks need correctness as a hard gate across dtype, non-aligned
  shapes, batch partitions, and `out=` behavior. A single large bf16 shape is
  insufficient.
- With the classic Docker builder and a large base, package small helper files
  into one tar in the helper stage and copy it once. Multiple `COPY --from`
  instructions cause repeated expensive base-layer commits.
