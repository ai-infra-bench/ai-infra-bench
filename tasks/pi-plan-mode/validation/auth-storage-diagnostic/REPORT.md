# AuthStorage filesystem diagnostic — fixed trial results

Tmpfs did not improve timestamp discrimination and did not make the original Base test reliable. This diagnostic does not justify moving the verifier to tmpfs as a stabilization measure.

## Frozen design

- Fresh, unpatched Base image: `sha256:a68c346850d3b3ec045dd52aaf751e229e888ca365de99ab06a99fe88eeb0cda`.
- One independent container, network disabled, 4 CPUs, 8 GiB memory, Node 22.19.0.
- Compare `/tmp/authdiag-overlay` on overlayfs with `/dev/shm/authdiag-tmpfs` on tmpfs.
- Probe invokes the image's original `getFileRevision()` from `dist/utils/paths.js` under UID/GID 65534. Each filesystem gets exactly five rounds of 200 same-length overwrites, with filesystem order alternating by round. No delays or retries between the old write, revision read, new write, and revision read.
- Original `test/auth-storage.test.ts` runs exactly five times per filesystem, in alternating order, with `--pool=forks --maxWorkers=4 --retry=0`. The root reporter uses the provided `drop_worker.cjs`; all 10 logs confirm worker UID 65534.
- No task, Oracle, alternative, verifier, Base source, or original test was edited. The diagnostic container is stopped. Results include every trial, including failures.

## Revision probe

The old and new synthetic auth JSON strings are both 44 bytes. Base revision identity is `dev:ino:size:mtimeNs:ctimeNs`, so this sequence needs a timestamp change to distinguish the content change.

| Filesystem | Samples | Identical before/after revisions | Per-round collisions / 200 | Median new-write + stat duration | Positive mtime increments |
| --- | ---: | ---: | --- | ---: | --- |
| overlayfs | 1,000 | 735 (73.5%) | 146, 153, 134, 149, 153 | 241,455 ns | 1,000,014–1,000,015 ns |
| tmpfs | 1,000 | 990 (99.0%) | 197, 197, 198, 199, 199 | 7,146.5 ns | 1,000,014–1,000,015 ns |

Every revision collision also had unchanged mtime and ctime. The nanosecond fields expose approximately 1 ms timestamp steps in this experiment; nanosecond representation does not imply that consecutive writes receive distinct timestamps. Tmpfs writes were faster while the observed timestamp step stayed the same. In this minimal sequence, it increased the chance of an indistinguishable overwrite.

These measurements are from the recorded kernel/filesystem conditions, not a universal claim about all tmpfs systems.

## Original test: all fixed runs

Each invocation collected 26 original cases.

| Round | overlayfs exit / failed cases | tmpfs exit / failed cases |
| --- | --- | --- |
| 1 | 1 / 1 | 0 / 0 |
| 2 | 0 / 0 | 0 / 0 |
| 3 | 0 / 0 | 0 / 0 |
| 4 | 0 / 0 | 0 / 0 |
| 5 | 1 / 1 | 1 / 1 |

All three failures were exactly:

`AuthStorage > keeps a coalesced reload alive while another credential reader is waiting`

At `test/auth-storage.test.ts:137`, the test expected key `new` but received key `old`. All other 25 cases passed in every invocation. The small trial counts cannot establish a failure-rate advantage for either filesystem; both demonstrably retain the failure.

## Interpretation

The unchanged Base caches parsed auth data against the file revision and returns the cached data when the current revision compares equal. Same-length overwrite within one observed timestamp step can therefore retain an old credential. The minimal probe demonstrates the required revision collision independently of an agent patch; the original Base test reproduces the resulting old/new failure under both filesystem choices.

Changing `TMPDIR` to tmpfs would not repair that assumption. Do not use the four successful tmpfs trials to select a passing environment or discard the fifth. Any future environment or upstream-test stabilization needs a separate, predefined validation procedure and must retain these failed results.

## Evidence and reproduction

- `summary.json` retains every trial, failure message and probe aggregate.
- `results/revision-probe.jsonl.gz` contains all 2,000 raw samples and 10 round
  summaries. Only host mount paths were removed from its design metadata.
- The three failing original JUnit reports remain in
  `../auth-storage-base-evidence/`, where the verifier pins their hashes. The
  other seven reports are in `results/`; all ten are unchanged. `results/run-output.json` consolidates their original
  exit codes and console output, including the worker UID confirmation.
- `provenance.txt` records the image, Base commit, resource limits and source
  hashes. `SHA256SUMS` covers the retained evidence files.

The following command runs the same fixed experiment into a new directory;
it does not overwrite the recorded evidence:

```bash
bash tasks/pi-plan-mode/validation/auth-storage-diagnostic/run-diagnostic.sh \
  ./harbor-validation/auth-storage
```

Use `summarize.py <output-directory>` to reproduce the aggregate from a run.
The summary reader supports both the original uncompressed output and the
compressed, consolidated files retained here. Setup-only container metadata
and duplicate evidence copies are excluded from the task.
