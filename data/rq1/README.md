# vLLM RQ1 derived data

This directory contains the Release-aligned per-artifact data used by the RQ1
observational study.

## Files

| File | Records | Contents |
| --- | ---: | --- |
| `vllm_issue_metrics_2026-07-31.jsonl.gz` | 16,990 | One row per canonical Issue with lifecycle and response metrics |
| `vllm_issue_summary_2026-07-31.json` | — | Issue population, monthly flow, backlog, response, closure, and quality aggregates |
| `vllm_pr_semantic_labels_2026-07-31.jsonl.gz` | 32,935 | One row per canonical PR with subsystem and accelerator labels |

## Population

- repository: `vllm-project/vllm`;
- inclusive cutoff: `2026-07-31T23:59:59Z`;
- canonical source: `vllm-github-data-2026-07-31`;
- Issue records: 16,990, including 16,985 GitHub `User`-authored Issues;
- PR records: 32,935, including 32,822 GitHub `User`-authored PRs and 113
  Bot-authored PRs;
- Issue and PR Release coverage: 100%;
- format: UTF-8 JSON Lines compressed with deterministic gzip (`gzip -n -9`).

The PR label file is the canonical aligned sidecar, not the original August 8
labeling run. It excludes 703 PR labels outside the July 31 Release and
supplements the 51 Release PRs absent from the original input.

## Issue metric structure

Each Issue record contains:

- `source_id` and `number`: stable Issue identity;
- `created_at`, `period`, `status_at_cutoff`, and observation-window fields;
- `first_close_at`, `time_to_first_close_days`, close/reopen transitions, and
  lifecycle events;
- `first_human_response_at` and
  `time_to_first_human_response_hours`;
- `first_snapshot_collaborator_response_at` and its elapsed time and state;
- qualifying human and snapshot-collaborator comment counts;
- lifecycle fallback, redundant-event, cutoff override, and API quality flags.

Fields containing `substantive` come from the deterministic
`rq1-substantive-text-v1` rule. They are exploratory sensitivity fields, not
human-annotated substantive responses and not formal headline results.

## PR label structure

Each PR label record contains:

- `source_id` and `number`: stable PR identity;
- `author`: Release actor identity and GitHub actor type;
- `release_created_at`, `release_state_at_cutoff`, and `release_source_layer`:
  canonical Release metadata;
- `release_files_cutoff_stable` and
  `release_representation_may_postdate_cutoff`: evidence-quality flags;
- `label_status`: labeling completion state;
- `classification.subsystems`: multi-label vLLM subsystem classification;
- `classification.subsystem_confidence`: `high`, `medium`, or `low`;
- `classification.accelerator_scope`: `agnostic`, `specific`,
  `cross_backend`, or `unknown`;
- `classification.accelerators`: zero or more of `cpu`, `nvidia_cuda`,
  `amd_rocm`, `intel_xpu`, `ascend_npu`, and `cambricon_mlu`;
- `classification.accelerator_confidence`: `high`, `medium`, or `low`;
- `classification.evidence` and `classification.rationale`: model-cited
  evidence and explanation;
- `label_provenance`: model, prompt, taxonomy, input hash, source cutoff, and
  labeling timestamp.

The full taxonomy and audit rules are documented in
[`../../analysis/rq1/RQ1_ANNOTATION_GUIDE.md`](../../analysis/rq1/RQ1_ANNOTATION_GUIDE.md).

## Read the data

```bash
gzip -cd data/rq1/vllm_issue_metrics_2026-07-31.jsonl.gz | head -n 1
gzip -cd data/rq1/vllm_pr_semantic_labels_2026-07-31.jsonl.gz | head -n 1
```

Python example:

```python
import gzip
import json

path = "data/rq1/vllm_issue_metrics_2026-07-31.jsonl.gz"
with gzip.open(path, "rt", encoding="utf-8") as stream:
    first_record = json.loads(next(stream))
```

## Integrity

| Representation | SHA256 |
| --- | --- |
| Compressed Issue metrics JSONL | `02d0c68412b2bceb48999cb41da2eacb4547ebcc544be6b62957e7ce2b5b28c8` |
| Uncompressed Issue metrics JSONL | `3dd514c19a6359d6a7ecbf881bb9c51cbb05437b331f0d78913b5538a40e233c` |
| Issue summary JSON | `f083b6a20cbaade6be6b8375ba5d2c76408b50ba29713cbe8431db6af1be38f7` |
| Compressed PR label JSONL | `ebe85d9d9bffeb50c7fd1f5d1d24e00edfcfb9754dd090ab8427da9c8d6b1ef5` |
| Uncompressed PR label JSONL | `03cbbef6bdbe01eee33b2023911d707f1dbef74c4e5895cc2b0ab65ee7af8a05` |

## Limitations

- Issue lifecycle and response metrics are public-activity proxies, not
  engineering hours.
- PR semantic labels are model-assisted measurements, not human ground truth.
- A stratified dual-human audit has not yet been completed.
- `unknown` denotes insufficient evidence and is a valid label.
- Subsystem and accelerator labels do not measure engineering hours,
  difficulty, or individual productivity.
- 1,254 human PR representations may contain text edited after the cutoff;
  the risk is retained per record.
- Workload categories and Issue semantic labels are not included. Issue data
  contains objective lifecycle/response metrics, not subsystem or accelerator
  classification.

## License

This derived dataset is licensed under the repository data
[`LICENSE`](../LICENSE) (CC BY 4.0). Underlying GitHub content remains subject
to its original project and contributor terms.
