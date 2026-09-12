# Node-local DP supervisor

One `vllm serve` invocation launches the local DP ranks on consecutive API ports. The supervisor aggregates readiness, honors configurable health probes and cleans up the full owned process tree on failure or termination. The user contract is in `instruction.md`.

The CPU environment supplies the exact frozen Base and ordinary dependencies. See `environment/lock/README.md` for the immutable image and source-build provenance. Tests and solutions remain outside the agent image.

The verifier runs the public CLI and actual API server lifecycle. Model execution and model-specific HTTP routes use controlled producers, while child processes, nested listeners, rank and device assignment, probe requests, signals and cleanup remain observable behavior. It also runs ordinary serving without the new mode. The candidate's helper names, supervisor class, process titles and internal bookkeeping are not scored.

`validation/ci-cases.json` lists controls against the current task. The prior task and its earlier results are archived under `validation/history/pr54-9cc04b5/`; they do not certify this revision. Current results and remaining limitations are recorded in `validation/e2e-evidence.json` and `validation/review-report.md`.

Task 1.2.0 adds cleanup checks for descendants that start a separate session. It retains the original instruction and inherited-session cases. Task 1.1.0 evidence is preserved under `validation/history/task-1.1.0/`; its Codex reward 1 is a historical false positive, not acceptance of the revised verifier.
