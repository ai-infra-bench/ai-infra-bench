# Evaluation scope and task domains

The selected sidebar edition currently displays the complete published
leaderboard snapshot globally. The chart has a static **Pass Average** label,
not a metric or set selector. Neither `?set=` nor a previously saved selection
changes the chart, results table, or release counts. Pass@4 is not displayed.
The website JSON is regenerated from the configured archive; raw evaluations
remain unchanged. See `leaderboard-source.json` and the README for data inputs
and the observed-denominator treatment of missing repetition slots.

All resource axes decrease from left to right. The scale is applied to the
ticks, measured points and connecting curves, not just to the printed labels.
Pass Average remains an ordinary increasing percentage axis.

## Task catalogue

Only Work type and Domain are filter dimensions; search remains available.
Ordering is stable alphabetical order. Removed subsystem, recorded-result and
sort parameters are ignored and discarded on the next filter interaction.

Domain describes the kind of AI infrastructure work, not the project:
Inference, Training or Agent harness. Only domains with actual tasks appear.
All current vLLM tasks are classified as Inference via the explicit project
mapping in `app/lib/task-filters.ts`.

New tasks may provide `metadata.domain` as `inference`, `training` or
`agent_harness`. Explicit metadata takes precedence. An unknown project is
not automatically classified as inference; it remains visible under All until
its domain is assigned.

## Future hardware sets

CPU/A100 set selection is deferred. When reintroduced, each set must have its
own validated, independently aggregated snapshot. Never slice a global mean
or standard deviation in the browser or show unmeasured placeholder scores.
