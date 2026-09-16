# RQ1: vLLM maintenance-workload analysis

This directory contains the reviewed RQ1 analysis for the frozen
[`vllm-github-data-2026-07-31`](https://github.com/ai-infra-bench/ai-infra-bench/releases/tag/vllm-github-data-2026-07-31)
snapshot. RQ1 is an observational study of public GitHub activity and is
separate from the agent benchmark score.

## Documents

| File | Purpose |
| --- | --- |
| [`RQ1_CONCLUSIONS_CN.md`](RQ1_CONCLUSIONS_CN.md) | Shareable Chinese conclusions and headline results |
| [`RQ1_CONCLUSIONS_CN.pdf`](RQ1_CONCLUSIONS_CN.pdf) | PDF export of the conclusions |
| [`../../docs/RQ1_METHODS.md`](../../docs/RQ1_METHODS.md) | Frozen operational definitions and data-quality rules |
| [`RQ1_ANNOTATION_GUIDE.md`](RQ1_ANNOTATION_GUIDE.md) | Per-artifact fields, taxonomies, and human-audit procedure |
| [`ISSUE_FINDINGS.md`](ISSUE_FINDINGS.md) | Detailed canonical Issue findings |
| [`LABEL_FINDINGS.md`](LABEL_FINDINGS.md) | Detailed PR subsystem and accelerator findings |
| [`RELEASE_ALIGNMENT.md`](RELEASE_ALIGNMENT.md) | Canonical snapshot inventory and source alignment |
| [`export_shared_record_table.py`](export_shared_record_table.py) | Full per-Issue/per-PR table exporter |
| [`../../data/rq1/README.md`](../../data/rq1/README.md) | Versioned Release-aligned Issue metrics and PR labels |

Generated snapshots and tables live under ignored `artifacts/`. They are not
committed because they are large and may contain raw collection data. Reviewed
datasets should be distributed as versioned Release assets with checksums.

## Current scope

- Lifecycle, response, Review, reviewer, comment, and available churn fields
  are derived from the canonical Release.
- Subsystem and accelerator labels cover all canonical PRs. They are
  model-assisted and remain provisional pending a stratified dual-human audit.
- Workload categories have not been labeled.
- First substantive response has not been human-annotated. The deterministic
  text field is exploratory only.
- The May 18 collaborator roster is a snapshot roster, not historical
  event-time maintainer membership.
- GitHub activity is a public proxy for maintenance demand, not engineering
  hours or individual productivity.

## Reproduce the canonical outputs

Derive Issue metrics from the Release SQLite:

```bash
uv run aib-rq1 derive-release-issue-metrics \
  --database /path/to/vllm_github_2026-07-31.sqlite \
  --records-output artifacts/rq1/2026-07-31/issue_metrics.jsonl \
  --summary-output artifacts/rq1/2026-07-31/issue_summary.json
```

Map the original and supplemental semantic labels to the Release population:

```bash
uv run aib-rq1 align-release-labels \
  --database /path/to/vllm_github_2026-07-31.sqlite \
  --labels artifacts/rq1/2026-08-08/full_pr_labels.jsonl \
  --labels artifacts/rq1/2026-07-31/supplemental_pr_labels.jsonl \
  --label-source-cutoff 2026-08-08T23:59:59Z \
  --label-source-cutoff 2026-07-31T23:59:59Z \
  --records-output artifacts/rq1/2026-07-31/pr_label_sidecar.jsonl \
  --summary-output artifacts/rq1/2026-07-31/pr_label_summary.json
```

Export the full one-row-per-artifact workbook and compressed CSV:

```bash
uv sync --extra report
uv run --extra report python analysis/rq1/export_shared_record_table.py \
  --database /path/to/vllm_github_2026-07-31.sqlite \
  --issue-metrics artifacts/rq1/2026-07-31/issue_metrics.jsonl \
  --issue-summary artifacts/rq1/2026-07-31/issue_summary.json \
  --pr-labels artifacts/rq1/2026-07-31/pr_label_sidecar.jsonl \
  --output artifacts/rq1/2026-07-31/share/vllm_rq1_per_artifact_metrics_2026-07-31.xlsx \
  --csv-output artifacts/rq1/2026-07-31/share/vllm_rq1_per_artifact_metrics_2026-07-31.csv.gz
```

The canonical SQLite SHA256 is
`2ac86507a95f9b8785e6ce0bbf2745e3fbba67c747e37b54020a7e57ce80f8b5`.

## Model gateway configuration

Model labeling requires `AIB_MODEL_ENDPOINT` to be set to your Azure-compatible
gateway URL and `AIB_MODEL_API_KEYS` to contain its credentials. No endpoint or
credentials are bundled with the repository.
