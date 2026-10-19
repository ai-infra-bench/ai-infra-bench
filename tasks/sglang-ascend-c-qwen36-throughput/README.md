# Native SGLang throughput on Ascend C

This is a native serving optimization task under `tasks/`, using a task-local floating-point score. `task.toml` declares `gpu_types = ["Ascend C"]`; `metadata.task_type` remains `performance`. The hardware is Ascend 910C (A3): eight 64 GiB NPU dies in the development resource budget, with two dies per measured TP2 serving instance. The other six dies are available for independent experiments; do not overlap work on the measured pair. CI integration is intentionally out of scope. The task does not prescribe an optimization method.

The image contains native SGLang, its official Ascend kernels, PyTorch and the vendor runtime. Model weights are an external read-only asset. Task tests, expected answers and reference results are not baked into the agent image. Do not expose tests or historical optimized solutions during an agent run. The quality suite contains 40 code cases (19 MBPP and 21 HumanEval), 35 mathematics cases (25 GSM8K and 10 multi-step arithmetic), and 25 IFEval instruction-following cases. It retains the 72 historical regression cases and adds 28 cases selected before model evaluation; selection provenance is frozen in `tests/quality100/selection.json`. It is not an unbiased model capability benchmark. Suite status metadata records its state at selection time; actual validation results are separate run artifacts. The 100-case suite requires its own native baseline validation; a historical 72/72 result does not establish 100/100.

## Baseline qualification

The benchmark is intended to measure further improvement over a well-optimized native deployment. Select a recent official Ascend release with its complete matched runtime stack, apply applicable documented optimizations within the task's fixed BF16/workload contract, and validate correctness and stable throughput before freezing the baseline. A newer version number alone does not prove a strong baseline. Freeze the exact image digest, source commit, launcher and configuration; changing any of them requires a new baseline and separate comparison group. Existing optimizations must not be disabled merely to inflate the measured gain.

The currently checked-in 0.5.12/CANN 8.5.0 image is the validated construction environment, not yet the final qualified baseline for this objective. Upgrading and qualifying the reference deployment remains a prerequisite to a formal optimization run. Do not silently relabel historical measurements as a baseline for a newer stack.

## Build and collect

This README and the task repository are operator inputs, not an agent workspace. Give the agent `instruction.md` and the built native development image only. For a development container, override the image command with `sleep infinity` and let the agent start its own serving experiments. During development, mount only the model and the candidate workspace; do not mount this repository, `tests/`, `validation/`, grader outputs, baseline responses, or an experiment archive. The image build context is `environment/`, and its Dockerfile copies only `app/` and `lock/`.

Follow the same visibility boundary as the repository's other tasks: private tests are supplied only after the agent phase. Stop the agent and its background processes and save its final workspace before beginning verification. The `/tests:ro` mount in the example below belongs exclusively to that verification phase. Run the CPU grader from a trusted operator environment. Never return that verification container to an agent; remove its private mounts/files and use a fresh development container for another attempt. Model inputs necessarily reach the serving process during inference; the boundary prevents advance access by the optimization agent, not a claim that candidate model code cannot observe its own requests.

Build on the matching arm64 Ascend host. The host driver must support CANN 8.5.0. Prepare the official Qwen3.6-27B weights and retain their file hashes before evaluation. Do not fetch weights during a timed task.

```bash
docker build -t sglang-ascend-c-task:local environment
python3 tests/check_assets.py --model-path /absolute/path/to/Qwen3.6-27B
mkdir -p /absolute/path/to/results
```

Choose an unused pair of dies and confirm that no other service owns them. The following example uses dies 0 and 1. Mount device/driver paths appropriate to the host; do not use `--gpus all` for NPU allocation. This host profile uses the Ascend privileged container setup and host networking. Port 30000 binds only to loopback. Model/package downloads are disabled; host networking itself is not an egress firewall. Apply an external egress policy when isolation is required.

```bash
docker run --rm --name native-sglang-check \
  --network host --privileged --shm-size 16g --cpus 16 --memory 128g \
  --device /dev/davinci0 --device /dev/davinci1 \
  --device /dev/davinci_manager --device /dev/devmm_svm --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver:ro \
  -v /usr/local/dcmi:/usr/local/dcmi:ro \
  -v /usr/local/Ascend/add-ons:/usr/local/Ascend/add-ons:ro \
  -v /etc/ascend_install.info:/etc/ascend_install.info:ro \
  -v /absolute/path/to/Qwen3.6-27B:/models/Qwen3.6-27B:ro \
  -v "$PWD/tests:/tests:ro" \
  -v /absolute/path/to/results:/results \
  -e ASCEND_RT_VISIBLE_DEVICES=0,1 \
  sglang-ascend-c-task:local \
  python3 /tests/collect.py --output /results/smoke-01 --mode smoke
```

`smoke` performs all 100 quality inference requests at concurrency 8 and a short generation at each of 1K, 4K, 16K and 64K. It checks real deployment but has no optimization score. `--mode full` retains the same quality cases and runs the full C16/16-request/1024-output matrix with at least one warmup and three compilation-clean measurements per length, with at most 12 total attempts to accommodate lazy shape specialization. Compilation-clean means no changes in the observed Triton cache metadata across a measured batch, after full warmup; it does not independently audit every possible vendor compiler cache. An empty cache is allowed for native or precompiled implementations; it is not evidence about compilation in other backends. Use a new output directory for every run. The collector stops its own model process on completion or failure. Preserve failure.json and server.log when a run fails; a server exit is not an accuracy result.

Baseline and candidate must both use the 16-request, concurrency-16 workload. Earlier 32-request or 64-request measurements are historical records and cannot serve as this workload's baseline; collect a fresh baseline after changing the workload.

For the initial baseline use the unchanged source and `/workspace/task/baseline.json`. For a candidate use its saved source checkout and an explicit configuration, for example `--config /workspace/task/candidate.json`. Fresh processes and independent compilation caches are required on both sides. Never compare different model weights, devices, precision or evaluator versions. The index hash identifies the shard inventory; it does not replace a trusted hash of the weight contents.

## CPU grading and scoring

Use `tests/test.sh` as the task verification entrypoint; the other Python modules are implementation helpers. Run the verifier on a trusted CPU host, outside the candidate process. Accept collection directories only from a fresh harness-controlled run; the score script does not attest arbitrary agent-supplied JSON reports. It needs Python, the pinned packages in `tests/requirements.txt`, Docker, and a preloaded CPU Python 3.11 sandbox image. Resolve that image to a local `sha256:...` ID. Model-generated code runs only in disposable CPU containers with no network, read-only filesystems and CPU/memory/PID limits. For the Python-answer checker, assertions and expected answers stay in the trusted host process: each container receives only candidate source and function inputs, and returns bounded data-only values. Candidate code cannot report test completion or mutate the host assertion list. No pickle or candidate-defined Python objects cross this boundary. The NPU container does not need Docker access. Package installation is preparation, not part of the offline timed run.

```bash
python3 -m venv verifier-venv
verifier-venv/bin/pip install -r tests/requirements.txt
docker build -f tests/code-sandbox.Dockerfile -t ascend-task-code-sandbox:local tests
TASK_CODE_IMAGE_ID=$(docker image inspect ascend-task-code-sandbox:local --format '{{.Id}}')
# Activate this environment, with Docker access, before using the entrypoint.
source verifier-venv/bin/activate
bash tests/test.sh --collection /absolute/path/to/results/smoke-01 \
  --output /absolute/path/to/graded/smoke-01 --code-image "$TASK_CODE_IMAGE_ID" --smoke
```

For a full baseline, first collect a new run with `--mode full`, then grade it without `--smoke`. Its validated `score/summary.json` becomes the frozen baseline. For a full candidate, pass `--baseline /absolute/path/to/graded/baseline/score/summary.json`. The verifier grades the fresh 100 responses, recomputes each measured batch and pooled metrics from retained raw requests, checks warmup/compilation exclusions and complete request coverage, rejects incomplete or modified workloads, and computes the four-length geometric mean with per-length ratios and variation. Both the top-level `summary.json` and `score/summary.json` report the same task-local result, and `reward.txt` contains its floating-point score. Baselines have `score: 1.0`. Correct, complete candidates have `status: VALID` and retain their full continuous score, including values below 1.0. Failures have `valid: false` and `score: 0.0`; their status distinguishes invalid measurements, infrastructure errors and late completion. A smoke check also scores 0.0 and is diagnostic only. Small improvements remain visible; report variation and repeat runs rather than converting them to binary success.

For an eight-hour run, the trusted runner owns the timer, job lifecycle and best-result selection. The task verifier takes an optional `--deadline <unix-seconds>` expressed on the same CPU host where verification runs. It checks local validation completion against that local deadline; remote collection timestamps are diagnostic only and are never compared with local time. The runner must independently bind each fresh job and its returned artifacts to the submitted source/configuration and frozen baseline, and record receipt before its budget expires. Use the runner's own monotonic clock for elapsed-budget accounting. A timestamp, checksum or agent-authored report alone is not proof of a fresh measurement. This task does not require a campaign protocol, trial receipt or separate leaderboard. Initial preparation and the baseline are outside the eight-hour budget; partial or late evaluations score 0.0. The six-hour timeout limits an individual evaluator invocation and does not extend the overall budget.

## Construction checks and limitations

```bash
python3 validation/tools/test_verifier.py
python3 validation/tools/check_quality_oracles.py --output /absolute/path/to/new-oracle-controls.json --code-image "$TASK_CODE_IMAGE_ID"
TASK_NATIVE_IMAGE_ID=$(docker image inspect sglang-ascend-c-task:local --format '{{.Id}}')
python3 validation/tools/check_agent_visibility.py --image "$TASK_NATIVE_IMAGE_ID" --output /absolute/path/to/new-visibility-audit.json
python3 validation/tools/check_response_controls.py --responses /absolute/path/to/results/full-01/quality/responses.json --output /absolute/path/to/new-response-controls --code-image "$TASK_CODE_IMAGE_ID"
```

The first command exercises verifier accounting using synthetic reports. The second checks all 100 reference answers or constraint witnesses, rejects deliberately incorrect answers, and checks truncation handling. Language detection uses a fixed seed and completes initialization before parallel grading; the official strict checker files remain unchanged; candidate code runs in the isolated CPU sandbox while trusted assertions run outside it. The visibility check starts a fresh container with no host mounts and checks that private task files are absent. The response controls invoke the real host verification entrypoint with wrong code, wrong mathematics, violated instructions, truncation, excess output tokens, missing/duplicate cases, and a mismatched suite hash; each must be invalid with a floating-point score of 0.0. A test-list mutation and early successful exits are also exercised as grader controls. These are grader and isolation controls, not additional model inference or performance measurements. Real smoke, full baseline, reference improvement, incorrect-solution controls and noise validation must be reported separately. No native optimization gain is claimed from a baseline replay or synthetic scoring fixture. Historical results from other environments must not be used as this task's baseline. The 35B-A3B model is reserved for later validation of a frozen optimization method, not for tuning this task's implementation.

This direct Docker/host-verifier interface intentionally precedes full Harbor integration. The task writes its continuous reward directly; no shared scoring protocol or leaderboard is added. The existing binary result archive cannot yet consume nonbinary rewards, so a standalone float result is not a claim of shared leaderboard integration. The repository's A100-only validator and its default 10-hour/2-hour budgets do not apply to this local Ascend profile; they have not been modified. A native task image and portable scripts do not, by themselves, constitute a Harbor CI pass.

The model-side collection boundary still needs hardening before use with untrusted submissions: the current verification container exposes private test assets to candidate model code, and its intermediate timing files are writable from that container. Read-only test mounts protect file integrity, not answer confidentiality. Host-side regrading and report consistency checks do not authenticate candidate-side timings. Move request generation, golden answers, authoritative clocks and result storage into a trusted controller before claiming tamper-resistant optimization rankings. Current native results and CPU replays establish functionality only within the documented trusted-collection assumption.
