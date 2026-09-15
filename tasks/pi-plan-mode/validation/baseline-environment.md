# Baseline environment verification and one fingerprinted failure

The original baseline outcome hash remains `fa3518ccc5ebb3c7c4c132869c26d13036d00bca4758762b257410559f7ccf94` for 2,154 cases after projecting out only the intentionally replaced old plan-extension file. The initial validation added no failure allowance. Subsequent unmodified Base reproduction established one additional conditional failure, described below; no testcase is removed or permitted to skip.

## Initial fresh Base reproduction

A new container was created from image `sha256:a68c346850d3b3ec045dd52aaf751e229e888ca365de99ab06a99fe88eeb0cda`, with 4 CPU, 8 GiB memory and no network. No Oracle patch was applied. Git HEAD was `d981de1229ef899957bbe968bc8dcda02a21f477`, and the initial working tree was clean. The root Vitest reporter used the trusted preload, and worker logs report UID 65534. Every worker received a fresh writable HOME. The package root uses sticky permissions for the unchanged SettingsManager scratch-directory tests.

Relevant SHA-256 values match the frozen Base manifest:

| File | SHA-256 |
| --- | --- |
| `test/auth-storage.test.ts` | `513f35d1adec13ba026a7e73b9d8fd2b98f416d102c6c061f976a3d5e468b2fe` |
| `src/core/auth-storage.ts` | `32d36165760959766807b8797042e69b65a65c7aad7d1b79a2621c41fe29b48d` |
| `src/utils/paths.ts` | `a687cdb54b82216673fea5be1210c48e64ffa8398d64cfabf2bd7dba5c9d4210` |

Five independent executions of the original auth-storage test file used `vitest run --pool=forks --retry=2 --maxWorkers=4` between 2026-09-15 04:23:56 and 04:24:03 UTC. All five reports contain all 26 cases and zero failures/errors. A subsequent complete original-suite invocation with the same flags contains 2,154 cases, zero failures/errors and 50 skips. The three permission-sensitive failures recorded in the original root baseline improve to passing under UID 65534, which the unchanged comparison policy permits.

The original JUnit reports, source provenance and run records are included in
[`base-environment-evidence/`](base-environment-evidence/). Console output is
consolidated in `run-output.json`; container IDs and setup-only scripts are not
part of the task. These preliminary runs are distinct from the fixed experiment
below.

## Initial observation and decision

Two complete runs in the earlier, reused Oracle debugging container reported the exact original case `test/auth-storage.test.ts::AuthStorage > keeps a coalesced reload alive while another credential reader is waiting` receiving the old key instead of the new key. The unchanged file passed in isolation. A standalone same-length overwrite probe observed identical nanosecond mtime/ctime for 65 of 100 consecutive overwrite pairs in the fresh Base container (73 of 100 in the earlier debug container). These timestamps participate in the upstream cache revision, making a timing explanation plausible; the probe does not establish the cause of the failed assertion.

The older debug XML files were overwritten by subsequent debugging runs; their failure observations survive in the contemporaneous tool outputs, not as retained raw XML. The fresh Base reports and provenance described above are retained in full.

Crucially, the fresh Base tests did not reproduce that assertion. Therefore it was **not** accepted as an environmental exception, and the initial P2P checker rejected any originally passing case that failed, skipped, or disappeared. The first complete Harbor matrix used that policy. The 18 contract cases and four lifecycle cases have passed in the privilege-separated Oracle debug run; that is separate evidence from a complete successful Harbor trial.

## Subsequent original-test reproduction and final policy

The first complete Harbor matrix (`matrix-acceptance-20260915`) preserved that
strict policy. Both correct implementations passed all 18 contract and four
lifecycle cases, but failed the exact AuthStorage assertion; both received 0.
Base and all eight negative controls completed their original regressions.
Those results remain unaccepted and retained in `initial-matrix-evidence.json`,
with hashes and locations of the raw XML, logs and Harbor results.

An independent fixed experiment then ran the **unchanged original**
`auth-storage.test.ts` on the untouched Base in a fresh container, at UID 65534,
4 CPUs and 8 GiB, with retries disabled. Five overlay filesystem executions
produced two failures of this assertion; five tmpfs executions produced one.
Every other case in the file passed. The failure was always the same
`AssertionError`, old versus new API-key data, at
`test/auth-storage.test.ts:137:22`. All original JUnit reports, a portable reproduction script, source hashes
and provenance are in [`auth-storage-diagnostic/`](auth-storage-diagnostic/).
A separate Base API trace and timestamp probe support the mechanism: equal-size
writes can share the same file revision in this kernel, leaving the cached old
value while disk contains the new value. Neither a trace alone nor a timing
hypothesis is used as a substitute for the original JUnit failures.

Tmpfs does not eliminate the problem, so it was not adopted as a supposed fix.
The final comparator retains the original baseline hash and all 2,154 expected
cases. It conditionally records only this **exact original Base failure** when
its testcase identity matches and every failure element (one to three under
the fixed two-retry policy) has the exact pinned error type, complete old/new
message and source location. Mixed or additional failures do not qualify. It does not permit
missing cases, skips, errors or different assertions, even in the same case.
The raw JUnit and `observed_known_base_failures` in the scoring summary continue
to expose it. Source integrity independently keeps AuthStorage and its original
test unchanged. This separates a proven unrelated baseline failure from the
Plan Mode modification without asking solvers to edit code outside scope.

After freezing this policy, all 11 validation cases were rerun through Harbor.
`e2e-evidence.json` identifies that final matrix; the prior failed matrix is not
retroactively relabeled successful. The three permission-sensitive image
baseline failures and the 50 original skips retain their original rules.
