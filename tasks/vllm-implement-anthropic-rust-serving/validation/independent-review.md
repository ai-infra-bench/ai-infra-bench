# Independent verifier review

Retain the task. The completed independent final review found no further
concrete actionable issue in the pending verifier changes. This conclusion is
limited to the selected contract and does not certify a complete Rust solution
or full Anthropic SDK coverage.

The review used the isolated worktree at benchmark HEAD
`497a5b6e0c0c3c8a538ee1f09e25aac4967d5b1c` with the pending hardening changes,
and that revision's task-review skill/rubric. The reviewer did not edit task
files. Its reference container was independent, network-disabled and limited to
4 CPU/16 GiB; it was removed after execution.

The first independent review produced three concrete local fairness examples:

| Finding | Observed before correction | Correction |
| --- | --- | --- |
| Multiple message_delta events | Strict SDK accepts an intermediate usage update and a final update with the same final Message; old predicate rejected the second update. | Require message updates after completed blocks and before message_stop, checking final state rather than requiring one update. |
| Multiple text blocks | Strict SDK accepts the same ordered text in two blocks; old predicate required one block. | Aggregate text in order and check balanced block starts/stops. Pure-text and mixed text/tool checks no longer prescribe text segmentation. |
| Named tool normalization | A required call from a singleton allowed tool set returns the requested tool, but old predicate required the function enum. | Check the effective single-tool restriction, accepting either representation and retaining tool name/argument checks. |

The first reviewer's final response was interrupted twice by platform content
screening. Its already-written local JSON results and source probes were retained;
the parent inspected and reproduced the findings. A replacement independent
reviewer then completed a fresh functional review of the corrected verifier.

The final independent reviewer executed **11/11** changed SDK cases and **8/8**
new boundary challenges, with no errors or skips. The new inputs cover a token
limit smaller than, exactly equal to, and larger than the scripted output, plus
a stop string before the token limit, each in streaming and non-streaming mode.
It also reviewed the native OpenAI parameter checks and acceptance of equivalent
tool/response representations. No additional blocker was reported.

Raw artifacts are retained at:

- `/tmp/anthropic-independent-review-497a5b6/`: the first review's original
  protocol/real-reference examples and before-correction observations.
- `/tmp/anthropic-final-independent-review-497a5b6/targeted.xml`: final 11-case JUnit.
- `/tmp/anthropic-final-independent-review-497a5b6/challenge.py` and
  `challenge-results.json`: the independently constructed eight cases.

Exact hashes and the boundary results are stored in
`independent-review-evidence.json`. The parent additionally ran the task's
`qualify_response_variants.py` against four combinations of text-block splitting
and intermediate usage deltas; all four passed the actual scored predicate.
The reference-only named-tool normalization passed its actual scored case.
These protocol/partial alternatives are not complete Rust solutions. The full
parent Rust/Harbor and Python matrices are recorded separately in `e2e-evidence.json`.

## Final generation-submission follow-up

The final native control matrix additionally showed that static-json-endpoints
could pass the tool-none subcase after irrelevant representation checks were
removed. The parent added a before/after observation requiring one actual engine
submission for each Messages request. It does not constrain none's internal mode
or parallel flag. The independent final reviewer accepted this observation and
ran four tool-choice cases (4/4) plus the none normalization (1/1), confirming
parallel_tool_calls=false and exactly one new engine capture. No new issue was
reported. The SDK test file hash in that review was
`2378aad27c0c744ebaccbd8b02c0aa11b6f06da01168f4ccc35d851d37a9b8ee`.

The pre-guard Harbor run was stopped and archived outside the task. Final
Harbor and full Python matrices were restarted after the new snapshot was frozen;
pre-guard results are not used as final executable evidence. Follow-up raw results
are under `/tmp/anthropic-none-generation-followup-497a5b6/` and their exact hashes
and capture summary are included in `independent-review-evidence.json`.
