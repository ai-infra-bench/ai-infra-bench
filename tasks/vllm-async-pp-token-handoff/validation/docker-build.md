> Current local review and execution status: see [final-review.md](final-review.md)
> and [e2e-evidence.json](e2e-evidence.json). Everything below is retained as
> historical build evidence; old "not rerun" statements describe that snapshot.

# Docker build and validation

> Historical v1.0 validation. Task v1.1 removes private helper-name gates and
> independently records config, production sample/NCCL scenarios, and the
> following Scheduler round; it has not yet been rerun.
>
> Provenance supersession: task v1.2.1 now retains the exact upstream Base at
> `HEAD` with sanitized parent history. Image IDs and Git assertions below are
> historical and are not evidence for the current environment; rebuild and
> `image-check` remain mandatory.

Status: **environment-ready for the focused two-rank GPU token path**. The
scheduler re-entry and original PP4 model/performance layers remain unclaimed.

## Ancestry and atomicity

GitHub compare reports base `8ebf372e...` as the exact merge-base of head
`6ce90d08...`; head is 17 commits ahead and zero behind. The recorded merge
SHA is a squash commit with one parent, not a two-parent merge commit.

The branch contains 17 commits and six merges from main, but the net feature
surface is four files (`+103/-23`). Two production files implement one coupled
behavior: allow scheduler re-entry while PP output placeholders are in flight,
then propagate the last stage's sampled token tensor directly over GPU PP
communication so earlier stages can prepare the next async step.

## Solution mapping and review

The constrained predecessor PR 32359 skipped another step for requests with PP
output placeholders. PR 32618 removes that scheduler guard, omits the old CPU
token payload in async PP, broadcasts the sampled GPU tensor from the last PP
rank, receives it on earlier ranks, rebuilds `prev_req_id_to_index`, and appends
a local `-1` output placeholder for non-discarded requests.

Review explicitly replaced an earlier CPU-copy/dictionary design with direct
GPU broadcast. Later reports identify multi-node, chunked scheduling, KV
offload, and some PP-size performance risks; those are retained as
generalization risks, not treated as coverage of this focused Gold.

## Hardware and external scope

- Focused Dev: two local A100 GPUs, two real NCCL ranks, no model or dataset.
- Original correctness: four PP stages, `Qwen/Qwen3-30B-A3B-Thinking-2507-FP8`,
  lm-eval and GSM8K.
- Original performance: four PP stages, random input length 2, output length
  512, 128 prompts, 16 warmups, async/non-async paired serving runs.

## Docker daemon

All commands use:

```bash
export DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock
```

Runtime validation uses `--network none`. No daemon pruning or unrelated image
deletion is performed.

## Evidence

Remote working directory:

```text
/data/ai-infra-bench/survey-builds/vllm-pr-32618
```

Representative build command:

```bash
source /data/akg_kernel_bench_lite/A100_proxy.sh
export DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock
docker build --network host --pull=false \
  --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY \
  --build-arg VLLM_SOURCE_URL=http://127.0.0.1:18086/source/vllm-base.tar.gz \
  -t ai-infra-bench/vllm-pr-32618:base \
  -f context/environment/Dockerfile context
```

- The exact v0.14.1 digest was absent before pull. Digest registration/pull
  completed in `1.77 s`, but the daemon reported shared layers, so this is not
  claimed as a cold-layer download benchmark.
- Donor image size: `9,013,402,905` bytes.
- First exact-source build: `518.43 s`.
- Cached rebuild after fixing `torchrun` to use an explicit loopback master:
  `124.82 s`.
- Final image:
  `sha256:1ca6c3d27eb2f883666d37d22eacfdef51a8db156ca8ff3158dc409780484cc5`.
- Final image size: `10,099,658,405` bytes.

The first Oracle attempt used `torchrun --standalone`; under `--network none`,
the generated container hostname was not resolvable. The public script now
pins `127.0.0.1:29518`. This retains runtime isolation while allowing the two
local ranks to rendezvous.

### Base result

Executed with physical GPUs 3 and 4 and `--network none`:

```text
FAIL: base GPUModelRunner has no direct GPU sampled-token broadcast/receive contract for async pipeline parallelism: ['_pp_broadcast_prev_sampled_token_ids', '_pp_receive_prev_sampled_token_ids_to_input_batch']
RC=1
```

The real config preflight succeeds first: async scheduling plus PP2 is allowed.
The failure is therefore the intended missing production GPU token path, not a
configuration or environment failure.

### Isolated Oracle result

Only head `vllm/v1/worker/gpu_model_runner.py` was mounted read-only:

```text
api_preflight=PASS async_pp_config=true methods=present
NCCL version 2.27.5+cuda12.9
rank0_received tokens=[[101], [202]] mapping={'keep': 0} keep_output=[7, -1] discard_output=[9]
PASS: production async-PP methods broadcast sampled tokens over two-rank NCCL and rebuilt receiver request state
rank0_gpu=NVIDIA A100-SXM4-40GB capability=8.0 uuid=8380fa1c-d192-a7e4-ec39-ab836d0f4fd8 world_size=2
RC=0
```

This proves real NCCL broadcast/receive, receiver tensor contents, discard-mask
handling, request-index reconstruction, and local output placeholder update.
It does not exercise the separate scheduler re-entry change.

### Integrity probes

- Runtime user: `uid=1000(agent)`; create/delete probe in `/workspace` passed.
- Candidate source: `/workspace/repo/vllm/__init__.py`.
- Candidate native binding: `/workspace/repo/vllm/_C.abi3.so`.
- Torch `2.9.1+cu129`, CUDA `12.9`; `VLLM_TARGET_DEVICE` is absent.
- GPU 3: `NVIDIA A100-SXM4-40GB`, capability `8.0`, UUID
  `8380fa1c-d192-a7e4-ec39-ab836d0f4fd8`; CUDA tensor operation passed.
- Git: branch `benchmark-base`, one commit, zero remotes, clean status, tree
  `27422138dd790ac7992e774d438e0bf84d546c01`.
- Runtime `--network none`: `/proc/net/route` data rows `0`.
- Image history proxy matches: `0`; final config proxy variables: `0`.
- Build verified exactly eight native artifacts and two generated Python shims;
  production-target/native intersection is empty.
- Anti-leak hashes:
  - scheduler base/Agent:
    `96f7360982899fffdbd627f51e3daf8afbe7a79fad5dc17d6dc0eb093aa516a0`;
    head: `c065763224110bea00b5bc130b1f7a9e10719420d2194876dd9c82be5b734a1d`.
  - GPUModelRunner base/Agent:
    `2c3fe21e67718201f5afb184aa3a967902cb5a09e041f1f5d8aeef77bf8919af`;
    head: `052172e67c3b4fabfbe32f88ed45e2a7ed6c829177a1842ce72a97b7c601a4fa`.

## State separation

- Agent image: exact survey base source plus scoped donor runtime; no PR head
  file or solved code.
- Base: deterministically fails API preflight because the PP GPU token methods
  do not exist.
- Focused Oracle: mounting only head `gpu_model_runner.py` passes the real
  two-rank NCCL behavior.
- Full verifier: additionally exercise head scheduler behavior, PP4 model
  serving, accuracy, and paired performance.

## Survey-manual feedback

- Validate survey base/head ancestry separately from merge SHA semantics;
  GitHub squash commits have one parent and cannot prove base/head ancestry.
- For distributed changes, a focused verifier should use the real collective
  backend when local hardware permits it, while explicitly separating model
  and topology scale claims.
- Performance numbers from the PR are evidence for a full verifier design, not
  a portable threshold for a smaller GPU count or different model.
- Later bug reports define generalization dimensions that a full verifier must
  add; they do not automatically invalidate a narrower deterministic Gold.
- Offline multi-process tests should pin the rendezvous address to loopback;
  `torchrun --standalone` may select a container hostname that cannot resolve
  after Docker networking is disabled.

## Remaining risk

The v0.14.1 native donor is ABI-compatible and pre-cutoff but four days older
than the exact base rather than an exact-SHA native build. Both target files
are Python and the target/native intersection is empty, bounding this risk.

The focused Oracle validates only the direct GPU sampled-token path. A complete
Gold must also mount/validate the scheduler change, run PP4 model forwards, and
cover known later-risk dimensions: multi-node transport, chunked scheduling,
KV offload, and different PP sizes.
