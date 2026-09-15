# Author validation results

Final matrix: `matrix-final-verified-20260915`, Harbor 0.23.0, retained image
`sha256:a68c346850d3b3ec045dd52aaf751e229e888ca365de99ab06a99fe88eeb0cda`.
All 11 jobs completed one trial with zero errored trials; every expected reward matched.

| Case | Reward | Required behavior failures | Known original Base assertion observed |
| --- | ---: | --- | --- |
| `base` | 0 | C01, C02, C03, C04, C05, C06, C07, C08, C09, C10, C11, C12, C13, C14, C15, C16, C17, L01, L02, L03, L04 | No |
| `oracle` | 1 | None (18 contract + 4 lifecycle passed) | No |
| `alternative-event-journal` | 1 | None (18 contract + 4 lifecycle passed) | No |
| `accept-stale-revision` | 0 | C06, C15 | No |
| `accept-extension-control` | 0 | C07 | No |
| `replay-duplicate-approval` | 0 | C10 | Yes, exact pinned signature |
| `allow-custom-planning-tools` | 0 | C02, C09, L01 | No |
| `replay-approved-resume` | 0 | L02 | No |
| `resume-original-toolset` | 0 | L01 | No |
| `drop-approved-request-context` | 0 | C10 | No |
| `early-exit-zero` | 0 | C01, C02, C03, C04, C05, C06, C07, C08, C09, C10, C11, C12, C13, C14, C15, C16, C17, L01, L02, L03, L04 | Yes, exact pinned signature |

Every run retained the complete 2,154-case regression inventory with no missing
or extra cases and no unaccepted regressions. The two correct implementations
had zero regression failures and retained the 50 original skips; neither needed
the conditional AuthStorage allowance in this final run. The repeated-approval
and early-exit controls did encounter that exact known Base assertion, which
remained visible in their reports; both still failed the intended behavior.

The early-exit control is rejected in two real paths: Vitest intercepts
`process.exit(0)` in contract workers; the independent lifecycle child actually
exits zero but emits no required state payload. A zero process exit does not
yield a successful task result.

The earlier strict matrix is retained unchanged in `initial-matrix-evidence.json`.
The Base reproduction and narrowly scoped regression policy are documented in
`baseline-environment.md` and `auth-storage-diagnostic/`. Final result/JUnit/log
hashes, prepared-verifier snapshot checks, and task artifact hashes
are in `e2e-evidence.json`.

Additional author checks: the final image as the actual pi-agent user passed
`npm run check` and 43 Oracle extension/utils tests. The independent event-journal
implementation separately passed `npm run check` and 42 own/utils tests.
The final agent-user environment passed 60 existing path/settings smoke tests.
The regression comparator/completeness checks passed six self-tests. The final
strict artifact/image audit reported zero errors and zero warnings, including
all ten patch applicability checks against their declared Base or Oracle state.


These are author construction and quality checks, not real coding-agent rollouts.
No model success rate, task difficulty or contamination-free status is claimed.
The image has not been published.
