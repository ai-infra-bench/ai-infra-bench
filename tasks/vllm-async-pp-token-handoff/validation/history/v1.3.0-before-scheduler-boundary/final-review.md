# Final review

Version 1.3.0 can be retained. The statement, environment and verification gates pass. The full grading entrypoint gives Base 0, Oracle 1, both correct alternatives 1, and all eleven incorrect controls 0: 15/15 expected results. The final Harbor Oracle gives reward 1 with zero errored trials using the documented two-GPU Docker adapter.

The serial-executor counterexample received reward 1 before the final overlap check and reward 0 after it. The test now holds worker progress and requires another submission for the same request before earlier work is released. Oracle and P2P alternatives retain their exact token outputs. Fixed-helper, fixed-buffer and PP wire-protocol assumptions were removed, and the task statement remains the user-approved English version.

Correct full-entrypoint runs took 11.7–12.3 minutes in this shared two-A100 validation, with a mean of 12.0 minutes. These are observed evaluation costs, not candidate performance requirements.

See semantic-boundary.md for both directions of the requirement map, local-regressions.json for every result, and e2e-evidence.json for executable hashes, environment identity, stability and Harbor provenance. Raw evidence is archived under evidence/. Coverage is representative and worker-side Python instrumentation is not comprehensive protection against arbitrary candidate tampering.

All changes remain uncommitted on codex/async-pp-behavior-hardening in /tmp/ai-infra-pr75-review. No commit or push was performed.
