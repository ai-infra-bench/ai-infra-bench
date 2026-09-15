# Checked session model migration

Implement [the migration request](instruction.md) in DeepSeek Harness: admit a session-local model change only when retained work fits the destination, preserve the selection across reopening, and support an opt-in Responses gateway that needs historical plaintext reasoning with tool calls.

This is a constructed feature scenario informed by upstream discussions [#1780](https://github.com/deepseek-ai/deepseek-harness/discussions/1780) and [#1410](https://github.com/deepseek-ai/deepseek-harness/discussions/1410). It does not claim to reproduce a historical deployment or prescribe a community patch. [HelpMatey PR #1](https://github.com/HelpMatey/deepseek-harness/pull/1) addresses related compaction behavior; this task deliberately checks migration without automatic compaction.

## Environment

Base is `deepseek-ai/deepseek-harness@4e84901e6471b79ec0338099867ebb4606d12bb5`, dated September 1, 2026. The image contains the complete source and its locked dependencies, Node 22.23.2, pnpm 11.7.0, Python, Git, build tools, and ripgrep. It uses 4 CPUs, 8 GiB RAM, 20 GiB storage, and a 36,000-second agent budget. Agent and verifier run offline; protocol fixtures use loopback HTTP. No real model credentials or GPUs are required.

The Dockerfile pins the parent image and Debian snapshot, checks out only Base history, and removes fetch metadata, remotes, tags, reflogs, and unreachable objects. Tests, solutions, and control patches enter only after the agent phase. The built image identity and dependency provenance are recorded in `environment/`.

## Verification

The version 0.0.3 verifier executes 28 deterministic cases through the existing Session Controller business operation, real Loader composition, LLM runtime, pi-ai serialization, session projections, token meter, agent loop, and tools. Positive capacity cases resolve actual provider profiles. External model-generated HTTP events are deterministic; missing-metadata and concurrency cases substitute only the relevant external boundary. The work tool writes a real file, and the follow-up request must include its result.

| Cases | Observable behavior |
|---|---|
| Migration workflow | Historical calls and results survive; a reopened session continues on the destination and executes another tool; rejected migration can continue on its original model |
| Admission | Exact fit, complete history and request overhead, explicit versus adapter-default output allowance, unknown capacity, empty sessions, queued/running sessions, stale asynchronous checks |
| Compatibility | Provider and model changes, ordered plaintext reasoning, foreign metadata removal, parallel call pairing, native replay fidelity, missing reasoning, default-off behavior, configuration rejection |
| Regression | Legacy model selection remains permissive and persists the deployment default |
| Interacting boundaries | Explicit output allowance on empty sessions and after reopening; inherited catalog protocol; distinct provider tool IDs with a shared pipe prefix |

Reward is binary: all 28 expected cases must finish and pass. Harbor transfers a source patch into a separate verifier container with clean, pinned dependencies. Agent-side test runners and Git state are not transferred. The root-owned runner starts candidate code in unprivileged workers; the Python parent owns the report directory, initializes reward to zero, and checks exact test names, completion, pass counts, skipped counts, and child status. Tests assert gateway content and call pairing without prescribing the internal projection function or generated call-ID spelling.

## Validation

Version 0.0.3 makes output-capacity enforcement explicit, preserves caller allowances before the first request, and corrects the error-wording and native-ID assertions. See [the current review](validation/v003-review.md) and [executed evidence](validation/e2e-evidence.json). Both complete reference implementations pass 28/28; Base and all eight negative controls receive 0. All 116 focused source regressions and the source compilation check pass. Final Harbor trials return Oracle=1, early-exit=0 and forged-report=0 with zero errored trials.

The earlier GPT-5.6 and GPT-6 statement-pilot results remain 14/22 and 22/22 under version 0.0.2. Regrading those unchanged answers against this revision gives 23/28 and 25/28, both reward 0. These are development regrades under an explicitly revised capacity contract. A single fresh GPT-6 high run is authorized; its result is tracked separately. The initial medium attempt was interrupted at the user’s request and is retained as an interrupted run. Historical task inputs and review evidence remain in `validation/history/`.

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
 validation/review.md              Scenario, environment, and verifier review
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
