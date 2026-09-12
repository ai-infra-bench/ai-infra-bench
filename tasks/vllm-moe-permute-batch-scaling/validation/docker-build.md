> Current local review and execution status: see [final-review.md](final-review.md)
> and [e2e-evidence.json](e2e-evidence.json). Everything below is retained as
> historical build evidence; old "not rerun" statements describe that snapshot.

# Docker build and A100 baseline validation

> Historical v1.0 validation. Task v1.1 turns focused rebuilding and
> source/native/import digest capture into mandatory evaluator behavior. The
> revised pipeline has not yet been rerun; the prior Agent patch did pass after
> the equivalent manual focused rebuild.
>
> Provenance supersession: task v1.3.1 now retains the exact upstream Base at
> `HEAD` with sanitized parent history. Image IDs and Git assertions below are
> historical and are not evidence for the current environment; rebuild and
> `image-check` remain mandatory.

## Status

`ENVIRONMENT-READY` with an exact-source `_moe_C` build and a correctness-
gated, model-free A100 performance baseline. The paired oracle confirms that
the benchmark is sensitive to the real PR. A production hidden verifier still
needs an independent trusted runner and a repeated-timing acceptance policy.

## Target

- Remote host: `bm-baai-dx-zone1-d-a100-40g-2-106`
- Physical GPU: index 2, NVIDIA A100-SXM4-40GB, compute capability 8.0
- GPU UUID: `GPU-3815a178-ad22-4b81-5669-0533760a7e6b`
- Work directory: `/data/ai-infra-bench/survey-builds/vllm-pr-32892`
- Image tag: `ai-infra-bench/vllm-pr-32892:base`
- Docker endpoint: `unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock`
- Docker data root: `/data/yaoyaoyao/pr34183-cuda-build/docker-data`

Every Docker command explicitly used the isolated endpoint. All runtime and
oracle commands used `--network none`.

## Architecture and dependency gate

The exact source requires CUDA 12.0 or newer for `moe_permute`. The `_moe_C`
target compiles its permute sources for every configured CUDA architecture;
there is no Hopper-only guard. The assigned A100 SM80 is therefore eligible.

The PR benchmark uses FP8 input, but this permute kernel only copies opaque
payload bytes and does not execute FP8 Tensor Core arithmetic. The local
reproduction uses `torch.float8_e4m3fn` storage and compares raw bytes, so it is
valid on SM80. This differs from an FP8 GEMM workload, which would not be A100-
eligible.

The exact base pins PyTorch 2.9.1 and CUDA 12.9.1. Official vLLM v0.14.0 was
the latest release before the 2026-01-22 base commit and matches these versions.
The cached official image reported:

```json
{"cc": [8, 0], "name": "NVIDIA A100-SXM4-40GB", "torch": "2.9.1+cu129", "torch_cuda": "12.9", "uuid": "3815a178-ad22-4b81-5669-0533760a7e6b", "vllm": "0.14.0", "vllm_path": "/usr/local/lib/python3.12/dist-packages/vllm/__init__.py"}
```

The release image contains NVCC 12.9, GCC and Ninja. CMake and Git were absent;
their locked offline packages are documented below. CUDA math headers and
NVRTC libraries already exist in digest-pinned `nvidia-*-cu12` Python packages,
so the build adds their fixed include/library paths without another download.

## Locked acquisition

Exact source:

```text
base commit: dc917cceb877dfd13f98c538c4c96158047d98bd
canonical Git tree: 89beecb205e031cbb82e2eea9d2cd0f350135b8c
archive size: 19743291 bytes
archive sha256: de9e3f1e4782c9ff5c01bbc4f2daaeaa16f52bfe0ddfca2843b0ed4ecf849421
```

Offline build dependencies:

```text
Cutlass v4.2.1 archive size: 33331894 bytes
Cutlass sha256: a4513ba33ae82fd754843c6d8437bee1ac71a6ef1c74df886de2338e3917d4df
CMake 3.31.10 wheel sha256: 2f766bb46367e5e0559fa33184653754bce044583a06014dcaebf8e6dff8a1f1
Git deb archive sha256: b33d71799bececf4aec897980fcbcae2d3c4da3e5cda2a0f6fe4be70139b761b
Git: 1:2.34.1-1ubuntu1.17
git-man: 1:2.34.1-1ubuntu1.17
liberror-perl: 0.17029-1
```

The base image was already present in the isolated daemon. A digest pull check
completed in 1.94 seconds and reported `Image is up to date`; no cold-pull time
is claimed. Its inspect size is 9000898385 bytes.

The host downloaded public artifacts while using the approved shell proxy.
The build itself read all four byte-locked files from a temporary HTTP server
bound only to `127.0.0.1:32892`, then rechecked every SHA-256. No proxy secret
entered a build argument, Dockerfile, layer, task file, or captured output.
The loopback server was stopped after final validation.

## Exact native build design

The release `_moe_C` is never copied into `/app`. The Dockerfile reconstructs
the exact codeload tree as one synthetic Git commit and proves its tree equals
the canonical Git tree. It then compiles only the production `_moe_C` target
for SM80 and installs it at `/app/vllm/_moe_C.abi3.so`.

The upstream top-level CMake declares unrelated Triton, FlashMLA, Qutlass and
flash-attention FetchContent projects after defining `_moe_C`. The focused
rebuild script temporarily inserts `return()` immediately before that block,
configures/builds the exact target, and restores the candidate CMakeLists bytes
on success, failure, or signal. This prevents unrelated unlocked downloads and
keeps Git clean. Cutlass 4.2.1 remains the only external C++ source needed by
configuration and is digest-locked.

The build tree, CMake, Ninja, NVCC, headers, and Cutlass remain available. A
non-root agent can edit the candidate and rebuild the target directly:

```bash
cmake -S /app -B /app/build -G Ninja -DVLLM_TARGET_DEVICE=cuda ...
cmake --build /app/build -j 8 --target _moe_C
cmake --install /app/build --prefix /app --component _moe_C
```

The scoring rebuild is performed by the verifier-only
`tests/rebuild_for_verification.sh` (mounted read-only at `/tests`), which runs
the identical orchestration; it is never shipped into the agent image.

Applying the real three-file PR patch caused exactly two CUDA objects plus the
shared library to rebuild. The first oracle incremental rebuild took 98 seconds;
a no-change rebuild/configuration took 7 seconds.

This is a focused native environment. Only `_moe_C` is exact-built under
`/app`; it does not claim that every unrelated vLLM native extension is an
exact base build. The reproduction loads the candidate `_moe_C` explicitly and
does not depend on release `_C` or release `_moe_C`.

## Final no-cache build

```bash
export DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock
docker build --network host --no-cache \
  --build-arg VLLM_SOURCE_URL=http://127.0.0.1:32892/vllm-codeload.tar.gz \
  --build-arg CUTLASS_SOURCE_URL=http://127.0.0.1:32892/cutlass-v4.2.1.tar.gz \
  --build-arg CMAKE_WHEEL_URL=http://127.0.0.1:32892/tooling/cmake-3.31.10-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl \
  --build-arg GIT_DEBS_URL=http://127.0.0.1:32892/git-debs.tar.gz \
  -f environment/Dockerfile \
  -t ai-infra-bench/vllm-pr-32892:base \
  environment
```

```text
elapsed: 966.33 seconds (16 minutes 6.33 seconds)
image ID: sha256:5d115d55ad585578e949a6d40dbeb839b34eec5281fe4875e7761df8f85d0818
docker inspect Size: 9508066767 bytes
configured user: 10001:10001
published registry digest: not available (local validation image only)
candidate native sha256: a2b814a3fa89e9aa0a8b4663702c704bbf30ec94e2e1c9fdb9a08fe4c93775a5
```

`cuobjdump --list-elf` showed multiple `_moe_C.abi3.*.sm_80.cubin` entries.
The final build compiled 23 `_moe_C` objects and linked successfully.

## Build-attempt audit

The successful time above excludes earlier diagnostic attempts:

1. A first no-cache build stopped at 226.77 seconds because the Cutlass hash
   had been measured before the asynchronous download completed. The final
   archive was revalidated with `gzip -t`, byte size and SHA-256 before relock.
2. A debug build stopped at 164.49 seconds because renaming a wheel to
   `cmake.whl` made pip reject its filename tags. The locked bytes were correct;
   the Dockerfile now preserves the complete wheel filename.
3. CMake initially exposed unrelated external FetchContent downloads. That
   build was interrupted and the focused, restoring CMake guard was added.
4. CMake generation/compilation then exposed runtime-image paths for NVRTC and
   CUDA math headers. Both already existed inside pinned Python packages and
   are now supplied explicitly; no new dependency was downloaded.
5. The final cache-assisted debug build succeeded in 715.63 seconds, after
   which correctness and sensitivity were checked before the final no-cache
   build.

## Runtime provenance and isolation

The final image was run on physical GPU 2 with `--network none`:

```json
{"candidate_native": "/app/vllm/_moe_C.abi3.so", "candidate_python_source": "/app/vllm/__init__.py", "compute_capability": [8, 0], "cuda_available": true, "git_clean": true, "git_commit_count": 1, "git_remote_count": 0, "git_tree": "89beecb205e031cbb82e2eea9d2cd0f350135b8c", "gpu_name": "NVIDIA A100-SXM4-40GB", "gpu_uuid": "3815a178-ad22-4b81-5669-0533760a7e6b", "moe_permute_supported": true, "network_connect_ex": 101, "torch": "2.9.1+cu129", "torch_cuda": "12.9"}
```

Additional assertions passed:

- `/app` is writable by UID/GID 10001;
- `/opt/cutlass` is read-only to the agent;
- exactly one synthetic Git commit, no remotes/tags, canonical tree, clean
  working tree;
- both candidate Python and `_moe_C` resolve below `/app`;
- the native op reports `moe_permute_unpermute_supported() == true`;
- outbound TCP returns `connect_ex=101` under network isolation.

The codeload tree has no generated `_version.py`, so importing candidate vLLM
emits a harmless `Failed to read commit hash` warning and reports a dev version.
This does not affect source identity, native loading, correctness, or timing.

## Correctness hard gate

The model-free reproduction uses the PR benchmark's DeepSeek-V2-lite MoE
dimensions: 64 experts, top-k 6, hidden size 2048, alignment 128, and batch
sizes `1, 32, 128, 512, 1024, 2048, 4096`.

For every case it checks, before timing:

- aligned expert prefix offsets against an independent PyTorch calculation;
- one-to-one inverse/permuted index maps;
- every valid destination falls in the routed expert's range;
- permuted FP8 payload bytes exactly equal their source row;
- aligned `m_indices` expert IDs and untouched trailing sentinels.

Both exact base and real-PR oracle passed all seven cases. No model or dataset
is downloaded.

## Paired A100 timing evidence

Each timing is the median of five trials, each trial containing 50 native op
calls after 20 warmups, measured with CUDA events. The oracle is the real PR
patch (`sha256:607027329ead219c8c80a698585bd924f44639ba5268a766115bd182fa80a979`),
applied only in a validation container; it is absent from the task image and
task directory.

The following adjacent base/oracle pair ran on the same physical A100 GPU 2:

| Batch | Base median (us) | Oracle median (us) | Base/oracle speedup | PR-style improvement |
|---:|---:|---:|---:|---:|
| 1 | 47.616 | 47.145 | 1.010x | 1.00% |
| 32 | 47.165 | 46.920 | 1.005x | 0.52% |
| 128 | 47.944 | 46.694 | 1.027x | 2.68% |
| 512 | 91.505 | 47.247 | 1.937x | 93.67% |
| 1024 | 171.418 | 65.413 | 2.621x | 162.05% |
| 2048 | 283.689 | 70.902 | 4.001x | 300.11% |
| 4096 | 514.929 | 110.449 | 4.662x | 366.21% |

PR-style improvement is `(base / oracle - 1) * 100`, matching the PR table's
definition. The strong scaling trend reproduces the claimed bottleneck: the
base kernel's per-token linear scan becomes dominant as batch size grows.

Two earlier exact-base runs gave 4096 medians of 513.925 and 513.270 us and
2048 medians of 282.501 and 281.784 us, corroborating the selected pair. One
final-image run was an outlier at 666.849/471.716 us for those two shapes while
GPU 2 also showed another resident process. It is retained as audit evidence
but excluded from the adjacent paired comparison. This demonstrates why a
hidden performance verifier must repeat and robustly aggregate measurements.

## Verifier boundary and remaining work

A benchmark run inside the mutable candidate Python process is not a complete
trust boundary on its own. The scorer, timing harness, and native rebuild are
therefore kept in the verifier-only `/tests` mount
(`tests/rebuild_for_verification.sh`, `tests/verify_moe_permute.py`), which is
never shipped into the agent image. The verifier loads only the candidate native
library, runs correctness before timing, and rejects malformed/missing timing
samples. Performance acceptance uses several large-batch shapes rather than one
noisy point. Base/source provenance is enforced by the out-of-image curator
audit, not by an in-image gate script.

## Construction-guide feedback

- Run architecture and instruction-semantics gates before building: an FP8
  storage-copy kernel can be SM80-valid even though FP8 GEMM is not.
- Native performance tasks need an exact base build plus explicit native-path
  and cubin-architecture evidence; a release extension is not a substitute.
- Lock irrelevant FetchContent dependencies out of focused builds instead of
  silently allowing network access.
- Record cache-hit pull, diagnostic builds, and final no-cache build separately.
- Preserve the native build tree so multi-turn agent rebuilds are incremental.
- Require correctness before timing, paired base/oracle runs on the same GPU,
  repeated measurements, active-process/clock snapshots, and a documented
  outlier policy.
- Do not import performance numbers from another GPU or from the PR table as
  local evidence; use the PR table only to select representative shapes.
- Legacy Docker builder snapshot time can dominate large-image construction.
  Prefer BuildKit and consolidate metadata-only layers when the daemon allows.
