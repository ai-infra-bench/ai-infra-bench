# Task review and hardening report

Retain the task under the repository's verifier-only and explicitly selected
coverage policy. The two requested verifier findings are corrected. Independent
review found three additional representation constraints, which were also
corrected and independently rechecked. The final generation-submission guard
also passed independent follow-up (4 tool-choice cases and 1 equivalent none
conversion). No further concrete actionable issue was reported in the completed
independent final review. This does not certify a complete Rust solution or
full SDK compatibility.

## Statement and environment

The workflow remains official Anthropic SDK use against vLLM's Rust frontend,
including preservation of existing Rust APIs. Instruction, Base, cutoff, image,
network/resources and the 36,000-second agent budget are unchanged. The canonical
image is `sha256:535bb97cac5f23043e7874dfde5037c1fee6d76d180d1da2e6e8217ca161d125`,
with Base `e196268bade5291c3fd80906bf9cd8c64851b21b` and cutoff
`2026-09-01T23:59:59Z`. The final image audit passed against that identity.
The task and skill were loaded from isolated benchmark HEAD `497a5b6`; their
exact identity, dirty scope and skill hashes are in the evidence.

The prior choice to retain a broad instruction while scoring a smaller subset
remains explicit. Hosted/search/reference types, thinking request/signature
semantics, errors/authentication and media remain unverified. The absence of a
complete Rust Oracle is permitted by `CONTRIBUTING.md` for `verifier_only`; it is
not disguised as a positive Rust result.

## Semantic boundary and corrections

```text
SDK request -> real Rust HTTP/router and request conversion
-> production Qwen renderer/tokenizer and actual engine-client request
-> limit-bounded deterministic token generation
-> real output conversion and HTTP/SSE -> official SDK result
```

Only model generation is substituted in the Rust target boundary. The producer
now obeys the received max_tokens and reports length when it exhausts that
budget. The existing JSON-constraint matcher, real prompt/token checks, parsers
and transport remain intact. Weights/GPU compute and previously excluded SDK
features are not included by implication.

- Generation limits: six SDK cases cover three limits in stream/nonstream mode,
  checking actual engine parameters, text, usage and termination. Eight native
  OpenAI cases cover two endpoints, both modes, and two nondefault generation
  profiles. The SDK itself no longer directly exposes temperature/top_p/top_k;
  those are existing OpenAI contracts. Both parallel-tool success cases use a
  sufficient 128-token budget for their 66-token script.
- Tool-none fairness: each Messages call must submit one generation; disabling
  tools is checked by public output. No internal parallel flag or mode is
  required for this case. Two native controls preserve
  direct text. A correct partial normalization passes all relevant behavior.
- Response representation fairness: ordered text may span multiple blocks, and
  a stream may contain multiple top-level message updates. Checks preserve
  block start/stop balance, update ordering and final SDK state.
- Named-tool fairness: requiring a call from a singleton allowed tool set is
  accepted as equivalent to explicitly selecting that tool, while the requested
  tool name and arguments remain checked.

The suite is 93 pytest cases: 21 SDK fixture controls, 53 Anthropic server cases
and 19 existing API/backend controls. Ten additional Python CPU checks execute
real dummy weights. The behavior-to-case mapping is in `contract-matrix.md` and
`case-inventory.json`; fixtures are never counted as candidate coverage.

## Measured results

The final immutable Python reference passed 93/93, and the correct tool-none
reference alternative also passed 93/93, both with zero errors/skips. Replacing
max_tokens with 512 is rejected by all six SDK limit cases. The named-tool
normalization passed its scored case. Four equivalent stream encodings passed
the actual scored predicate. These are reference/protocol qualifications, not
complete Rust solutions.

The completed independent reviewer passed 11 changed SDK cases and eight new
boundary challenges: below/equal/above output length and a stop before the
budget, in both response modes. See `independent-review.md` and its evidence.

Final Harbor results (server columns are passed / failed):

| Case | Reward | Server cases | Native controls |
| --- | ---: | ---: | ---: |
| base | 0 | 19 / 53 | 19 / 0 |
| alternative-tool-none-normalization | 0 | 19 / 53 | 19 / 0 |
| byte-tokenization | 0 | 1 / 71 | 1 / 18 |
| count-tokens-only | 0 | 19 / 53 | 19 / 0 |
| ignore-generation-limit | 0 | 15 / 57 | 15 / 4 |
| ignore-json-constraint | 0 | 18 / 54 | 18 / 1 |
| ignore-sampling-options | 0 | 15 / 57 | 15 / 4 |
| json-chat-rendering | 0 | 15 / 57 | 15 / 4 |
| static-json-endpoints | 0 | 19 / 53 | 19 / 0 |

All 11 final Harbor trials completed without framework errors. The
3 Base repetitions have identical failed case names.
Every trial passed 21 SDK fixtures and all ten real CPU controls. Base fails at
the missing Anthropic routes, not compilation, imports or hardware. Native
mutation failures and the correct partial alternative's passing native cases
are checked separately from total reward zero.

The final `record_hardening_results.py` verifies frozen input hashes, prepared
test/instruction identities, JUnit counts and zero skips/errors, native control
outcomes, Python positives/negatives, image identity and independent-review
records before writing `e2e-evidence.json`. The generic Oracle-only artifact
auditor is not used to invent an Oracle result. No complete Rust Oracle,
complete Rust alternative, or Harbor Oracle success is claimed.

The old 77-case evidence is archived under `history/497a5b6/`; the original
115-case audit remains under `history/f4163bc/`. Trial input checksums identify
prepared snapshots before final evidence-only writes. The final static-response
control also fails the tool-none subcase, so removing irrelevant representation
constraints does not permit skipping generation. Validation ran on an uncommitted
snapshot containing only this task's verifier/validation changes. Its executable
hashes identify the validated contents independently of the later commit and PR.
