# MiniMax M3 streaming reasoning integrity hardening, version 0.0.2

Retain the task. The public contract, environment and behavioral verifier remain
unchanged. Version 0.0.2 hardens result integrity and brings the agent budget
into compliance with the project-wide 10-hour policy.

## Semantic boundary

OpenAI Chat Completions request -> real pinned MiniMax tokenizer and chat
template -> OpenAIServingChat -> combined reasoning/tool parser -> streamed SSE
reasoning, content and structured tool calls.

Only model execution is substituted with deterministic decoded text and valid
token IDs. Prompt rendering, request validation, request-local parser state,
reasoning parsing, tool parsing and SSE serialization execute real vLLM code.

## Integrity changes

The regression checker now requires the exact 26 testcase names rather than
only a count of unique cases. The tokenizer and serving E2E scripts each run one
explicit pytest case and produce separate JUnit files. A trusted checker
requires those exact names, zero failures/errors/skips and complete totals.
Reward and all three JUnit files are removed before every verifier run.

The SystemExit(0) control reaches the tokenizer-pipeline import boundary and
exits successfully before pytest runs. The os._exit(0) control reaches the
serving-lifecycle import boundary and also exits successfully. Neither produces
the required JUnit file; both receive reward 0 in Docker and Harbor. This
demonstrates completion integrity rather than relying on nonzero child status.

## Final validation

Eight Docker and eight Harbor cases match their expected rewards. Base and five
negative controls receive 0. Oracle and the independently named/stateful
alternative receive 1. The final Oracle passes all 26 regressions, the pinned
tokenizer pipeline and the real ASGI/OpenAIServingChat lifecycle. Harbor reports
no exceptions.

Base commit: `e368415daa2c4a4141904ec9c85e7a0dcaff6160`.
Image: `sha256:4ad2798441190b1508185ecb3ca79c640d79c396380f43b23d34b5d56a6ce20b`.
The image and dependency locks are unchanged. The prior validation record is
preserved under `validation/history/0.0.1-evidence.json`. Changes remain local
and uncommitted.
