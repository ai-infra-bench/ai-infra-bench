# Data

This directory contains reviewed datasets used by AI Infra Bench:

- [`vllm_survey_results.jsonl`](vllm_survey_results.jsonl): de-identified
  vLLM maintainer survey recommendations;
- [`rq1/`](rq1/README.md): Release-aligned lifecycle and response metrics for
  all 16,990 canonical vLLM Issues, plus subsystem and accelerator labels for
  all 32,935 canonical vLLM PRs.

## Maintainer survey

This file contains de-identified source recommendations collected through the vLLM maintainer survey. Each JSONL record represents one unique GitHub issue or pull request. Repeated recommendations are merged into `survey.endorsements` rather than duplicated.

The survey focuses on vLLM engineering work. One current record points to FlashInfer because the root cause of a vLLM failure was in an upstream kernel repository.

## Field groups

- `schema_version`: source-record schema version.
- `source_id`: stable identifier derived from repository, object type, and number; never from a mutable title.
- `repo`, `source_type`, `number`, `url`, `title`: canonical source identity.
- `survey`: immutable maintainer evidence. `reason` and `effort_raw` preserve the respondent's wording. Informal effort is not converted to hours without a documented normalization policy.
- `github_snapshot`: refreshable GitHub metadata. `as_of` states when it was observed. Snapshot SHAs are not automatically benchmark base or reference commits.
- `benchmark`: curator assessment that may evolve while a source is reproduced and scoped.

## Curator values

`benchmark.value` estimates whether a source is useful for measuring AI-infrastructure engineering:

- `high`: strong diagnostic, architectural, performance, hardware/runtime, or cross-system signal;
- `medium`: potentially useful, but more evidence or technical depth is needed.

`benchmark.readiness` records the next curation step:

- `needs_reproduction`: create a deterministic reproducer and verifier;
- `needs_solution_mapping`: identify the canonical fixing PR or commit;
- `needs_scoping`: split an umbrella or project-scale source into atomic tasks;
- `needs_review_analysis`: extract review-derived requirements first;
- `hold_open`: no stable reference solution yet.

## Privacy and provenance

- Respondent email addresses and form timestamps are excluded.
- Personal names in free-text responses are replaced with role-neutral placeholders such as `[contributor]`.
- Personal GitHub profile links and links to identity-bearing individual comments are excluded. Repository-level issue and pull-request links remain as technical provenance.
- Invalid test responses and entries without a valid GitHub URL are excluded.
- Maintainer wording stays under `survey`; inferred labels stay under `benchmark`.
- Survey endorsements are source-discovery evidence, not public claims that a benchmark task is valid.

A later materialization stage creates runnable benchmark tasks with a verified base state, reference solution, environment lock, reproducer, tests, grader, and hardware contract. Those fields do not belong in this discovery-level file.

## License

Datasets in this directory are licensed under [Creative Commons Attribution
4.0 International](LICENSE), subject to the provenance qualifications in their
dataset-specific documentation. Software and documentation elsewhere in the
repository use Apache-2.0.
