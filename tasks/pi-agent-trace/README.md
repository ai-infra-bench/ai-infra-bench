# Pi agent trace: review and validation

## Reviewed replay cases

The CI catalog in `validation/ci-cases.json` binds every case to an explicit
reviewed child API adapter and frozen candidate file hashes. Missing or mismatched integration is
unscored; it must not be reported as a candidate reward of zero.

The following expectations come from actual v4 Harbor replays with unchanged
input hashes. These checks qualify the named patches, not every implementation
that uses the same interface.

| Case | Expected reward | Current finding |
|---|---:|---|
| `alt-opus-cooperative` | 1 | Passed the current contract with its independently documented child-context event and payload. |
| `alt-grok-run5` | 0 | Concurrent child inherits the wrong tool parent; write-failure reporting repeats after reload. |
| `alt-grok-run8-fixed` | 0 | Concurrent child inherits the wrong tool parent; write-failure reporting repeats after reload. |
| `alt-opus-run1` | 0 | Concurrent child inherits the wrong tool parent. |

The three historical submissions remain byte-for-byte unchanged. Their earlier
results belong to the earlier verifier; they are now regression diagnostics,
not passing alternatives. Per-case `validation/tools/reviewed-bindings/*.review.json` files
retain the reviewed README, patch identity, observed failing contract names and
verifier hashes. The cooperative positive uses
`agent-trace:request-child-context` (`callId`, `baseEnv`, `accept`), distinct from
the Oracle API; CI does not require the Oracle helper or event name.

Run a named case from the repository root through the generic CI entry point:

```bash
python3 .github/scripts/task_ci.py run-reviewed-case \
  --task pi-agent-trace --case alt-opus-cooperative \
  --image sha256:<immutable-local-image-id> --output <new-output-directory>
```

The runner materializes the candidate, verifies its binding identity and runs
one Harbor attempt. It checks the collected reward against the case expectation.
Use an existing immutable local image ID and a fresh output directory.

## Reviewed child-process integration

The statement intentionally leaves the child-context API name and representation to
the implementation. The verifier therefore requires a curator-owned adapter for each
frozen submission. It must not infer a private helper by scanning candidate code.

1. Collect the complete final submission (including new/ignored files) before verifier
   injection. Read its README and the stated public API. Record the snapshot hashes.
2. Write `child-binding.mjs` outside the candidate checkout. Export
   `async function childEnvironment({pi, toolCallId, env, context, extensionPath})`.
   Map these inputs to the documented public API and return the environment that API
   returns. `pi` and `context` are public ExtensionAPI/tool execution context;
   `extensionPath` identifies the loaded entrypoint if the documented API exports a
   helper. The adapter may not construct trace IDs, read private state, fix the
   candidate, inspect expected answers, or write traces.
3. Freeze `child-binding.json`:
   ```json
   {"schema_version":"pi-agent-trace-binding.v1","kind":"documented",
    "adapter_sha256":"<sha256>",
    "candidate_files":{"packages/coding-agent/examples/extensions/agent-trace/index.ts":"<sha256>",
                       "packages/coding-agent/examples/extensions/agent-trace/README.md":"<sha256>"},
    "readme_evidence":"<public API section and exact cited use>"}
   ```
   Include every extension implementation file used by the API. No default Oracle
   adapter is selected automatically. Base or a control missing the feature needs an
   explicitly reviewed `base` or `incomplete-control` binding; null hashes identify
   absent files, and `readme_evidence` explains why ordinary env passthrough is valid
   for that diagnostic. A supported transparent implementation can use passthrough
   only when its documented interface justifies it.
4. Mount/copy both files root-owned into `/tests/` after collection, before verification.
   Missing/mismatched binding writes `integration-needed.json` and exits 2 without a
   reward. This is unfinished curator integration, never a model score of zero.
5. Archive adapter, manifest and final candidate identity with the verifier results.
   Review bindings independently from implementation correctness. Record any invalid
   candidate API separately; do not silently replace a missing API with Oracle wiring.

The child fixture supplies its actual toolCallId, obtains its environment while a
second tool is running, and spawns a real Pi child. It observes trace/session files;
no Oracle-selected environment key, private function, or internal state is asserted.
The child performs manual compaction so both run and compaction root parentage is
checked. The parent environment is compared before and after tools finish.

Run the existing `control-process-exit-zero-after-registration`,
`control-forged-junit`, and `control-verifier-runner-escape` through actual Harbor.
These controls must reach the intended boundary; an earlier binding/setup error is
not evidence of scoring integrity. Candidate JUnit remains same-process evidence;
root ownership of the runner alone does not prove report-forgery resistance.

## Environment build

`environment/Dockerfile` is the full public build recipe. The optional incremental
recipe reapplies the same ownership, baseline and generated-file inventory steps
to an existing pinned Pi image; its parent is an explicit build argument:

```bash
docker build --network none \
  --build-arg PI_BASE_IMAGE=<existing-immutable-pi-image-id> \
  -f tasks/pi-agent-trace/environment/Dockerfile.incremental \
  tasks/pi-agent-trace/environment
```

The parent identity used for the recorded image is retained in
`environment/image-manifest.json`. `baseline_check.py` matches the baseline checker
embedded in the full recipe. Incremental builds do not download source or dependencies.

## Qualification

`validation/tools/qualification.json` records the exact tested source hashes,
image identity and fresh replay results. The 39 profiles pass input/hash checks;
69 repository CI unit tests pass. Fresh final-v10 Harbor replays pass for the Oracle and the independent
cooperative alternative (reward 1 each); the write-failure and forged-JUnit
controls are rejected (reward 0 each). The full 39-case CI matrix is separate;
an input check is not a behavioral pass.
