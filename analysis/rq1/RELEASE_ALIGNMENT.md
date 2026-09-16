# RQ1 Release alignment status

Canonical source: [`vllm-github-data-2026-07-31`](https://github.com/ai-infra-bench/ai-infra-bench/releases/tag/vllm-github-data-2026-07-31)

- Inclusive cutoff: `2026-07-31T23:59:59Z`
- Base snapshot cutoff: `2026-05-18T20:02:21Z`
- Compressed SHA256:
  `a15e30ab5d187a46b46a4fc493b157fe00d13d3135d87ab94b990e2df04383e0`
- SQLite SHA256:
  `2ac86507a95f9b8785e6ce0bbf2745e3fbba67c747e37b54020a7e57ce80f8b5`

## Canonical inventory

| Object | Rows |
|---|---:|
| Issues | 16,990 |
| PRs | 32,935 |
| Issue/PR conversation comments | 205,998 |
| PR reviews | 131,473 |
| Inline review comments | 122,491 |

The collaborator table is the May 18 snapshot roster: 103 triage-or-greater
collaborators, including 70 write-or-greater and 33 triage-only actors. It is
not a historical role table.

## Why the data layer changed

At the common July 31 cutoff, the release contains 44 more Issues, 51 more PRs,
955 more conversation comments, and 453 more reviews than the August 8 API
snapshot truncated to that date. These are recovered historical objects, not
post-cutoff activity. Release canonical tables must therefore be the primary
layer.

## Alignment matrix

| Analysis component | Current primary data | Status |
|---|---|---|
| Issue arrivals, closures, backlog, response, close time | Release SQLite | Aligned |
| PR lifecycle and time to merge | Release per-record export | Aligned |
| PR response and first review | Release per-record export | Aligned |
| PR requested changes, reviewers, and comments | Release per-record export | Aligned |
| PR review rounds and churn | Release per-record export | Available with documented proxy and missingness limits |
| Subsystem and accelerator labels | Release PR sidecar | 100% labeled; audit required |
| August 8 Issue/API metrics | API supplement | Retained for sensitivity only |

The Issue adapter chooses the lifecycle source by artifact layer: base Issues
use `issue_closed_history`, while delta Issues use
`canonical_maintenance_event`. It does not union both sources. Canonical cutoff
state is authoritative.

Formal substantive-response conclusions remain blocked on human annotation.
The deterministic text rule in generated artifacts is exploratory only.
