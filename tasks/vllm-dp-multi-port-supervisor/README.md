# Node-local DP supervisor

One `vllm serve` invocation launches the local DP ranks on consecutive API ports. The supervisor aggregates readiness, honors configurable health probes and cleans up the full owned process tree on failure or termination. The user contract is in `instruction.md`.

The CPU environment supplies the exact frozen Base and ordinary dependencies. See `environment/lock/README.md` for the immutable image and source-build provenance. Tests and solutions remain outside the agent image.

The verifier runs the public CLI and actual API server lifecycle. Model execution and model-specific HTTP routes use controlled producers, while child processes, nested listeners, rank and device assignment, probe requests, signals and cleanup remain observable behavior. It also runs ordinary serving without the new mode. The candidate's helper names, supervisor class, process titles and internal bookkeeping are not scored.

The [validation summary](validation/README.md) records the tested version, results, limitations and a fixed download link to the detailed evidence ZIP. `validation/ci-cases.json` and its patches remain in the task because CI executes them.
