# Ray zero-copy logprobs hardening, task version 0.0.2

Retain the task. Version 0.0.2 fixes an E2E boundary that rejected production-
correct executor wiring and adds trusted completion checks for the Ray child
process. The user-facing contract, Oracle and environment image are unchanged.

## Semantic boundary

Cross-Raylet compiled-DAG producer -> RayDistributedExecutor result acquisition
and Future configuration -> retained vLLM ModelRunnerOutput -> subsequent
channel reads -> downstream logprob processing and completion response fields.

The final E2E runs two real Raylets with distinct node IDs and addresses, pins
producer and consumer actors to different Raylets, uses a one-slot compiled-DAG
channel, holds seven outputs concurrently, and checks all token IDs, sampled
tokens, logprob values, ranks, shapes and cumulative-token boundaries. GPU model
execution is not semantic to Ray shared-memory ownership and remains replaced by
deterministic ModelRunnerOutput production.

## Correct executor boundary

The former E2E manually constructed `FutureWrapper`, bypassing the production
`RayDistributedExecutor` method that chooses wrapper arguments and output
transforms. The E2E now adapts the same compiled DAG to
`RayDistributedExecutor._execute_dag(..., non_block=True)` without constructing
the candidate's Future itself.

Two previously rejected candidates are retained as positive controls. One
enables copying through an executor-provided flag; the other supplies an
executor-provided output transform. A third alternative serializes the final
worker output to owned bytes and decodes it in the executor. A worker-local
serializer registration is retained as a negative control because serializer
state is not installed in the driver/consumer process and the channel still
times out. The E2E exercises
both `RayWorkerWrapper.execute_model_ray` and `RayDistributedExecutor`, so all
three complete seven Ray reads with correct data and receive reward 1. Three
slice_request-only candidates remain invalid because the full channel-backed
ModelRunnerOutput is retained before request slicing; representative slice-only
and partial-path controls still time out and receive reward 0.

## Completion integrity

The 13 regression names and one Ray lifecycle name are checked exactly. Reward,
regression JUnit and Ray JUnit files are deleted before each run. The Ray script
runs its lifecycle through pytest, writes JUnit, and only then uses os._exit to
avoid Ray interpreter-teardown instability.

SystemExit(0) and os._exit(0) controls reach the candidate Ray executor import
boundary and terminate the child successfully before pytest. Neither creates
the required Ray JUnit; both receive reward 0 in Docker and Harbor.

## Final validation

All 20 Harbor cases match expected rewards with no Harbor exceptions. Base and
eleven negative controls receive 0. Oracle and seven semantically valid alternatives
receive 1. The final Oracle passes all 13 regressions and the real two-Raylet
worker/executor lifecycle.

Base commit: `82531edbfb6b33e1c8667dea15c8622f011dcef0`.
Image: `sha256:e74823128bb8b25649d0c42c4bd3a18a3fe61d331bf1bd009ba1ff0ada07caed`.
The agent budget is 36000 seconds. The image and dependency locks are unchanged.
The v0.0.1 evidence and original eight model rewards remain under validation
history. This task version is committed locally and has not been pushed.
