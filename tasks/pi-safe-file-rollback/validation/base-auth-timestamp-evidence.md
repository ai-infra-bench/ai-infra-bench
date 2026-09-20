# Auth reload timestamp collision

The additional `ignore-conflicts` regression failure is an existing file-revision
cache issue, separate from the rollback defect that this negative control tests.
The original auth test and its production dependencies are unchanged by the
control patch. Three bounded runs of the original test file passed on Base;
the same three runs with the control patch reproduced the exact failure once,
including all three attempts under `--retry 2`.

The mechanism is reproducible on unmodified Base. The original fixture writes
`old` and immediately replaces it with the equal-length value `new`. On the
examined filesystem, both writes can have identical device, inode, size, mtime
and ctime fields. `AuthStorage.readLatestData()` treats that unchanged revision as
a cache hit, returning `old` without acquiring the mocked reload lock. In 200
independent temporary fixtures, 166 produced identical revisions and stale
results; no stale result occurred with a different revision. Changing the new
credential to `new-value` produced distinct revisions and fresh results in all
200 control iterations.

`tests/stable_auth_reload.test.ts` preserves the upstream case's two readers,
first-reader cancellation, second-reader completion and single lock/release
assertions. Its different-length credential makes the intended reload
deterministic without sleeps. It passed three runs on Base and three with the
negative control, using a root Vitest coordinator and UID/GID 65534 workers.

Keep the original case and complete baseline inventory. Any special handling
must match this exact named `old` versus `new` assertion failure and require the
stable counterpart to pass. Missing cases, skipped execution, timeouts and other
failures remain errors. Increasing retries or ignoring the auth case entirely
would not establish the intended behavior.

`base-auth-timestamp-evidence.json` records the image, source and stable-test
digests, observed signature and bounded results. These diagnostic frequencies
are observations from this investigation, not general failure-rate estimates.
