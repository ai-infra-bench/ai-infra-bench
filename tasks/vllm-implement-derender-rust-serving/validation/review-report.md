# Long-state and empty-delta qualification

The two functional P1 findings from the independent review of `c2d48fa663f8dad4555c560d1a1de23e6a15ddab`
are repaired. This report records the author's ordinary functional qualification;
the user-requested independent review follows publication of the new commit.

The instruction, CPU environment and semantic boundary are unchanged: real HTTP
generation input -> native Rust routing/tokenizer/parser/state transition ->
client-visible output and state consumed by an independent instance. Model
forward passes remain outside this token-in/token-out boundary.

The Oracle no longer assumes deferred text fits in 1024 window entries. It keeps
structural state checks and permits the decoder's own valid pending state to
continue. Streaming token IDs accept null, omission and an empty array as empty
deltas. Non-streaming nonempty-token validation remains intact. Tests grade
output and lifecycle, with opaque state and no fixed emission schedule.

| Final functional version | HTTP passed / failed / errors | Reward |
| --- | ---: | ---: |
| alternative-native-decoder-replay | 87 / 0 / 0 | 1 |
| base | 9 / 78 / 0 | 0 |
| discard-client-state | 48 / 39 / 0 | 0 |
| discard-logprobs | 84 / 3 / 0 | 0 |
| ignore-prompt-usage | 81 / 6 / 0 | 0 |
| omit-terminal-flush | 61 / 26 / 0 | 0 |
| oracle | 87 / 0 / 0 | 1 |
| plain-text-only | 79 / 8 / 0 | 0 |
| reject-long-returned-state | 79 / 8 / 0 | 0 |
| reject-null-stream-delta | 83 / 4 / 0 | 0 |

All ten versions compile and pass 673 Rust server/chat regressions. Oracle and
the native-replay alternative pass all 87 HTTP cases. The two new controls
separately restore the invalid window cap or reject null deltas and are rejected.
Fresh Harbor Oracle and alternative trials each score 1 with zero framework
errors. Both retained positive binaries pass two more complete HTTP rounds and
six independent growing-state/empty-event challenges each.

The original task/CPU-environment assessment remains applicable to unchanged
artifacts. Native execution isolation is unchanged and has only its previously
recorded dynamic evidence; no new security-completeness review or forwarding
probe is claimed after the prior platform screening interruption. The unchanged
Python-forwarding control stays in the repository CI manifest, but is not part
of this round's ten measured functional versions.

Exact hashes, run identities and measured results are in `e2e-evidence.json` and
`run-results.json`. The 67-case records at c2d48fa remain historical. This task
continues to qualify the supplied Qwen tokenizer and supported plain chunk
modes, without claims about streaming tools/reasoning/logprobs, GPU behavior,
model quality or throughput.
