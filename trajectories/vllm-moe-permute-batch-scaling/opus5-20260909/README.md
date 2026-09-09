Opus 5 evaluation: vllm-moe-permute-batch-scaling

Adds a native MoE permutation task covering output correctness and batch-size latency scaling with publicly specified workload parameters.

Original reward: **1**. Model identifier: `claude-opus-5`; Claude Code Tap 2.1.238. This is an archived 2026-09-09 solver run, not a newly generated trajectory.

The archived solver passed native build/staging, correctness and performance. The 4096-token latency was 108.1958 microseconds (limit 250), and the 4096/512 latency ratio was 3.02924 (limit 3.5).

Job: `da8fa991-15bd-4dbd-8b59-fa63261b439e`. Trial: `b6157859-b182-4f53-930b-b47279f088ef`. Harbor errored trials: 0.

Real rebuilt CUDA MoE permutation extension and measured timing on one A100. No unmeasured +/-5% timing claim is made.

- [trajectory.json](trajectory.json): browsable Harbor ATIF trajectory.
- [trace-bundle.tar.gz](trace-bundle.tar.gz): ATIF, Claude Code stream JSON, API JSONL, sanitized Tap SQLite, original job/trial results and configuration, and verifier logs.
- [manifest.json](manifest.json): per-file original/export SHA-256, bundle hash, exact task-file hashes, redaction scope and known limitations.
- [publication-checks.json](publication-checks.json): packaging checks and preparation equivalence to the previously reviewed CI helper.

Extract the archive with `tar -xzf trace-bundle.tar.gz -C <empty-directory>`. The exported database is `agent/traces.sqlite3`; `PRAGMA integrity_check` must return `ok`. Verify the bundle SHA-256 against manifest.json before use.

Publication copies remove authentication header/key values and recognizable credentials. Original local artifacts and rewards are unchanged. The SQLite database is rebuilt into a fresh file; table/record counts are preserved and blob bodies are unchanged. Candidate repository trees/native binaries and unrelated session state are omitted; the commands and edits remain in the trajectories.

Task files match the reviewed version byte-for-byte. The task image is retained on the evaluation host; the 10–12 GB image itself is not uploaded in this PR and historical absolute log paths remain provenance, not public download URLs. The checked-in environment recipe/locks and this portable solver archive are available to reviewers. Repository CI must build or obtain the image on a matching runner. No new solver rerun or external reviewer approval is claimed.

Task: [tasks/vllm-moe-permute-batch-scaling](../../../tasks/vllm-moe-permute-batch-scaling). Upstream context: https://github.com/vllm-project/vllm/pull/32892. Base: `dc917cceb877dfd13f98c538c4c96158047d98bd`.

Formatting note: the frozen Oracle solution/solve.sh has one blank line at EOF. Git diff --check and the staged-scope audit report that style warning. It is preserved to keep the published task byte-identical to the evaluated artifact; executable checks and reward thresholds have not been disabled or changed.
