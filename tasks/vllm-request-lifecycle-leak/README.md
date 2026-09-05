# vLLM request lifecycle retention

## What the Agent does

Ensure completed requests release request-owned multimodal payloads promptly without breaking prefix-cache bookkeeping. The user-facing contract is in [instruction.md](instruction.md).

## Environment

A digest-pinned vLLM CPU image with the exact Base source, offline runtime, and a 10-hour Agent budget. Its image must be rebuilt after removing Agent-visible reproduction assets.

## Verifier

The separate hidden verifier uses a root-owned supervisor to drive eleven
independent observations through production Scheduler lifecycle operations.
It covers normal completion, cancellation, streaming continuation/end, live
ownership, prefix-cache hashing, and prompt/multimodal reclamation. Candidate
code runs as the unprivileged Agent user; only the supervisor owns expectations
and the binary reward written to `/logs/verifier/reward.txt`.

## Layout

- `instruction.md`: user-facing behavioral request.
- `task.toml`: Harbor metadata, resources, isolation, and artifact paths.
- `environment/`: exact Base source image and dependency provenance.
- `solution/`: Oracle patch and application script, hidden from the Agent.
- `tests/`: separate-verifier entrypoint and behavioral checks.
- `validation/`: control manifest and evidence for the frozen snapshot.

## Running

With the canonical image available locally:

```bash
harbor run -p tasks/vllm-request-lifecycle-leak -a oracle
harbor run -p tasks/vllm-request-lifecycle-leak -a terminus-2 -m anthropic/claude-opus-4-8
```

## Permission-fix validation status

The verifier now stages trusted harness scripts independently of host UID and
keeps root-only write access while allowing Harbor to read outputs. Runtime
validation was not rerun for this change at the maintainer's request. Historical
results are retained under `validation/history`; they do not certify the current
verifier. Non-root host collection and the full control matrix remain pending.
