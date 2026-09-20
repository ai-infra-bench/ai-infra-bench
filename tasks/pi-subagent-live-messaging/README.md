# Pi subagent live messaging

Add optional communication between workers in one parallel Pi subagent dispatch.
The [statement](instruction.md) defines observable delivery behavior while
leaving tool names, schemas, addressing conventions, and transport to the solver.
The task remains in development.

## Environment

The Dockerfile pins Pi at `71dca871bc80b6bc97be37f0ca3189399d651fff`,
Node 22.23.2, a Debian snapshot, installed lockfile dependencies, and the release's
generated model catalogs. The agent runs offline with 4 CPUs, 8 GiB RAM and a
36,000-second allowance. Pi runs directly from TypeScript source.

## Verification

The verifier requires all 24 behavior cases to pass. It uses real Pi parent/child
processes, a scripted model endpoint, and controlled external work to observe
actual model input, delivery order, isolation, lifecycle behavior, queue pressure,
transport failures, and declared UTF-8 payload limits. It does not measure
autonomous collaboration gains.

Candidate Pi processes run under an unprivileged UID with no supplementary
groups and `no_new_privs`. The trusted scorer owns the tests and reports, checks
completion, and writes reward 0 for missing results or premature exit.

`tests/binding.py` describes the reference public interface. A reviewer can supply
`--binding PATH` to `verify.py`; the Harbor entry point uses
`/tests/interface_binding.py` when supplied by the curator. Bindings translate
public calls and results; they must not implement delivery or rewrite recipient
model input. New interfaces require reviewed integration; a missing binding
must not be reported as a feature failure.

`validation/ci-cases.json` declares the retained alternative implementation and
negative controls, with patch hashes and expected rewards.

## Running

```bash
harbor run -p tasks/pi-subagent-live-messaging -a nop -e docker
harbor run -p tasks/pi-subagent-live-messaging -a oracle -e docker
python .github/scripts/task_ci.py validate pi-subagent-live-messaging
```
