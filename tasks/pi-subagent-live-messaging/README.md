# Pi subagent live messaging

Add optional communication between workers in one parallel Pi subagent dispatch.
The [v0.0.3 statement](instruction.md) defines observable delivery behavior while
leaving new tool names, schemas, addressing conventions, and transport to the solver.

## Current validation

Scorer **0.0.9** has **24 behavior cases**. Regrading the eight unchanged model
submissions gives **G6 4/4** and **G56 1/4** complete successes. Both observed
single-task pass@4 values are 1. G56 #1 fails ordered delivery, #2 fails ordered
delivery and partial broadcast, and #4 fails partial broadcast with an unhandled
EPIPE. See the [current report](validation/v9/REPORT.md).

The Oracle, renamed JSONL implementation, and RPC error-handling control pass
24/24. IPC/socket controls that hide partial failures fail that case; score
forgery and premature exit receive reward 0. The [scenario design](validation/v9/design.md)
documents real queue pressure, OS connection faults and declared UTF-8 size
limits. New arbitrary interfaces/transports still require reviewed integration.
The [v0.0.8 boundary controls](validation/v8/REPORT.md) remain historical evidence.
No new model samples were generated. Full release review remains pending.

The verifier uses real Pi parent/child processes, a scripted model endpoint, and
controlled external work. It observes actual model input and real transport
failures; it does not establish autonomous sharing or collaboration gains by a
real model. The provider's scripted output/context allowance accommodates the
boundary payloads without involving a paid model.

## Score integrity

Candidate Pi processes run as UID/GID 60000 with no supplementary groups and
`no_new_privs`; the trusted Python scorer runs separately as root with isolated
imports. Tests and live grading reports are root-owned. Candidate scratch space
is separate. All 24 required results must pass before reward 1 is written;
premature exit or missing results fail closed. Finished reports are exported
read-only for Harbor collection. Both supported reward filenames are owned and
written by the scorer.

All four attack controls passed their rejection checks on v0.0.7. Direct score
forgery and early exit were rechecked on v0.0.9 and still receive 0 through Harbor.
Re-run the security gate, including a passing Oracle, with:

```bash
python3 tasks/pi-subagent-live-messaging/validation/v9/run_regrade.py \
  --output /tmp/pi-messaging-security-check \
  --labels oracle forge_reward early_exit \
  --image ai-infra-bench/pi-subagent-live-messaging:base-71dca871bc80
```

The output directory must not already exist. Omit `--image` to build the task's
Dockerfile. This validates the reproduced scoring attacks, not arbitrary kernel
or container escapes. No model resampling was needed for the v0.0.7 regrade.

## Interface binding

`tests/binding.py` describes the reference public interface. A reviewer can supply
`--binding PATH` to `verify.py`; the Harbor entry point uses
`/tests/interface_binding.py` when provided by the curator. The binding translates
public calls and results; it must not implement delivery or rewrite recipient
model input. Do not load a candidate-provided adapter as trusted scoring code.

The [G6 binding review](validation/v3/g6-binding-review.md) and the renamed positive
control demonstrate accepted differences. A new arbitrary interface still needs
reviewed integration; automatic interface discovery is not implemented. Lack of a
binding must not be reported as a feature failure.

## Environment and running

Pi Base: `71dca871bc80b6bc97be37f0ca3189399d651fff`. The CPU Docker environment has
Node 22.23.2, installed lockfile dependencies, frozen model catalogs and Python.
The solver works offline in `/workspace/pi`, with 4 CPUs, 8 GiB RAM and a 36,000-second
allowance. Pi runs from TypeScript source; no solution or verifier is in its image.

```bash
harbor run -p tasks/pi-subagent-live-messaging -a oracle -e docker
harbor run -p tasks/pi-subagent-live-messaging -a nop -e docker
```

The cached runner image is
`ai-infra-bench/pi-subagent-live-messaging:base-71dca871bc80`,
`sha256:95b13c4082432f20c58dda2919767637393dc0cb2374890c1e235ed71a036a87`.
It has not been published to a registry. Existing global provider/catalog type
errors are recorded separately from behavior checks.

## Evidence

- [Behavior design](validation/v3/behavior-design.md)
- [Current model regrade and controls](validation/v9/results.json)
- [Sampling configuration](validation/v6/plan.json)
- [Independent causal trace audit](validation/v3/use-finding-audit.json)
- [Current construction status](validation/construction.json)

Older files in `validation/` describe v0.0.2. Its construction record is preserved
as `construction-before-light-interface.json`; its solver pilot is `solver-pilot.json`.
These historical scores are not scores for v0.0.3.
