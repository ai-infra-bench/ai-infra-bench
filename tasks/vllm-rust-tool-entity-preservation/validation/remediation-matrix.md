# Approved remediation for task version 0.0.2

| Finding | Change | Actual validation |
| --- | --- | --- |
| The verifier required escaped protocol closing tags to remain encoded, contradicting Base source tests and the instruction to preserve working behavior | Keep ordinary entity spellings verbatim while retaining legacy decoding only for each parser's complete closing delimiters | Oracle and compatible alternative pass 68/68 verifier cases, 60/60 Rust matrix cases, source Rust tests, and real OpenCode E2E |
| Five Rust candidates were false negatives under v0.0.1 | Replay all eight historical attempts on the compatibility verifier | Five Rust candidates receive 1; two Python-only candidates and the no-patch attempt remain 0 |
| The blanket no-decode alternative no longer satisfies the compatibility contract | Reclassify it as an incorrect control and retain a selective, structurally different alternative | Blanket no-decode receives 0; compatible alternative receives 1 in Docker and Harbor |
| Closing-delimiter compatibility was tested only in complete mode | Parameterize the four parser cases across complete and streaming modes | Eight compatibility cases pass for both positive implementations and all five historical Rust candidates |
| Source tests were compiled but not executed | Run the complete `vllm-tool-parser` source test suite before verifier layers | Oracle and compatible alternative pass; blanket no-decode fails the preserved Base assertions |
| Successful child termination could leave required checks incomplete | Add a Rust `process::exit(0)` control at the production parser boundary | Marker proves the control executed; Docker and Harbor both assign reward 0 because required results are incomplete |
| Agent timeout and artifact evidence were stale | Set the agent budget to 36000 seconds, preserve v0.0.1 evidence, and regenerate path-addressable hashes | Repository validation, final Harbor Oracle and strict artifact audit pass |

The user-facing instruction and environment image are unchanged. Historical
raw rewards are not rewritten. Changes remain local and uncommitted.
