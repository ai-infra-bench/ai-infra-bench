Current version 0.0.9: [review, six formal controls and eight existing-patch replays](validation/v009-review.md). The next independent G56/G6 matrix has not started. Historical results below remain bound to their recorded snapshots.

# Checked session model migration

Implement [the migration request](instruction.md) in DeepSeek Harness: admit a session-local model change only when retained work fits the destination, preserve the selection across reopening, and support opt-in Chat Completions and Responses gateways that need historical plaintext reasoning with tool calls.

This is a constructed feature scenario informed by upstream discussions [#1780](https://github.com/deepseek-ai/deepseek-harness/discussions/1780) and [#1410](https://github.com/deepseek-ai/deepseek-harness/discussions/1410). It does not claim to reproduce a historical deployment or prescribe a community patch. [HelpMatey PR #1](https://github.com/HelpMatey/deepseek-harness/pull/1) addresses related compaction behavior; this task deliberately checks migration without automatic compaction.

## Environment

Base is `deepseek-ai/deepseek-harness@4e84901e6471b79ec0338099867ebb4606d12bb5`, dated September 1, 2026. The image contains the complete source and its locked dependencies, Node 22.23.2, pnpm 11.7.0, Python, Git, build tools, and ripgrep. It uses 4 CPUs, 8 GiB RAM, 20 GiB storage, and a 36,000-second agent budget. Agent and verifier run offline; protocol fixtures use loopback HTTP. No real model credentials or GPUs are required.

The Dockerfile pins the parent image and Debian snapshot, checks out only Base history, and removes fetch metadata, remotes, tags, reflogs, and unreachable objects. Tests, solutions, and control patches enter only after the agent phase. The built image identity and dependency provenance are recorded in `environment/`.

## Verification

The version 0.0.9 verifier executes 41 deterministic SDK/operation cases through the existing Session Controller business operation, real Loader composition, LLM runtime, pi-ai serialization, session projections, token meter, agent loop, and tools. Positive capacity cases resolve actual provider profiles. External model-generated HTTP events are deterministic; missing-metadata and concurrency cases substitute only the relevant external boundary. The work tool writes a real file, and the follow-up request must include its result.

| Cases | Observable behavior |
|---|---|
| Migration workflow | Historical calls and results survive; a reopened session continues on the destination and executes another tool; rejected migration can continue on its original model |
| Admission | Exact fit, complete history and request overhead, explicit versus adapter-default output allowance, unknown capacity, empty sessions, queued/running sessions, stale asynchronous checks |
| Compatibility | Provider and model changes, ordered plaintext reasoning, foreign metadata removal, parallel call pairing, native replay fidelity, missing reasoning, default-off behavior, configuration rejection |
| Regression | Legacy model selection remains permissive and persists the deployment default |
| Interacting boundaries | Explicit output allowance on empty sessions and after reopening; inherited catalog protocol; distinct provider tool IDs with shared pipe prefixes, long prefixes, punctuation normalization and known-provider routing |

Nine additional cases launch the actual DSH CLI web host, invoke public Remote operations, execute Bash tools, stop the process, and cold-open the same JSONL/Zstd files in a second process. They cover cross-provider and same-provider Chat migration, Chat-to-Responses migration, explicit allowances on empty sessions, rejection, destination defaults, sibling-session isolation, and immutable durable history. A strict loopback HTTP/SSE provider validates outgoing requests before returning deterministic model events. Only model computation is substituted; DSH, SDK serialization, persistence and tools run for real.

Reward is binary: all 41 SDK/operation cases and all nine process cases must finish and pass. Harbor transfers a source patch into a separate verifier container with clean, pinned dependencies. Agent-side test runners and Git state are not transferred. The root-owned runner rebuilds candidate host bundles and starts candidate code as UID 65534, with no new privileges; the Python parent owns the report directory, initializes reward to zero, and checks exact test names, completion, pass counts, skipped counts, and child status. Tests assert gateway content and call pairing without prescribing the internal projection function or generated call-ID spelling.

## Current validation

Version 0.0.9 removes a private catalog-helper fixture dependency and detects reuse of source-route budget estimates. It also checks Responses reasoning migrated into Chat and native replay after returning to the source. Six formal Harbor controls match their expected outcomes; eight unchanged first-round patches were regraded separately. See [the current review](validation/v009-review.md) and [execution evidence](validation/e2e-evidence.json).

## Historical validation

The [September 13 independent review](validation/session-method-review-20260913.md) found three issues in that historical revision: reasoning-only Chat assistants are lost, two configuration tests require unspecified error text, and the durable-history observer decodes only the first Zstd frame. The passing results below remain historical execution evidence; those findings were subsequently repaired; they do not describe the current revision. The [review method](validation/session-review-method-20260913.md) and counterexample evidence are recorded separately.

Version 0.0.5 promotes actual process restart and Chat reasoning checks into the mandatory offline score. Both the Oracle and the correct alternative pass all 36+7 cases twice. Base and all ten negative controls score 0. Final Harbor rewards are Oracle=1, early-exit=0 and forged-report=0, without framework exceptions. See [the historical v0.0.5 review and its evidence](validation/v005-review.md).

The eight original model patches have also been [regraded directly against v0.0.5](validation/v005-eight-patch-regrade.md), with no new model calls or source edits. New Chat requirements are reported separately from failures of the original contract.

Previous GPT-6/GPT-5.6 results apply to the historical verifier revision on which they ran. This update does not recompute their pass@4 or claim those submissions pass v0.0.5. The former task, Oracle, controls and evidence are preserved in `validation/history/v004-before-v005.tar.gz`; earlier reviews and trajectory archives remain unchanged.

The full DSH live-model experiments are separate supplemental evidence in `validation/dsh-chat-real-review-20260912.md`. Offline scoring requires neither internal endpoints nor credentials and does not score model answer quality. The Responses fixture checks the explicitly declared gateway extension; it does not claim that every public Responses API accepts that extension.

## Layout

```text
instruction.md                    Agent-facing feature request
task.toml                        Harbor configuration
 environment/Dockerfile           Clean Base environment
 environment/image-manifest.json  Built image identity
 environment/verifier-image-manifest.json Separate verifier image identity
 environment/lock/manifest.json   Dependency provenance
 solution/solve.sh                Oracle entrypoint
 solution/feature.patch           Reference code, docs, and source tests
 tests/                           Behavioral verifier and external fixtures
 tests/Dockerfile                 Clean verifier with curator-only tests
 validation/ci-cases.json          Correct alternative and wrong controls
 validation/*.patch               Full patches against Base, curator-only
 validation/e2e-evidence.json      Final executable hashes and run evidence
 validation/v009-review.md         Current scenario, environment, and verifier review
```

## Running

From the benchmark repository:

```bash
harbor run -p tasks/dsh-session-model-migration -a nop -e docker
harbor run -p tasks/dsh-session-model-migration -a oracle -e docker
harbor run -p tasks/dsh-session-model-migration -a codex -m <model> -e docker
python .github/scripts/task_ci.py validate dsh-session-model-migration
```

The task remains in development. The reference is newly authored rather than a merged upstream PR. Changing executable task files requires rerunning the affected Base, Oracle, controls, and Harbor cases.
