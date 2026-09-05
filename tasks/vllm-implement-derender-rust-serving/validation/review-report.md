# Post-review task qualification

Task retained; the two reproduced P1 findings in the independent review of
`2e654d4eb6c5ea68f936acc3bfe468949251da86` are repaired. This is the author's
hardening qualification, not a claim that another independent reviewer has
approved the new revision.

Gate 1 passes: the user's frozen native Rust derender query and supported
plain-text chunk protocol remain unchanged. Gate 2 passes: the exact canonical
CPU image, source, offline dependencies and model metadata are retained; the
Python reference remains available during development. The reviewed workflow is
HTTP token/context input -> real Rust routing/tokenizer/parsers/state update ->
client-visible response and continuation on an independent process.

Gate 3 now includes an execution boundary for the explicit no-Python-forwarding
constraint and 18 terminal/continuation cases. Candidate serving runs in a
per-process native filesystem with reduced privileges and blocked outbound
connections; Python clients remain outside. Real tokenization, parsing and
HTTP still run. The bounded-window Oracle and full-history/native-decoder
alternative both flush pending text at termination. Assertions preserve
incomplete UTF-8 during continuation without prescribing private state or the
exact timing of safe prefix emission. Requests after termination are not graded.

| Final version | HTTP passed / failed / errors | Reward |
| --- | ---: | ---: |
| alternative-native-decoder-replay | 67 / 0 / 0 | 1 |
| base | 9 / 58 / 0 | 0 |
| discard-client-state | 48 / 19 / 0 | 0 |
| discard-logprobs | 64 / 3 / 0 | 0 |
| ignore-prompt-usage | 61 / 6 / 0 | 0 |
| omit-terminal-flush | 51 / 16 / 0 | 0 |
| oracle | 67 / 0 / 0 | 1 |
| plain-text-only | 59 / 8 / 0 | 0 |
| python-forwarding | 0 / 2 / 65 | 0 |

All nine versions compile and pass 673 existing server/chat Rust tests. Positive
versions have no errors or skips. Forwarding reaches the candidate's actual
Rust entry point and fails because Python is absent from its runtime; its setup
errors are the intended rejection. The original review's Python-forwarding
Harbor reward 1 becomes 0 in a fresh final Harbor trial. Final Oracle and
alternative Harbor trials both return 1, all with zero framework errors.

Two further HTTP rounds for each retained positive native binary pass. An
independent 12-case mixed-marker/replacement partition challenge passes under
both algorithms. The native-boundary probe confirms source/Python/tests/proc
are absent, model metadata remains readable and immutable, privileges are
reduced, and even a live same-container listener cannot be reached. Exact
hashes, trial identities, test results and reproduction artifacts are recorded
in `e2e-evidence.json` and `run-results.json`.

The original 49-case and five-round records remain historical at the parent
revision. Pre-freeze runs, including tests later relaxed for fairness, are
retained in the external work directory and are excluded from final results.
The verifier uses one supplied Qwen tokenizer and Hermes/Qwen3 parsers. It does
not claim streaming tools/reasoning/logprobs, all-model coverage, GPU inference,
model quality or throughput. No new independent subagent review was run during
this hardening.
