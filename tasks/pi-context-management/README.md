# Pi model-managed context windows

Implement an optional Pi extension that lets the model save working notes,
request a fresh context, and retrieve original evidence while pursuing one goal
in one persistent session. The [statement](instruction.md) defines five minimal
tools. Storage layout, acknowledgement metadata, and search ordering remain
implementation choices. The task remains in development.

## Environment

The Dockerfile pins Pi at `71dca871bc80b6bc97be37f0ca3189399d651fff`
(release 0.85.1), Node 22.23.2, a Debian snapshot, installed lockfile dependencies,
and the release's generated model catalogs. The agent runs offline with 4 CPUs,
8 GiB RAM and a 36,000-second allowance. Pi runs directly from TypeScript source.

## Verification

The verifier starts real Pi CLI processes and supplies deterministic model
responses over loopback HTTP. Provider adapters, tools, context hooks, session
persistence and process restart all execute. The trusted parent observes actual
outgoing model requests; candidate Pi runs under a separate unprivileged UID.

Twelve scenarios cover disabled behavior, empty reset, context rollover,
repeated resets, restart, Unicode note replacement, selective history recovery,
completion of the switching tool batch, session isolation, Responses
compatibility, clearing notes across restart, and eleven consecutive resets
with unchanged notes. Every scenario must finish and pass for reward 1.
These checks establish feature behavior, not autonomous model strategy quality.

`validation/ci-cases.json` declares the retained alternative implementation and
negative controls, with patch hashes and expected rewards.

## Running

```bash
harbor run -p tasks/pi-context-management -a nop -e docker
harbor run -p tasks/pi-context-management -a oracle -e docker
python .github/scripts/task_ci.py validate pi-context-management
```
