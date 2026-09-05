# vLLM Model Runner V2 selection

## What the task asks

Implement tri-state behavior for `VLLM_USE_V2_MODEL_RUNNER` and propagate the resolved selection through `VllmConfig`/`GPUWorker` consistently.

## Environment

- Base image: pinned digest in `environment/Dockerfile`
- Workdir: `/workspace/repo`
- Runtime policy: offline (`network_mode = "no-network"`)
- GPU: one A100-class accelerator
- Agent budget: 10 hours

## Verifier

- A root-owned supervisor runs candidate imports in an unprivileged child and
  keeps reward fail-closed until all required cases are accounted for
- Checks defaults across Qwen3/Qwen2, generation/pooling and supported/
  unsupported features, explicit overrides, startup errors, and the real GPU
  worker consumption path
- Reward is written by the candidate-independent supervisor to
  `/logs/verifier/reward.txt`

## Layout

- `instruction.md`: user-facing behavioral contract
- `task.toml`: task config and resource constraints
- `environment/`: deterministic base and native runtime checks
- `solution/`: Oracle patch + solve script
- `tests/`: behavioral + hidden-mode checks
- `validation/`: control manifest and evidence for the frozen snapshot

## Run

- Oracle: `harbor run -p tasks/vllm-runner-v2-selection -a oracle`
- Agent: `harbor run -p tasks/vllm-runner-v2-selection -a agent -m claude-opus-4-8`

## Permission and interpreter follow-up

Trusted harness scripts are staged into a protected container-local directory,
outputs remain root-writable but readable by Harbor, and worker execution
preserves the selected virtual-environment Python path. GPU/Harbor/control runs
were not repeated at the maintainer's request. Prior runtime results are archived
under `validation/history` and do not certify this modified verifier.
