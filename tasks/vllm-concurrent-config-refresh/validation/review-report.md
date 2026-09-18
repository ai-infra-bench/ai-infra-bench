# Concurrent config refresh hardening, task version 0.0.2

Retain the task. The v0.0.2 statement now covers the verifier's existing
transient incomplete-read behavior, and the final Base, Oracle, alternative and
negative controls all behave as expected.

## Contract and semantic boundary

The final user requirement is that an otherwise valid configuration recover
from brief missing or incomplete reads while multiple API workers start, but a
persistently missing, malformed or unsupported configuration must still fail.
The statement does not prescribe exception classes, retry counts, helper names
or a repair location.

Concurrent API workers -> real configuration-file reads with a brief filesystem
visibility/read anomaly -> bounded configuration parsing -> all four workers
become healthy and a completion request succeeds.

The four API processes, Transformers configuration parsing, vLLM startup, model
weights, health endpoint and completion endpoint run for real. `LD_PRELOAD`
substitutes for a concurrent cache writer by producing one ENOENT and one
short-lived incomplete read at the real `config.json` system-call boundary. It
preserves the error type, worker isolation, one-shot lifetime and subsequent
successful read that determine the required recovery.

## Verifier and fairness

The four unit regressions require a valid local configuration to load and
persistently missing, malformed and unsupported configurations to fail. The E2E
starts four API servers, verifies both injected faults occurred exactly once,
waits for health, and sends a real completion request. Three separate invalid
startup processes must terminate unsuccessfully within 15 seconds.

The Oracle retries the complete parser through the existing retry helper. The
correct alternative retries individual Transformers parser calls with a
different attempt count and repair location. Both pass full Docker and Harbor
grading and a separate transient-partial-read challenge. FileNotFound-only,
visible-path-only and unbounded-retry controls receive zero. Candidate-triggered
SystemExit(0) and os._exit(0) both reach the configuration module, leave the
required JUnit inventory incomplete, and receive zero.

## Historical eight model trials

The eight gpt-5.6-sol/high trials used the same v0.0.1 task checksum and produced
eight different patches. All passed the four regressions and three persistent
invalid-startup cases. Every patch deliberately retried only FileNotFoundError,
successfully recovered the injected ENOENT, and then failed when the verifier's
previously undisclosed incomplete read became an OSError. These rewards are
retained as historical artifacts but are not valid measurements for v0.0.2.

## Final validation

Eight Harbor cases match their expected rewards: Base and five negative
controls receive zero; Oracle and the parser-local alternative receive one.
There are no Harbor exceptions. The final Oracle passes 4/4 regressions, the
four-process startup/health/completion probe, and all three persistent invalid
startup cases.

Base commit: `910cc8543a6907c9cc87c417f8f2420969278bf5`.
Image: `sha256:55a976d181ef27bfd311c2aa7d6ad6d9e66b483a6eaf34dd51118722be4ef8c0`.
The agent budget is 36000 seconds. The image, dependency locks, CPU and memory
settings are unchanged. The task is uncommitted and has not been pushed.
