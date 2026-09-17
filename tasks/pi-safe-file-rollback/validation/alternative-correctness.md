# Positive implementation controls

`alternative-blob-journal.patch` is a complete patch against the pinned Pi base.
It reuses the reference implementation's public SDK, RPC and TUI integration but
replaces the storage and restore mechanism:

| Reference mechanism | Alternative mechanism |
| --- | --- |
| Inline file images in an atomically replaced metadata file | Immutable SHA-256 content blobs and append-only checksummed metadata frames |
| Direct destination file rewrites | Sibling temporary files published with atomic rename |
| Whole metadata-file replacement | Complete-frame replay with incomplete trailing-frame truncation |

Checkpoint selection, idle-edit conflicts and session branching preserve the same
published contract. The alternative uses ordinary production APIs and contains no
verifier hooks or scenario identifiers. Its purpose is to check that grading
accepts a different persistence and restoration algorithm, not to claim every
part of its integration was developed independently.

Its prior qualification included production type/style checks, a build and nine
recovery unit tests. The ordinary-filename regression includes `__proto__` and
`constructor` after restart. The version `0.0.2` formal Harbor trial earned reward
`1`, with all 25 behavioral cases passing and all 2,158 original regression cases
present without new regressions. That is historical evidence; validation of a
later verifier must use the matching identities and results in
[e2e-evidence.json](e2e-evidence.json).

`minimal-checkpoint-metadata.patch` is a second complete positive patch against
the same Base, introduced for version `0.0.3`. It derives from Oracle and changes
only production SDK/RPC presentation:

| Public result | Variant |
| --- | --- |
| Checkpoint records | Only `{ id }`; no session or conversation-entry metadata |
| Checkpoint listing | Reverse the reference implementation's public list order |
| Successful RPC rollback | Empty acknowledgement data within the existing response envelope |
| Preflight conflict diagnostic | Report `blocked` while preserving the same refusal and retry behavior |

The variant uses the ordinary public methods and RPC dispatcher, not verifier
hooks or runtime monkeypatches. It preserves Oracle's storage and recovery
mechanism, so it is an interface-representation control, **not another independent
algorithm**. It tests whether the verifier accepts the freedoms stated in the
550-word first-person prompt. Actual rollback and conversation comparisons, plus
conflict-resolution retry, still enforce the substantive behavior. Its observed
reward must be read from the corresponding formal matrix; patch application
alone does not establish correctness.
