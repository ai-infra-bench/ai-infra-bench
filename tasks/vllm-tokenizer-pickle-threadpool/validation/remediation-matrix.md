# Remediation matrix

| ID | Severity | Finding and evidence | Planned change | Validation | Status |
|---|---|---|---|---|---|
| C1 | blocking | New task provenance and public-boundary contract require validation against issue #45433 and PR #45460 review. | Start from Ray/multiprocessing receiving `None`; preserve pooled thread safety without requiring the Golden return statement. | Public Base returns `None`; Oracle and alternative survive pickle and spawn. | fixed |
| C2 | blocking | Environment and exact cutoff dependencies are missing. | Generate and build the hardened image with a self-contained fast tokenizer. | Lock, digest stability, Git/dependency/hidden-file/network isolation pass. | fixed |
| C3 | blocking | Verifier and controls are missing. | Cover pickle protocols, cloudpickle, spawn, encode/decode, batch, pool size, idempotence, and slow-tokenizer controls. | Base/Oracle five rounds; reconstruction-helper alternative passes; partial fixes fail. | fixed |
| C4 | blocking | Evidence and Harbor records are missing. | Record actual hashes, runs, limitations, image, and Harbor identifiers. | Evidence audit and Harbor Oracle pass. | fixed |
| C5 | blocking | The first Oracle run reached the real pickle/spawn boundary but one unit case called `batch_encode_plus`, which is absent from the cutoff-locked Transformers API. | Exercise the same batched-call behavior through the current public `tokenizer([...])` interface. | Oracle passes all 10 cases; Base still fails only serialization-dependent behavior. | fixed |
