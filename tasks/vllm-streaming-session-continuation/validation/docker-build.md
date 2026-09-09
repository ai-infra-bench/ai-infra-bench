# Harbor build and validation

> Historical v1.0 validation. Task v1.1 broadens the public/hidden lifecycle
> cases and has not yet been rerun; see `docs/VLLM_OPUS5_TASK_REVISION_V1_1.md`.
>
> Provenance supersession: task v1.2.1 now retains the exact upstream Base at
> `HEAD` with sanitized parent history. Image IDs and Git assertions below are
> historical and are not evidence for the current environment; rebuild and
> `image-check` remain mandatory.

Status: Harbor-ready for the scoped GPU-runner continuation contract. The
entire upstream PR is not atomic: it contains 64 commits, changes 16 files, and
spans API, scheduler, request, output-processing, and runner layers. This task
therefore maps only the accepted 41-line production change that updates an
already-cached request in `GPUModelRunner._update_states`.

## Contract and solution mapping

The verifier constructs a real `CachedRequestState`, persistent input-batch
row, `NewRequestData`, and scheduler output, then invokes the production
`GPUModelRunner._update_states` method. A streaming continuation must preserve
the request object, remove its stale batch row before re-addition, refresh all
input state, recalculate prompt length, and clear output tokens that have
become prompt context.

This is not a missing-symbol or source-string smoke test. The base reaches the
production runner and attempts to add a duplicate stale row. The accepted
solution is the matching one-file hunk from oracle commit
`3abe7e7b4942d479f2c43188b8cf414e3a21dd38`; it adds the continuation branch
and `_update_streaming_request`. The image contains neither that patch nor any
instruction or verifier asset.

The exercised state transition is CPU-executable: it creates no model and
runs no CUDA kernel. Accordingly `task.toml` declares `gpus = 0` and uses a
correctness grader. GPU/native viability is a separate environment-integrity
probe and is not a task resource gate.

## Locked environment

- Survey base: `0118cdcc02ae16a137645e2289bf41f5e3da9d80`
- Canonical source tree: `eb2267901a78dcd021c505f5a6bd50ccc6632a9b`
- Source archive SHA-256:
  `75b2632ec1ea5f92539b9c5f6a7e3cd3357874f04cfd6953c9ae851f1b992957`
- Official base: `vllm/vllm-openai:v0.14.0` at manifest digest
  `sha256:1d6866b87630d94f5e0cdae55ab5abb4ce0b03fcb84d9d10612f9d518d19d4fd`
- Native-only donor: `vllm/vllm-openai:v0.15.1` at manifest digest
  `sha256:8c9aaddfa6011b9651d06834d2fb90bdb9ab6ced4b420ec76925024eb12b22d0`

The post-cutoff v0.15.1 donor remains a material ABI approximation. It is
needed because the exact candidate Python `_custom_ops` expects bindings that
the healthy v0.14.0 extension lacks. The donor contributes only seven explicit
regular ELF `.so` paths. `native-donor.sha256` and `final-native.sha256` lock
the donor and final bytes; the final manifest also locks v0.14.0 `_version.py`.
No donor Python package or staging directory remains.

The exact source archive is materialized before native artifacts, checked
against the canonical tree with `git add -f -A`, and committed as one synthetic
commit with no remote. Native/generated files remain ignored after the commit.

## Build evidence

All commands used the isolated daemon, never the default daemon:

```bash
export DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock
source /data/akg_kernel_bench_lite/A100_proxy.sh
cd /data/ai-infra-bench/survey-builds/vllm-pr-28973/harbor-context
/usr/bin/time -p docker build \
  --network host --pull=false \
  --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY \
  -t ai-infra-bench/vllm-pr-28973:harbor \
  -f environment/Dockerfile environment
```

The standard Harbor `environment` context was 14.85 kB, so `solution/`,
`tests/`, and `instruction.md` were physically outside the context.

```text
Successfully built 94ca1f6c7342
real 772.82
image sha256:94ca1f6c73422a9aa81ccf954efac9cfbcb7f4d1dd2416ef953ac84add3690f0
size 10618390313 bytes
USER agent
WORKDIR /workspace/repo
```

Build assertions passed for archive hash, canonical tree, one commit, no
remote, clean Git, seven donor/final ELF objects, exact manifests, and absent
donor staging. Image config and history scans found no proxy environment or
credential-shaped proxy URL.

## Runtime integrity

Fresh CPU containers used `--network none` and no `--gpus`. They established:

```text
uid=1000 writable=PASS assets_absent=PASS
git_count=1 canonical_tree=PASS network_routes=0
source=/workspace/repo/vllm/__init__.py
runner=vllm.v1.worker.gpu_model_runner
SO_COUNT=7 DONOR_STAGE_ABSENT=PASS
```

Without a GPU device mapping, direct `vllm._C` import reports missing
`libcuda.so.1`; this is expected and is not required by the CPU state-update
contract. An independent A100 GPU7 no-network probe passed the native boundary:

```text
gpu=NVIDIA A100-SXM4-40GB cuda_count=1 tensor=tensor([0.], device='cuda:0')
source=/workspace/repo/vllm/__init__.py
native=/workspace/repo/vllm/_C.abi3.so
network_routes=0
```

## Base and Oracle

Base, with only `tests/` mounted read-only:

```text
contract_device=cpu
FAIL: production runner rejected session continuation:
AssertionError continuation was re-added without removing its stale batch row
TEST_SH_RC=0 REWARD=0
```

Isolated Oracle, with `solution/` applied as `agent` before running the same
verifier:

```text
SOLVE_RC=0
contract_device=cpu
PASS: production runner updated the streaming session in place
TEST_SH_RC=0 REWARD=1
```

Both runs were offline and used no GPU. The baseline failure is behavioral and
the Oracle demonstrates the accepted implementation, rather than merely
checking that a symbol or signature exists.

## Remaining risks and manual feedback

- The publishable contract is one accepted runner change, not the 64-commit PR.
  Review and task metadata must preserve this narrow mapping.
- The v0.15.1 native donor is post-cutoff. It has strict path/hash/ELF and
  anti-leak controls, but an exact base-SHA native build would be stronger.
- Hardware requirements should follow the target behavior. A GPU production
  module can still have a CPU-executable state-management contract; unrelated
  CUDA integrity must not force GPU grading.
- Harbor must build from `environment/`, not the task root, so hidden tests and
  accepted solutions cannot enter the image even if ignore rules regress.
