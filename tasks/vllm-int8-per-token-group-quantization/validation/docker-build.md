> Current local review and execution status: see [final-review.md](final-review.md)
> and [e2e-evidence.json](e2e-evidence.json). Everything below is retained as
> historical build evidence; old "not rerun" statements describe that snapshot.

# Docker build and validation record

> Historical v1.0 build/oracle record. Task v1.1 adds mandatory evaluator-time
> rebuilding and content-addressed patch/source/native/import evidence; that
> revised end-to-end grader has not yet been rerun.
>
> Provenance supersession: task v1.2.1 now retains the exact upstream Base at
> `HEAD` with sanitized parent history. Image IDs and Git assertions below are
> historical and are not evidence for the current environment; rebuild and
> `image-check` remain mandatory.

## Status

Environment, base runtime, and oracle correctness/performance control validated on A100. No PR-reported H100 timing is used as an A100 result.

## Required construction

Remote context: `/data/ai-infra-bench/survey-builds/vllm-pr-21476/context`

Docker daemon (required on every command):

```bash
export DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock
```

The Dockerfile downloads only digest-pinned source/dependency archives during
construction. It therefore requires construction-time network access. Runtime
validation remains network-isolated.

Base build command:

```bash
/usr/bin/time -f 'BUILD_SECONDS=%e' docker build \
  -f environment/Dockerfile \
  -t ai-infra-bench/vllm-pr-21476:base .
```

Oracle-control build reuses the exact same Dockerfile/toolchain and changes only the selected source archive and immutable source identity:

```bash
/usr/bin/time -f 'BUILD_SECONDS=%e' docker build \
  -f environment/Dockerfile \
  --build-arg VLLM_SOURCE_COMMIT=2e25870f8445f9531a7fa9fb8f144bb68e4ab6e6 \
  --build-arg VLLM_SOURCE_SHA256=12a475fafd3aa1fcb0fa1eae1daf48a68f59a63fd0b69bca06dfefe8455703b6 \
  --build-arg VLLM_SOURCE_URL=https://codeload.github.com/vllm-project/vllm/tar.gz/2e25870f8445f9531a7fa9fb8f144bb68e4ab6e6 \
  -t ai-infra-bench/vllm-pr-21476:oracle .
```

Both builds fail closed on archive SHA-256 mismatch. Runtime validation uses
`--network none`, GPU 1, and mounts only the probe:

```bash
docker run --rm --network none --gpus 'device=1' \
  -v "$PWD/validation/int8_quant_probe.py:/tmp/int8_quant_probe.py:ro" \
  ai-infra-bench/vllm-pr-21476:base \
  python3 /tmp/int8_quant_probe.py --mode base

docker run --rm --network none --gpus 'device=1' \
  -v "$PWD/validation/int8_quant_probe.py:/tmp/int8_quant_probe.py:ro" \
  ai-infra-bench/vllm-pr-21476:oracle \
  python3 /tmp/int8_quant_probe.py --mode candidate
```

Correctness is a hard gate: the candidate native operator must exist; the base must not contain it; CUDA and Triton scale tensors must agree; quantized values may differ by at most one integer step because of rounding. Timing is reported only after that gate and is a paired CUDA-vs-Triton median on this A100. Task v1.1 publicly freezes a `1.5x` same-A100 paired speedup threshold on every listed shape; the PR author's approximately 15x H100 number remains context, not the local threshold.

Only `ai-infra-bench/vllm-pr-21476:base` is the coding-agent environment. The oracle image is an evaluator-side control and is not delivered to the agent. Likewise, `int8_quant_probe.py` is mounted read-only by the evaluator and is not copied into either image.

## Evidence

The official base pull took 1278.14 seconds through the daemon proxy. The final focused exact-base build took 1963.78 seconds and produced:

```text
image ID: sha256:d328facbe773b42425b38c950b80d80f1b8513b5e528dcb7bfa90ac5710e8bb6
size:     11882500265 bytes
user:     agent
workdir:  /workspace/repo
source:   /workspace/repo/vllm/__init__.py
native:   /workspace/repo/vllm/_C.abi3.so
GPU:      NVIDIA A100-SXM4-40GB, capability (8, 0)
PyTorch:  2.7.1+cu128
CUDA:     12.8
```

`cuobjdump -lelf vllm/_C.abi3.so` reported `sm_80` cubins. Image labels expose `_C=exact-source:14bf19e...;other=v0.10.0-donor`. The focused CMake invocation was observed as `ninja -j 4 _C`. The final image has one synthetic commit, a clean worktree, no remote, and runs as the non-root `agent` user.

The base A100/offline probe passed all three Triton/reference cases and confirmed `native_int8_op False`, which is the required negative control:

```text
base_triton_correct (32, 128) 64 torch.float16
base_triton_correct (64, 256) 128 torch.bfloat16
base_triton_correct (7, 512) 64 torch.float32
```

The exact-head oracle build took 1898.69 seconds and produced image ID `sha256:23d0aab4a9c9645c6e8c072e71a5804954713dc2a230e646dedf19ac8e8a9b3d` (11,882,858,315 bytes). Its label binds `_C` to `2e25870f8445f9531a7fa9fb8f144bb68e4ab6e6`. On A100 GPU 1 with `--network none`, the hard correctness gate passed for float16, bfloat16, and float32 inputs. CUDA-versus-Triton quantized outputs differed by at most one integer step, and maximum scale error was `1.49e-08`:

```text
native_int8_op True
correct (32, 128) 64 torch.float16  q_max_delta 1 scale_max_delta 1.4901161193847656e-08
correct (64, 256) 128 torch.bfloat16 q_max_delta 1 scale_max_delta 1.4901161193847656e-08
correct (7, 512) 64 torch.float32    q_max_delta 1 scale_max_delta 0.0
```

After correctness passed, five median batches of 400 calls gave the following paired same-process measurements. Both paths include output allocation and Python/operator dispatch; the Triton path directly launches `_per_token_group_quant_int8`, so no mock/patch overhead is included:

| Shape | Group | CUDA ms | Triton ms | A100 speedup |
|---|---:|---:|---:|---:|
| `(1024, 4096)` | 128 | 0.019105 | 0.045069 | 2.359x |
| `(4096, 4096)` | 128 | 0.055677 | 0.130248 | 2.340x |
| `(2048, 4096)` | 64 | 0.048307 | 0.129485 | 2.680x |
| `(16, 256, 4096)` | 128 | 0.055923 | 0.130263 | 2.331x |
| `(4096, 4096)` | 64 | 0.094484 | 0.254899 | 2.698x |

The recorded oracle result is approximately 2.33–2.70x, not the PR's approximately 15x H100 result. It clears the task-v1.1 `1.5x` public threshold. The v1.1 timing cases were recalibrated in September 2026 after discovering the v1.0 shapes measured kernel-launch overhead rather than throughput (oracle candidate time was flat ~0.018 ms from 0.008 MiB to 8 MiB; ms/MiB only stabilized at >=32 MiB). The new cases are all in the throughput regime and were validated against `slow-candidate-occupancy.patch` (expected_reward=0): the control's best single round was 1.251, safely below the 1.5 threshold, confirming the gate discriminates.

Two construction diagnostics were retained rather than hidden. The first full-extension attempt failed after 1891.02 seconds because GitHub's FlashAttention archive omitted its CUTLASS submodule. After locking that submodule, a corrected full build passed the former failure point but was intentionally stopped at roughly 38 minutes while still compiling unrelated FlashAttention variants (about 89 of 312 Ninja outputs). The final focused build compiles the complete candidate extension `_C`; it does not use a single-file overlay.

No model or dataset is needed for this kernel-level task. The runtime probe uses only deterministic generated tensors and runs with `--network none`.

## Construction-guide feedback

- For a PR that adds a native operator, source-path binding alone is insufficient. Require the task image to rebuild the exact baseline native extension and require the oracle control to rebuild from the immutable head using the same toolchain.
- For a focused native PR, build the complete candidate extension (`_C` here) from exact source. Unrelated extensions may be copied no-clobber from the pinned same-version image only when the image labels and validation record expose that scoped native origin.
- FetchContent inputs are part of the environment lock. Mirror them into the context with revision and digest, and force the build offline so a missing dependency fails visibly.
- GitHub source archives omit submodule contents. Recursively inspect gitlink entries and lock every build-relevant submodule as a separate digest-verified input.
- Hardware-specific performance claims need an architecture gate plus same-machine paired measurement. Upstream timing from a different GPU should never become the local threshold.
