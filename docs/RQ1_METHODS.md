# RQ1: vLLM maintenance-workload methods

## Scope and canonical freeze

RQ1 is an observational study of public vLLM community activity. It is
separate from the agent benchmark score and does not interpret GitHub activity
as engineering hours.

- Repository: `vllm-project/vllm`
- Canonical release: `vllm-github-data-2026-07-31`
- Inclusive event cutoff: 2026-07-31 23:59:59 UTC
- Reporting periods: launch through 2024, calendar year 2025, and 2026 through
  the cutoff
- Primary presentation: monthly time series
- Issue population: all issues created by the cutoff
- PR population: all PRs created by the cutoff, including open and
  closed-unmerged PRs

The release SQLite database is the authoritative census. It contains 16,990
issues, 32,935 PRs, 205,998 issue/PR conversation comments, 131,473 submitted
PR reviews, and 122,491 inline review comments. It combines a Fivetran base
snapshot through 2026-05-18 with a GitHub API delta through 2026-07-31. The
2026-08-08 API collection is retained only as a later supplement and
sensitivity snapshot.

The PR is the semantic classification unit. Commits supply revision and churn
evidence; they are not independently classified. Direct default-branch commits
that cannot be mapped to a PR are audited separately for omitted code work.

## Identity and role semantics

Human and bot classification uses GitHub's actor type. An actor is a bot only
when `user.type == Bot`; names that contain `bot` are not sufficient. Objects
whose actor type is missing or is an organization are reported separately and
are not silently included in the human population.

The release contains a repository-collaborator roster frozen at the May 18
base snapshot: 103 actors with triage or greater access, comprising 70 with
write or greater access and 33 triage-only actors. This is called the
**snapshot collaborator** roster. It is not historical membership and must not
be described as an event-time maintainer roster.

For release-aligned Issue results, a snapshot-collaborator response is a public
comment by an actor in that roster, excluding bots and the Issue author. The
term **maintainer response** is reserved for a future measure with audited
historical role information. API `authorAssociation` fields are retained as
supplementary evidence but do not replace the frozen-roster definition.

## Data layers

The analysis keeps these layers separate:

1. the immutable release SQLite database and its manifest/checksums;
2. canonical cutoff tables for artifacts, comments, reviews, files, commits,
   and lifecycle events;
3. derived metrics with definitions and code versions;
4. model-produced semantic labels with prompt, taxonomy, resolved model,
   input hash, confidence, rationale, and evidence;
5. human audit and adjudication records;
6. monthly aggregates and reporting-window summaries;
7. post-cutoff API supplements, never silently merged into the main snapshot.

For base-layer Issues, close/reopen transitions come from
`issue_closed_history`. For delta-layer Issues they come from
`canonical_maintenance_event`. The two lifecycle sources are selected by
artifact source layer rather than unioned, preventing duplicate transitions.
`canonical_issue.state_at_cutoff` is authoritative at the release cutoff.

## Issue metrics

- **Arrivals:** GitHub `User`-authored issues opened in the month.
- **Closures:** open-to-closed transitions in the month. Repeated
  close/reopen cycles remain in lifecycle data; tables report both transitions
  and unique issues closed.
- **Backlog:** issues open at 23:59:59 UTC on the last day of the month,
  reconstructed from lifecycle events and reconciled to canonical cutoff
  state. Backlog age bands report more than 30, 90, and 180 days open.
- **First human response:** elapsed wall-clock time to the first non-author,
  non-bot GitHub `User` comment.
- **First snapshot-collaborator response:** elapsed wall-clock time to the
  first qualifying comment by an actor in the May 18 collaborator roster.
- **Time to close:** elapsed wall-clock time from creation to the first close.
  Issues without a first close are right-censored at the cutoff.

Administrative actions, reactions, bot messages, author self-replies, and
empty/deleted comments are not responses. Response coverage is reported at
fixed 2-day, 7-day, and 30-day windows. Denominators include only Issue cohorts
with a complete window at the cutoff, and each rate includes a Wilson 95%
confidence interval. Observed-event response quantiles are conditional on an
event and therefore never substitute for fixed-window coverage.

The deterministic `rq1-substantive-text-v1` rule remains in artifacts only as
an exploratory sensitivity field. It is not a headline result. A formal first
substantive-response measure requires stratified human annotation and reported
false-positive/false-negative performance.

Time-to-first-close tables report observed-event quantiles and a Kaplan-Meier
estimate over right-censored Issues. Automated, human, and unknown close actors
are separated.

## Pull-request metrics

- **First review time:** elapsed wall-clock time from PR creation to the first
  submitted, non-bot review by someone other than the author.
- **Time to merge:** elapsed wall-clock time from PR creation to merge. Open and
  closed-unmerged PRs are right-censored.
- **Review submissions:** submitted reviews in states `APPROVED`, `COMMENTED`,
  or `CHANGES_REQUESTED`; dismissed and pending reviews are separate.
- **Requested changes:** submitted `CHANGES_REQUESTED` reviews and whether any
  occurred.
- **Review comments:** line-level review comments, separate from conversation
  comments.
- **Reviewers:** unique non-bot humans submitting a formal review, excluding
  the PR author.
- **Review rounds:** review activity blocks separated by an author revision.
  Commit timestamps are only a proxy for push timing, so missing-timing flags
  accompany the measure.
- **Code churn:** additions, deletions, changed files, and commits observed by
  the cutoff. Churn is a patch-size proxy, not an effort estimate.

The per-artifact sharing table derives PR lifecycle, response, Review,
round-proxy, and available churn fields from the canonical Release tables.
Headline aggregates are reported from those Release-derived records. At the
common July 31 cutoff, the Release contains 51 more PRs, 955 more conversation
comments, and 453 more reviews than the later API snapshot truncated to the
same date, so date truncation alone is not an acceptable migration.

## Monthly people and demand

The implemented Issue denominator is a distinct snapshot collaborator who
posts at least one qualifying non-author Issue comment in the month. Tables
call this an **active Issue snapshot-collaborator responder**. It excludes
collaborators who only review or merge PRs and is therefore narrower than a
study-wide active-maintainer measure.

The PR denominator is a distinct non-bot human who submits at least one
qualifying formal Review in the month. A combined active-maintainer sensitivity
measure may later union qualifying Issue responses, formal Reviews, and merges.
Because the available collaborator roster is a single snapshot, any
roster-restricted measure must still be interpreted as snapshot-roster activity
rather than historical membership.

Every demand ratio reports its numerator, denominator, and an undefined value
when the denominator is zero. The study reports distributions and
concentration, not individual rankings.

## Semantic classification

Workload-type classification is postponed. The current model-assisted scope is
multi-label subsystem and accelerator coverage only. Labels cover all 32,935
canonical Release PRs: 32,884 map from the original August 8 run and 51 were
supplemented from cutoff-stable Release text, with base merge-commit file paths
recovered for five. The labels remain provisional until a stratified human
audit reports per-label precision/recall and agreement. Per-record provenance
distinguishes the August 8 inputs from the July 31 Release supplement.

## Reporting limits

Counts are accompanied by denominators and missingness. Time metrics report
median and tail quantiles with censoring-aware estimates where applicable.
No comment, review, churn, or elapsed-time measure is converted to human
engineering hours without maintainer-survey calibration.
