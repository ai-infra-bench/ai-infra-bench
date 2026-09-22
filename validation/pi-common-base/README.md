# Context and Messaging shared-environment parity

This summary records measured runs on 2026-09-22. It reuses matching runtime evidence; it is not a new model evaluation or a claim that GitHub CI has passed.

The exact task files and retained image inputs in `parity.json` were checked against this contribution. Context uses the public history-scoring repair at `da6bc0d0`; Messaging uses the reviewed implementation at `837d38ae` (PR #109). The source Pi commit is `71dca871bc80b6bc97be37f0ca3189399d651fff`, with Node 22.23.2 and the unchanged dependency lock. Both task manifests retain the same measured image ID.

| Comparison | Implementations | Scenarios each | Identical before/after decisions |
|---|---:|---:|---:|
| Context | 11 | 12 | 132/132 |
| Messaging | 7 | 24 | 168/168 |

Every boolean scenario result and reward matches, including Base, reference, alternatives and negative controls. Messaging profiles were regenerated for the new image. Missing/stale profiles and malformed bindings remain integration failures; a trusted scorer crash remains a scoring error, rather than a model zero.

The complete native suite recorded **2,187 passes, 50 skips and 5 failures**: three existing TUI collection errors, an existing startup timeout, and one clipboard timer failure. Focused clipboard reruns passed three times in each image (four cases per run); the full-suite failure remains recorded. The frozen Pi `build:offline` reports TS2322, so these tasks preserve their original TypeScript source execution and do not claim a successful dist build.

## Local checks

```bash
python3 -m unittest discover -s templates/pi-harbor-node/tests -v
python3 -m unittest discover -s tasks/pi-context-management/tests -p test_verify.py -v
python3 templates/pi-harbor-node/generate.py --check tasks/pi-background-processes tasks/pi-agent-trace tasks/pi-context-management tasks/pi-subagent-live-messaging
python3 .github/scripts/task_ci.py validate pi-context-management pi-subagent-live-messaging
```

These checks passed: 15 template tests, two Context tests, four generated-file checks and two structural validations. Docker interactions in template unit tests are mocked and do not replace the measured runtime matrix. Background and Trace default generated Dockerfiles remain byte-identical.

## Rebuild and reproduce

With BuildKit, the public pinned dependencies and the retained image available, use `templates/pi-harbor-node/build.py --platform linux/amd64 tasks/<task>` and the normal Harbor validation cases declared in each task. Create fresh reviewed Messaging profiles for the rebuilt image before replay. A new image requires fresh runtime checks; the archived summary does not attest a different image. The measured build used temporary immutable dependency caches to access public content; no private cache address or build override is part of this contribution.

This is a draft environment migration pending review of the remaining native-suite limitations and public CI/image availability. The summary does not certify unknown submissions or all upstream tests.
