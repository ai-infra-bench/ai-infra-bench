# Checked session model migration

Implement [checked session model migration](instruction.md) in DeepSeek Harness:
admit a model change only when retained work fits the destination, persist the
selection across reopening, and support opt-in plaintext reasoning replay for
Chat Completions and Responses gateways.

This constructed feature scenario is informed by upstream discussions
[#1780](https://github.com/deepseek-ai/deepseek-harness/discussions/1780) and
[#1410](https://github.com/deepseek-ai/deepseek-harness/discussions/1410).
The reference implementation is newly authored; the task remains in development.

## Environment

The Dockerfiles pin DeepSeek Harness at
`4e84901e6471b79ec0338099867ebb4606d12bb5`, Node 22.23.2, pnpm 11.7.0,
a Debian snapshot, and the upstream dependency lockfile. Dependency provenance
is recorded in `environment/lock/manifest.json`.
The agent and verifier run offline with 4 CPUs and 8 GiB RAM. Tests use loopback
HTTP fixtures and require no model credentials or GPUs.

## Verification

The verifier requires all 41 SDK/operation cases and nine process cases to pass.
It checks destination capacity, durable selection, historical tool calls and
results, reasoning compatibility, rejection, concurrency, and legacy behavior.
Process cases launch the real CLI host, execute tools, and cold-open persisted
sessions in a second process. Only provider responses are scripted.

Harbor transfers the candidate source patch to a separate verifier container.
The trusted scorer checks exact case names, completion and child status; missing
results or early exits receive reward 0. The Responses reasoning fixture covers
the gateway extension declared in the statement.

`validation/ci-cases.json` declares the retained alternative implementations and
negative controls, with patch hashes and expected rewards.

## Running

```bash
harbor run -p tasks/dsh-session-model-migration -a nop -e docker
harbor run -p tasks/dsh-session-model-migration -a oracle -e docker
python .github/scripts/task_ci.py validate dsh-session-model-migration
```
