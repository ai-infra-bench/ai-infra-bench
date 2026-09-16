# Alternative correct implementation

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

Production type/style checks and build passed, and its nine recovery unit tests
passed. The ordinary-filename regression includes `__proto__` and `constructor`
after restart. The final formal Harbor trial earned reward `1`, with all 25
behavioral cases passing and all 2,158 original regression cases present without
new regressions. The final patch, verifier and image identities, trial identifier
and observed results are recorded in [e2e-evidence.json](e2e-evidence.json).
