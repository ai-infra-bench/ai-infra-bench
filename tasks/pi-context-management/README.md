# Pi model-managed context windows

Implement an optional Pi extension that lets the model save working notes,
request a fresh context, and retrieve original evidence while pursuing one goal
in one persistent session. The short [statement](instruction.md) defines five
minimal tools. Storage layout, acknowledgement metadata and search ordering
remain implementation choices.

This is version 0.0.2. It replaces the former six-tool, named-note and pagination
contract. Current review and evidence live in [validation/v2](validation/v2/review.md).
Older top-level validation reports describe v1; its control patches are retained
under `validation/v1`. No solver-model pilot has been run for v2.

## Environment

Pi Base is `71dca871bc80b6bc97be37f0ca3189399d651fff`, release 0.85.1. The CPU-only
image provides Node 22.23.2, installed lockfile dependencies, frozen model catalogs,
Python, Git and ripgrep. Code runs directly from TypeScript in `/workspace/pi`.
The agent has 4 CPUs, 8 GiB memory, no network and a 36,000-second allowance.

The environment is unchanged from v1. The validated CPU-runner image is
`ai-infra-bench/pi-context-management:base-71dca871bc80`, ID
`sha256:95b13c4082432f20c58dda2919767637393dc0cb2374890c1e235ed71a036a87`.
It is cached on that runner, not published to a registry. Codex source and
benchmark tests/solutions are never installed in the agent image.

## Behavior verification

The verifier starts real Pi CLI processes and drives them with deterministic
model responses over loopback HTTP. Pi's provider adapters, tools, context hooks,
session persistence and process restart all execute. The trusted parent observes
actual outgoing model requests; candidate Pi runs under the agent UID with
separate writable state. No paid model or LLM judge is used.

Twelve scenarios cover disabled behavior, an empty reset, context rollover,
repeated resets, restart, Unicode note replacement, selective original-history
recovery, completion of the switching tool batch, session isolation, Responses
compatibility, clearing notes across restart, and eleven consecutive resets with unchanged notes. See
[coverage.json](validation/v2/coverage.json). Reward is 1 only when every scenario
finishes and passes. Successful early process exit alone does not pass.

The principal source test is Codex's
`new_context_tool_skips_auto_compact_fallback`: script the reset request, inspect
the next actual context, and continue normal tool use. This task deliberately
adds local persistence and explicit goal/user-instruction retention. See
[source alignment](validation/v2/source-alignment.json).

Current formal results and job identities are recorded in
[test-update-results.json](validation/v2/test-update-results.json). Base and incorrect
controls receive 0; the reference and an alternative using separate JSON note
storage receive 1. The alternative also changes search order and optional return
metadata. Base and Oracle retain the same five pre-existing typecheck errors.

## Layout and running

- `instruction.md`: solver request and minimal callable interface.
- `environment/`, `task.toml`: frozen Base and Harbor configuration.
- `solution/`: reference implementation patch and installation script.
- `tests/`: scripted provider, independent scorer and reward entrypoint.
- `validation/ci-cases.json`, `validation/v2-*.patch`: current controls.
- `validation/v2/`: current provenance, behavior mapping, review and evidence.

```bash
harbor run -p tasks/pi-context-management -a nop -e docker
harbor run -p tasks/pi-context-management -a oracle -e docker
```

These commands build the Dockerfile. To reuse the validated CPU-runner image,
set `[environment].docker_image` to its tag in a temporary task copy, as the
recorded formal runs do. Implementation/verification results are ready for
continued joint review; they do not establish autonomous model strategy quality.

## Real-model usage pilot

The v2 reference extension was also used by real GPT-6 Astra and GPT-5.6 Sol models.
GPT-6 completed the workflow; GPT-5.6 repeated context switches and completed
after a documented operator interruption/recovery. These are directed usage
trials, not solver results or autonomous timing evaluation. See
[the live-model review](validation/v2/live-model-review.md).

Live-runner code, completion and efficiency metrics, offline trace replay, and
regression tests are now maintained in [validation/live](validation/live/README.md).
Efficiency diagnostics do not affect the deterministic benchmark reward.

The latest [observer regression results](validation/v2/test-completion-review.md)
cover 21 unit tests, full re-scoring of saved live traces, and two rejected
premature-evidence counterexamples; no new model calls were made for that update.
