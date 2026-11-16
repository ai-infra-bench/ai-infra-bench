# Pi agent trace: review and validation

## Automatic candidate integration

The public contract requires the candidate extension to provide `child-context.mjs`
with `childEnvironment({ pi, toolCallId, env, context, extensionPath })`. The verifier
loads that candidate-owned module during a real tool execution, as the unprivileged
`node` user, and spawns the child with its returned environment. No per-submission
curator adapter, approved file hash or private API discovery is required.

The child fixture supplies the spawning tool's actual call id while another tool
is active. It observes the child's real session and trace files, including a manual
compaction. The observer never constructs trace ids or parent context. Missing or
invalid integration is an ordinary candidate behavior failure, not an unscored
integration request.

## Standard CI and Harbor

List the active version's cases and prepare one with the shared CI entrypoint:

```bash
python3 .github/scripts/task_ci.py cases --task pi-agent-trace
python3 .github/scripts/task_ci.py prepare-case \
  --task pi-agent-trace --case alt-opus-cooperative-bridge-v1 \
  --image sha256:<immutable-local-image-id> --output <new-task-directory>
```

Run the prepared task through the normal Harbor runner with the agent name printed
by `prepare-case` (`oracle` for reference/control patches, `nop` for Base), then
validate the collected result with `task_ci.py check-result`. Preserve the prepared
task hashes, image identity, logs, completion inventories and collected reward.
`validation/ci-cases.json` contains current behavioral controls; a declared expected
reward is not a measured result. Read `apply_after` before materializing a patch.

The two adapted alternatives use different tracer representations and child
integration protocols. They implement the public callable bridge, not a pinned
private event protocol. The closure/module variant includes the sequential-tool
persistence fix; the class/queued-span variant already flushes resolvable entries
at tool start. Their expected rewards require validation of this integrated version.
Original patches and prior adapter-based replay utilities remain in Git history
and external frozen review evidence, rather than the active case directory.

The lifecycle suite also kills a process while a second sequential tool is still
running and checks that the first tool's persisted result already has its trace
end record. The matching negative control changes only that early flush in the
current Oracle. Child-event callback cardinality or unknown-call behavior is not
part of the public callable contract; old controls imposing that private protocol
are not active cases.

The current negative controls include missing/incorrect propagation, wrong sibling
parent, missing start attributes, premature entry references, raw-prefix rewrite,
hidden model reports and early successful exits. Judge report-forgery and early-exit
controls by their actual reached markers, parent exit status and completed case
inventory. Root-owned final output alone does not prove same-process report integrity.

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

The current `environment/image-manifest.json` identifies the full-build image and
its hashed inputs, including the named package cutoff override. The optional
incremental recipe is not the recorded build for that image; use an explicit
compatible parent and retain its separate build evidence if choosing that path.
`baseline_check.py` mirrors the full recipe's embedded checker. Incremental builds
do not download source or dependencies.
