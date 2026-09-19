# vLLM KV connector lifecycle

Remove the retired external KV connector constructor without breaking current plugins. The developer request is in [instruction.md](instruction.md).

The image contains the exact vLLM Base, its reachable Git history and a pinned v0.20.1 runtime. The task runs offline on CPU with a 10-hour agent budget.

The verifier enters through the production factory and worker lifecycle APIs. External plugins supply deterministic inputs and observable constructor/shutdown callbacks. It checks both roles, constructor forwarding, the identity and contents of nonempty cache configurations, repeated initialization, shutdown/reinitialization, argument errors, plugin exceptions and rejection of the retired API. No private lookup helper or lifecycle storage layout is prescribed.

A root scorer drives individual operations in an unprivileged candidate process and checks each response. Candidate stdout is diagnostic only. A success marker, an exit code, or a self-reported aggregate score cannot complete the checks. This is behavioral verification of Python plugin APIs, not a general sandbox proof against arbitrary native-code attacks.

Run the Oracle with `harbor run -p tasks/vllm-kv-connector-lifecycle -a oracle --env docker`. Controls are declared in `validation/ci-cases.json` and can be prepared with the repository's `task_ci.py prepare-case` command. [The coverage map](validation/coverage.md) explains both directions of the statement/verifier contract. [Current evidence](validation/e2e-evidence.json) identifies the tested snapshot; files under `validation/history/` do not certify it.
