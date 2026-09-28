# Pi agent trace: review and validation

## Child-process integration

The instruction fixes how a cooperating tool obtains a child environment: it emits
`agent-trace:child-env` on `pi.events` with `{ toolCallId, env, reply }`, and the extension
replies synchronously. `tests/child-binding.mjs` is the verifier's cooperating tool side of
that contract; it constructs no trace ids and reads no candidate state, so every
submission is scored automatically; an earlier draft needed a curator-written binding
per submission, which pinning the event removes.

The child fixture supplies its actual toolCallId, obtains its environment while a
second tool is running, and spawns a real Pi child. It observes trace/session files;
no Oracle-selected environment key, private function, or internal state is asserted.
The child performs manual compaction so both run and compaction root parentage is
checked. The parent environment is compared before and after tools finish.

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
