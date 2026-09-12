# Docker build and baseline validation

## 2026-09-05 trusted-scoring and representation-independence repair

Review of commit `41106b16eab924a15e7c7efc7c402d73b7098aec` found two
blocking issues. First, the shell granted reward 1 whenever the one Python
process that imported candidate vLLM exited zero. Injecting `os._exit(0)` at
the candidate package boundary therefore produced no test output but received
reward 1. Second, the verifier treated an unset environment accessor returning
`None` as part of the contract and required forced-V2 incompatibility to be
raised during `VllmConfig` construction.

The final scoring path now has a root-owned supervisor that never imports
candidate modules. It initializes a root-only reward file to 0, owns the list
of 17 required cases and their expected behavior, and launches one
unprivileged observation process per case. Each process returns only a raw,
nonce-bound observation; it cannot report aggregate success. The parent grades
every observation itself and is the only process able to replace reward with
1. A child exit code or prebuilt aggregate marker cannot grant success.

The behavior matrix no longer constrains the unset accessor representation or
the precise validation phase. It observes the real startup path through local
Qwen3/Qwen2 Hugging Face metadata, production `ModelConfig`/`VllmConfig`, and
production `GPUWorker.__init__`. It covers dense Qwen3 automatic V2 selection,
other-architecture and pooling fallback, KV-sharing and logits-processor
fallback/rejection, explicit V1/V2, and explanatory forced-V2 failure before a
usable worker exists.

Direct final-image controls on NVIDIA H20-3e produced:

```text
Base:                                 0
Oracle:                               1
Tri-state alternative:                1
Boolean-accessor/presence alternative: 1
Tri-state-only incomplete control:    0
SystemExit(0) early-exit control:      0
os._exit(0) early-exit control:        0
```

Before parent-owned per-case grading was added, the two early-exit controls
also ran through Harbor 0.22.0 with zero errored trials. These IDs are retained
as historical evidence only; exact-commit Harbor results for the final
protocol are attached to the pull request:

```text
pr3-p0-system-exit-zero: job 0d396b20-cd6a-495b-93df-3b96a7253358,
                          trial 753f4a21-6a4f-41b5-af57-5ceb317942c1,
                          reward 0
pr3-p0-os-exit-zero:     job 02208374-287d-4acb-8011-71fbf748e7c7,
                          trial ace1d876-6719-453c-8198-d4207fd7ce61,
                          reward 0
```

The replacement parent-owned protocol was then replayed on the retained
canonical image:

```text
Base:                                  0 (16/17 accepted observations)
Oracle:                                1 (17/17 accepted observations)
Boolean-accessor/presence alternative: 1 (17/17 accepted observations)
SystemExit(0):                         0 (0/17 accepted observations)
os._exit(0):                           0 (0/17 accepted observations)
```

The environment files did not change, so the validation playbook permits
reusing the retained canonical image
`sha256:d22ddb74a5d77fe9df2ce4a04b91fa937c83c9b8ed9105e3dec91fa838019189`.
The image was re-inspected and task metadata remains digest-aligned. Results
below this section are historical evidence for earlier scoring snapshots.

## 2026-09-05 public-startup verifier repair

The verifier no longer calls `_validate_v2_model_runner` or any other candidate
private helper. A tiny local Qwen3 Hugging Face configuration now drives the
real `ModelConfig` and `VllmConfig` construction path; the selected value is
then observed through the production `GPUWorker` constructor. Unsupported
forced V2 is checked at this public startup boundary using
`kv_sharing_fast_prefill`, not by naming the implementation that detects it.

Direct execution on the final image and NVIDIA H20-3e produced:

```text
Base:                              0
Oracle:                            1
Independent alternative:           1
Tri-state-only incomplete control:  0
Previous Opus-5 candidate artifact: 1
```

The previous incomplete control was replaced because it only failed through
the old synthetic subclass/private-helper coupling and passed once exercised
through a valid production configuration. The replacement is a genuine
behavioral near miss: it preserves unset/explicit tri-state parsing and forced
V2 rejection, but never implements configuration-driven default selection.

> **Historical evidence only.** The instruction, verifier, task configuration,
> or environment changed during the current hardening pass. These results do
> not validate the current executable snapshot and must be regenerated.

## 2026-09-03 verifier-independence repair

The rebuilt hidden verifier no longer requires the Oracle's private selector
or support-check helper names. It subclasses the production `VllmConfig`,
observes its resolved tri-state behavior, and constructs the real GPU worker
consumer. This change repaired a demonstrated false negative: an Opus-5
candidate used independently named resolution helpers and eagerly stored the
resolved value, so the earlier harness rejected it before judging behavior.

Fresh offline containers on an NVIDIA H20-3e (compute capability 9.0, driver
595.58.03) produced:

```text
Base reward:                       0
Oracle reward:                     1
Frozen independent candidate:      1
independent agent.patch sha256:
f7dde5d7bc8c68344b5bda0a65042663ee8dd422e27a2be9304a33ea47429518
```

The Base failed because the unset environment value still resolved to legacy
V1 and no selection API was available. The Oracle and independent candidate
both passed the unset/explicit/unsupported matrix and real GPUWorker
consumption. The candidate was frozen before hidden verification; its agent
container had no access to `/tests` or `/solution`.

Status: validated focused Harbor task for configuration selection plus
production GPUWorker consumer propagation. Base failure and isolated accepted
Oracle positive pass were both observed on the final anti-leak image.

## Harbor task upgrade (2026-08-25)

The independent task is intentionally narrower than the cumulative upstream
PR. Its solution maps accepted-head changes in `vllm/envs.py`,
`vllm/config/vllm.py`, and `vllm/v1/worker/gpu_worker.py`. It excludes upstream
tests, the unverified Scheduler migration, and the Distributed FlashInfer
change implicated in the later multi-GPU regression. GitHub's
compare API reports accepted head
`0579be818c0d2b438cd41b76d8d09f9338ac1fd8` `ahead` by 55,
`behind_by=0`, with merge base equal to locked Base
`c7560af42487b1570c4e6f4cea5df1605a4d59fc`.

```text
solution/fix.patch sha256 2586b38eb9922dca53bd6312374d1d183292f88cae7da4054df22a79541c745d
changed paths vllm/config/vllm.py, vllm/envs.py, vllm/v1/worker/gpu_worker.py
```

The hidden verifier retains the full two-sided configuration matrix and also
constructs the production `vllm.v1.worker.gpu_worker.Worker` four times. Only
the unrelated Elastic-EP distributed executor is replaced; the real
`Worker.__init__`, `WorkerBase.__init__`, and consumer assignment execute. It
therefore proves that the resolved `VllmConfig` value, rather than a second
environment read, reaches a runtime consumer for unset dense Qwen, unsupported
fallback, explicit V1, and explicit V2.

The Triton availability check is part of production selection semantics. A
no-GPU Oracle correctly fell back to V1 and was rejected by the verifier; the
task was therefore declared as one A100 rather than weakening the check. With
physical GPU 2 exposed, all runs still used `--network none` and produced:

```text
Base reward:   0
Oracle reward: 1
```

The accepted Oracle output was:

```text
PASS: tri-state selection and real GPUWorker consumption agree in both directions
gpu=NVIDIA A100-SXM4-40GB capability=8.0 uuid=3815a178-ad22-4b81-5669-0533760a7e6b
```

The canonical Docker build context is exactly `tasks/vllm-runner-v2-selection/environment`;
its only local `COPY` source is `lock/native.sha256`. Solution, hidden tests,
reproduction code, instruction, task metadata, and validation evidence are
outside that context. The task-root `.dockerignore` excludes them as defense
in depth. Solved code and hidden tests are not Agent-visible. The task keeps the
locked non-root writable, one-commit/no-remote source tree and offline runtime.

Final environment-context rebuild evidence:

```text
build context 17.92 kB
image sha256:b98f42baebd895b6366fa2745504b93ad106058b2efb87416a8d181c0f908e06
created 2026-08-25T15:37:54.720892464+08:00
size 8,853,930,961 bytes
runtime user agent
```

The jump-host relay detached before `/usr/bin/time` returned, so no reliable
elapsed value is claimed for this rebuild. Runtime assertions with physical
GPU 2 and `--network none` confirmed `/workspace/public_dev`, `/tests`, and
`/solution` are absent; UID is 1000, the repository is writable and clean with
one commit/no remote, CUDA sees the A100, and candidate Python/native imports
resolve below `/workspace/repo`.

## Scope and atomicity

The upstream PR has 55 commits, changes 6 files, and is one step in the open
multi-PR Model Runner V2 migration. It is not commit-atomic. The publishable
scope is the narrow runner-selection contract: tri-state environment override,
Qwen3 dense default selection, and unsupported-feature fallback/validation.

The full patch also changes Distributed FlashInfer consumption of the runner
flag and was immediately linked to a four-GPU NIXL/FlashInfer P/D nightly block
count mismatch. That distributed behavior is excluded from this benchmark
oracle; treating all six files as a solved atomic gold would be unsafe.

The PR head is `0579be818c0d2b438cd41b76d8d09f9338ac1fd8`, with
`+208/-20`. Review requested the final fallback matrix (including custom logits
processors and no-Triton platforms) rather than blindly setting V2 in tests.
The author explicitly limited this first migration step to Qwen dense models;
the umbrella issue describes later dense, MoE, quantized, MLA/DSA, multimodal,
and mamba steps. PR #39353 was the stated prerequisite and had merged before
this PR. These facts support a narrow config contract, not a complete model
runner migration oracle.

The two-sided boundary is:

- Explicit `VLLM_USE_V2_MODEL_RUNNER=0/1` remains a hard override.
- An unset variable is represented by `None`, allowing configuration selection.
- Only dense, unquantized Qwen3 generation defaults to V2 in this step.
- Unsupported features automatically fall back to V1; forced V2 rejects them.

The production `VllmConfig` methods are executed dynamically. No test searches
source text. GPUWorker propagation is now exercised through its production
constructor. Scheduler and Distributed FlashInfer migration remain excluded
because this task claims only one verified runtime consumer and the latter
would couple the benchmark to the known distributed regression.

## External dependency preflight

The original end-to-end scenario names `Qwen/Qwen3-0.6B`, which would require
external Hugging Face artifacts. The selection behavior is entirely determined
by `VllmConfig`, so the runtime-mounted verifier uses local synthetic model
configuration objects and executes production selection methods plus the real
GPUWorker constructor. It needs no model, tokenizer, dataset, network,
connector, or service.

## Docker daemon

All Docker commands use:

```bash
export DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock
```

The daemon data root is
`/data/yaoyaoyao/pr34183-cuda-build/docker-data`. The default daemon is not
used, and no pruning or deletion is performed.

## Build, baseline, and integrity evidence

### Official-image pre-overlay probe

The official v0.20.2 image is the newest release before the base commit cutoff:

```text
repository digest sha256:70a098d90dbab428a001d9e852fc0fc8d67da5beb03e7851a22247653bf35923
image size 8231364540 bytes
created 2026-05-08T20:26:26.98773105Z
vllm 0.20.2
torch 2.11.0+cu130
cuda NVIDIA A100-SXM4-40GB
allocation 128 elements
vllm._C /usr/local/lib/python3.12/site-packages/vllm/_C.abi3.so
vllm._custom_ops import passed
```

The native manifest contains exactly nine regular ELF `.so` files plus
generated `_version.py`. All ten hashes passed both before and after copying;
the final candidate tree contains exactly nine `.so` files.

### Build

Remote context:
`/data/ai-infra-bench/survey-builds/vllm-pr-39337/context`

```bash
export DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock
source /data/akg_kernel_bench_lite/A100_proxy.sh
cd /data/ai-infra-bench/survey-builds/vllm-pr-39337
/usr/bin/time -p docker build \
  --network host \
  --pull=false \
  --build-arg HTTP_PROXY \
  --build-arg HTTPS_PROXY \
  --build-arg NO_PROXY \
  -t ai-infra-bench/vllm-pr-39337:base \
  -f context/environment/Dockerfile context
```

Initial real build result before the manifest-whitespace-only cached rebuild:

```text
Successfully built 50f83080da46
Successfully tagged ai-infra-bench/vllm-pr-39337:base
real 514.59
user 0.10
sys 0.03
```

Warning-free final rebuild result:

```text
Successfully built 289e072dfaa7
Successfully tagged ai-infra-bench/vllm-pr-39337:base
real 335.07
user 0.06
sys 0.03
```

- Final image ID:
  `sha256:289e072dfaa7adc8f5a291adc56c4242580673b4122cafe89731d1e746f9833e`
- Final image size: `8,853,930,570` bytes
- Runtime user: `agent` (UID 1000)
- Synthetic commit: `f9e756b26bed94e7cede482d8de4b4dfda224319`
- Branch: `benchmark-base`
- Root tree: `00dedbf38a187d7be24007ab92ce0158c646d024`
- Image proxy environment rows: `0`
- Image history rows containing proxy assignments: `0`

The manifest-whitespace fix removed the earlier `sha256sum` formatting warning;
all ten artifact checks completed with only `OK` results in the final build.

### Historical curation baseline (removed from Agent image)

The following earlier config-only harness established the initial Base/Oracle
boundary. It is not shipped in the final environment. The publishable score is
now produced only by `tests/verify_runner_consumers.py`, mounted at verifier
runtime.

```bash
docker run --rm --network none \
  ai-infra-bench/vllm-pr-39337:base \
  bash /workspace/public_dev/run.sh
```

Exit status: `1` (expected).

```text
FAIL: model-runner selection contract is incomplete
 - env None: expected None, got False
 - default model selector is unavailable
 - runner oracle property is unavailable
```

This is a feature-addition Base failure with preserved legacy explicit `0/1`
behavior. It is not accepted alone; the Oracle pass below proves that the
public behavior distinguishes the intended solution.

### Historical cumulative Oracle positive pass

The official cumulative PR diff was downloaded only to the remote validation
directory, never copied into the Agent context or image:

```text
/data/ai-infra-bench/survey-builds/vllm-pr-39337/oracle.diff
SHA-256 2db98aeab32bfc2a66abfbaa4a851c8e8171050f198896c79808857820090ed7
size 13987 bytes
```

It was bind-mounted read-only and applied inside a disposable offline
container based on the Base image:

```bash
docker run --rm --network none --gpus device=0 \
  -v /data/ai-infra-bench/survey-builds/vllm-pr-39337/oracle.diff:/tmp/oracle.diff:ro \
  ai-infra-bench/vllm-pr-39337:base \
  bash -lc 'git apply --check /tmp/oracle.diff && \
    git apply /tmp/oracle.diff && bash /workspace/public_dev/run.sh'
```

The diff changed the expected six upstream files and the public Dev exited 0:

```text
tests/test_config.py
vllm/config/vllm.py
vllm/envs.py
vllm/v1/attention/backends/flashinfer.py
vllm/v1/core/sched/scheduler.py
vllm/v1/worker/gpu_worker.py
PASS: tri-state overrides, default selection, and fallback all work
```

This demonstrates the positive boundary without shipping solved code.
The warning immediately before PASS is expected: it is production behavior for
the synthetic unsupported-feature fallback case, not a test or environment
warning.

### GPU, source binding, offline, and sanitization

All runs used `--network none`; the integrity probe additionally used GPU 0:

```text
uid 1000
vllm 0.20.2
torch 2.11.0+cu130
source /workspace/repo/vllm/__init__.py
native /workspace/repo/vllm/_C.abi3.so
custom_ops /workspace/repo/vllm/_custom_ops.py
gpu NVIDIA A100-SXM4-40GB 8.0
target_device None
offline 1 1
git_count 1
git_remote_rows 0
git_status_rows 0
pyc_count 0
so_count 9
route_file_lines 1
user 1000
```

`/workspace/repo` is writable by `agent`; `/workspace/public_dev` is absent.

## Remaining risks

- Nearest-release native artifacts are not a compilation of the exact SHA,
  though they share Torch/CUDA pins and are not invoked by the target workload.
- Distributed FlashInfer/NIXL and real model inference remain outside scope;
  the task must not be described as validating the complete six-file PR.
- The verifier requires a CUDA-visible A100 so production `HAS_TRITON` is true;
  running it as a CPU-only task changes the intended default-selection branch.

## Survey-manual feedback

- A long-running migration PR should be publishable only after extracting a
  two-sided behavior contract; file count alone does not establish atomicity.
- Require explicit distinction between host-side selection tests and mandatory
  GPU/native environment-integrity probes.
- An end-to-end model named by a PR should not force weight downloads when the
  changed behavior has a deterministic local configuration boundary.
- Immediate follow-up/revert evidence must be used to exclude unsafe consumers
  from a supposedly atomic oracle.
- Feature-addition tasks need an isolated Oracle positive pass; Base failing on
  a missing property is insufficient by itself.
> **Historical evidence only.** The instruction, verifier, task configuration,
> or environment changed during the current hardening pass. These results do
> not validate the current executable snapshot and must be regenerated.
