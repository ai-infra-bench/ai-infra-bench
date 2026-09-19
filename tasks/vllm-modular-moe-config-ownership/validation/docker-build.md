# Docker build and baseline validation

> Historical v1.0 validation. Task v1.1 no longer inspects kernel storage or
> requires private attribute/constructor names. Its mutation-and-conflict
> behavior verifier has not yet been rerun.
>
> Provenance supersession: task v1.2.1 now retains the exact upstream Base at
> `HEAD` with sanitized parent history. Image IDs and Git assertions below are
> historical and are not evidence for the current environment; rebuild and
> `image-check` remain mandatory.

Status: validated Harbor task for the modular-kernel configuration ownership
contract. The real base image executes a CUDA Triton MoE before reproducing the
old API, and the accepted squash Oracle passes the same hidden verifier.

## Harbor upgrade verification

The authoritative accepted mapping is squash parent
`b337647aa0ce103a84aac1e07a8fd738a5a4f13f` to merged commit
`3778673ea81bf5241f40e9c5e90f989bde377acf`. Survey Base
`e2ed238885be6af358be1851cd43105b7d036c49` is an ancestor of both the PR Head
and the squash parent; the focused five-file production patch applies cleanly
to that Base.

The historical v1.0 Harbor verifier used a hidden input shape and checked:

- a real CUDA BatchedTritonExperts forward and finite output;
- no-config compatibility without consulting process-global vLLM config;
- ordinary explicit config identity and numerical equivalence;
- DP+EP config identity and decision;
- the production `FusedMoEModularMethod.make` consumer passes the layer's MoE
  config rather than its generic vLLM parallel config;
- the production FlashInfer CUTLASS wrapper makes the same ownership choice,
  while the functional CUTLASS entry no longer accepts the obsolete keyword;
- the superseded `parallel_config=` keyword is rejected.

On A100 GPU0 with `--network none`, the unchanged Base reached the real Triton
forward and then produced reward `0` at the missing `moe_parallel_config`
contract. Applying the accepted Oracle produced reward `1`:

```text
CUDA_TRITON_COMPAT_OK 20993.70703125
consumers=FusedMoEModularMethod.make,flashinfer_cutlass_moe_fp8
dp_ep=true
legacy_keyword_rejected=true
ordinary_matches_compatibility=true
```

The remaining post-cutoff v0.13 native donor risk is an environment provenance
limitation, not an untested target behavior: the candidate Python and focused
production consumer are exact Base source, all donor artifacts are manifest
locked, and the same real Triton path executes on both Base and Oracle.

## Atomicity, review requirements, and behavior contract

The PR has 12 branch commits and changes eight files (`+32/-27`). Its core is a
coherent configuration-ownership refactor; two tiny formatting/type-annotation
changes are incidental. Review narrowed the implementation after noting that
most non-EP paths should not receive extra MoE-parallel arguments, that the
functional DeepGEMM/CUTLASS paths are non-EP, and that non-modular backends such
as FlashInfer TRTLLM MoE must remain unaffected.

The publishable behavior boundary is therefore:

- An explicit `FusedMoEParallelConfig` is stored by identity and drives the
  cached DP+EP decision from `dp_size` and `use_ep`.
- A normal single-rank config remains non-DP+EP and produces the same CUDA
  result as the compatibility entry.
- Construction without a config remains compatible and assumes non-DP+EP;
  it must not consult process-global vLLM configuration.
- The superseded `parallel_config` keyword is rejected.
- A real CUDA Triton modular MoE executes before the baseline-specific failure;
  the verifier is not a constructor-signature or source-string test.

## Docker daemon

All Docker commands use:

```bash
export DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock
```

The daemon data root is
`/data/yaoyaoyao/pr34183-cuda-build/docker-data`. The default daemon is not
used, and no pruning or deletion is performed. Build networking uses
`/data/akg_kernel_bench_lite/A100_proxy.sh`; runtime is `--network none`.

The final image has zero runtime proxy variables, history proxy assignments,
or common credential markers.

## Native binding decision

The unmodified v0.12.0 image passed `vllm._C`, `vllm._custom_ops`, and A100
allocation with PyTorch `2.9.0+cu129`. After overlaying the exact base Python,
import failed before the verifier workload:

```text
RuntimeError: operator _C::cutlass_encode_and_reorder_int4b_grouped does not exist
```

Thus the failure is introduced by pairing newer candidate Python with the
pre-cutoff v0.12 binary, not an upstream packaging defect. v0.13.0 is the
nearest official native donor and retains the exact Torch 2.9.0 / CUDA 12.9
family, but was published four days after the cutoff. The revised multi-stage
image copies only its `.so` files with relative paths preserved; post-cutoff
Python and generated version metadata are excluded. This approximation must
remain a recorded publication risk even if all imports and kernels pass.

The final Dockerfile does not discover donor artifacts by wildcard. It reads
the seven-path SHA-256 manifest in `environment/lock`, rejects unsafe/non-`.so`
paths, symlinks, non-ELF files, hash mismatches, extra staging objects, and any
surviving final staging directory. The exact archive is separately
force-added, and its synthetic commit tree must equal canonical upstream tree
`75491c7db4e75808a6bfe937322d3839a619ecdf`; generated/native files are placed
after that commit.

## Official image evidence

v0.12.0 was published on 2025-12-03, before the exact base timestamp
`2025-12-15T00:33:41Z`; v0.13.0 was published on 2025-12-19. The official
v0.12.0 image is therefore the correct runtime base. Before overlay it passed:

```text
image sha256:6766ce0c459e24b76f3e9ba14ffc0442131ef4248c904efdcbf0d89e38be01fe
size 8931755554 bytes
versions 0.12.0 2.9.0+cu129 12.9
source /usr/local/lib/python3.12/dist-packages/vllm/__init__.py
native /usr/local/lib/python3.12/dist-packages/vllm/_C.abi3.so
cuda True NVIDIA A100-SXM4-40GB tensor([0.], device='cuda:0')
```

The v0.13.0 native-only donor pull took `414.20s`. Its own `_C`,
`_custom_ops`, and A100 allocation probe passed with the same PyTorch/CUDA
family:

```text
image sha256:d623253f2ba246378421c9642e20885e65257f38418ff26d48c81aea1702521b
size 8944175827 bytes
versions 0.13.0 2.9.0+cu129 12.9
native /usr/local/lib/python3.12/dist-packages/vllm/_C.abi3.so
cuda True NVIDIA A100-SXM4-40GB tensor([0.], device='cuda:0')
```

## Final build

Remote context:
`/data/ai-infra-bench/harbor-envonly/tasks/vllm-pr-30282/environment`

```bash
export DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock
source /data/akg_kernel_bench_lite/A100_proxy.sh
cd /data/ai-infra-bench/harbor-envonly/tasks/vllm-pr-30282
/usr/bin/time -p docker build \
  --network host \
  --pull=false \
  --build-arg HTTP_PROXY \
  --build-arg HTTPS_PROXY \
  --build-arg NO_PROXY \
  -t ai-infra-bench/vllm-pr-30282:harbor-base \
  -f environment/Dockerfile environment
```

Result:

```text
Sending build context to Docker daemon  19.97kB
Successfully built f232f10352aa
Successfully tagged ai-infra-bench/vllm-pr-30282:harbor-base
real 237.94
user 0.04
sys 0.03
```

- Image ID:
  `sha256:f232f10352aaa102893cd53be0f29116f36a40e80caf1498a986c1ae97f0a079`
- Image size: `10,446,427,684` bytes
- Runtime user: `agent` (UID 1000)
- Candidate synthetic commit:
  `8521e82ad54a82c639f292ca77d3c60922faab6c`
- Candidate tree:
  `75491c7db4e75808a6bfe937322d3839a619ecdf` (canonical match)
- Archive SHA-256, seven native hashes, regular ELF checks, and no-extra-object
  assertions: passed

## Harbor Base and Oracle

```bash
export DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock
docker run --rm --network none --gpus device=0 \
  --user root \
  -v "$TASK/tests:/tests:ro" \
  ai-infra-bench/vllm-pr-30282:harbor-base \
  bash -lc '/tests/test.sh; cat /logs/verifier/reward.txt'
```

Base reward: `0` (expected baseline failure).

```text
WARNING ... Current vLLM config is not set.
WARNING ... Using default MoE config. Performance might be sub-optimal!
CUDA_TRITON_COMPAT_OK 12059.134765625
TypeError: FusedMoEModularKernel.__init__() got an unexpected keyword argument 'moe_parallel_config'
```

The CUDA marker is printed only after two batched Triton expert GEMMs,
activation/finalization, `torch.cuda.synchronize()`, and finite/nonzero output
validation. Thus the real compatibility entry runs before the baseline reaches
the task-specific failure. The global-config warning is itself part of the old
fallback behavior that the target removes.

After applying the accepted focused Oracle as UID 1000, the same verifier
returned reward `1`:

```text
CUDA_TRITON_COMPAT_OK 20993.70703125
{"compatibility_norm": 20993.70703125, "consumers": ["FusedMoEModularMethod.make", "flashinfer_cutlass_moe_fp8"], "cuda": true, "dp_ep": true, "gpu": "NVIDIA A100-SXM4-40GB", "legacy_keyword_rejected": true, "ordinary_matches_compatibility": true}
ORACLE_REWARD=1
```

The solved tree additionally demonstrates:

- the explicit ordinary config to be stored by identity, remain non-DP+EP,
  execute the same CUDA Triton path, and match the compatibility output;
- an explicit `dp_size=2, use_ep=True` config to be stored by identity and set
  `is_dp_ep=True`; and
- the legacy `parallel_config=` keyword to raise `TypeError`.

A fresh final-image container also confirmed that `/workspace/public_dev`,
`/tests`, and `/solution` are absent before verifier mounts; its synthetic Git
state is one commit, zero remotes, and clean.

## Final binding and sanitization probes

```text
uid 1000
versions 0.12.0 2.9.0+cu129 12.9
source /workspace/repo/vllm/__init__.py
native /workspace/repo/vllm/_C.abi3.so
custom_ops /workspace/repo/vllm/_custom_ops.py
modular /workspace/repo/vllm/model_executor/layers/fused_moe/modular_kernel.py
target_device None
offline 1 1
cuda 1 NVIDIA A100-SXM4-40GB tensor([0.], device='cuda:0')
```

The unmodified underlay remains v0.12.0 at
`/usr/local/lib/python3.12/dist-packages/vllm`; it is not v0.13 Python. The
candidate wins on `PYTHONPATH`, and only the seven manifest-listed `.so` files
exist in its tree.

```text
tree 75491c7db4e75808a6bfe937322d3839a619ecdf
git_count 1
git_remote_rows 0
git_status_rows 0
route_rows 0
pyc_count 0
staging_exists no
native_count 7
runtime_proxy_keys 0
history_proxy_assignments 0
history_secret_markers 0
```

## Remaining risks

- Native extensions are a four-day post-cutoff approximation. They use the
  exact Torch/CUDA family and pass real candidate imports and Triton execution,
  while donor Python is excluded, but exact-SHA compilation would be stronger.
- The verifier validates the DP+EP decision with a real config object but does not
  launch a multi-rank distributed EP job. Its scope is configuration ownership
  and modular-kernel behavior, not collective correctness.
- Review explicitly discussed non-modular FlashInfer TRTLLM MoE as unaffected;
  this focused verifier does not execute that separate backend.

## Survey-manual feedback

- Refactor tasks must turn review discussion into behavioral scope: distinguish
  modular DP+EP paths, ordinary non-EP paths, compatibility entry points, and
  explicitly unaffected backends.
- A CUDA task should emit its task-specific baseline failure only after a real
  kernel synchronization and output validation; signatures alone are not an
  adequate workload.
- When pre-cutoff native bindings fail only after source overlay, preserve the
  original-image pass and overlay failure as separate evidence. A post-cutoff
  donor needs exact ABI comparison, a path/hash manifest, ELF/no-extra-object
  assertions, and explicit anti-leak checks.
- Archive-based synthetic Git must use `git add -f -A` and compare its tree to
  the canonical upstream tree before generated/native artifacts are added.
