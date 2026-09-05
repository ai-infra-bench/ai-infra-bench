# vLLM multi-port DP supervisor

## What the Agent does

Add one supervised node-local process group for multiple data-parallel API endpoints behind an external load balancer. The user-facing contract is in [instruction.md](instruction.md).

## Environment

A digest-pinned vLLM image with the exact Base source, CPU execution for frontend orchestration, offline runtime, and a 10-hour Agent budget.

## Verifier

The separate hidden verifier enters through the public CLI, starts real HTTP child processes, and checks rank assignment, aggregate health, failures, signals, and socket cleanup. Full credit is binary and is written to `/logs/verifier/reward.txt`.

## Layout

- `instruction.md`: user-facing behavioral request.
- `task.toml`: Harbor metadata, resources, isolation, and artifact paths.
- `environment/`: exact Base source image and dependency provenance.
- `solution/`: Oracle patch and application script, hidden from the Agent.
- `tests/`: separate-verifier entrypoint and behavioral checks.
- `validation/`: control manifest and evidence for the frozen snapshot.

## Running

The TCP/process cleanup checks were tightened after the original PR validation.
At the maintainer's request, this revision has not been rerun through Docker or
Harbor. Prior results are retained as historical evidence and do not certify the
modified verifier. Publication remains pending validation.

To validate this revision:

```bash
harbor run -p tasks/vllm-dp-multi-port-supervisor -a oracle
harbor run -p tasks/vllm-dp-multi-port-supervisor -a terminus-2 -m anthropic/claude-opus-4-8
```

