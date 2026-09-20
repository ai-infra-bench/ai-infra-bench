# Public reference comparison

This author-side comparison uses snapshots retrieved on 2026-09-15. It is excluded from the solver prompt and image. It establishes differences in the requested contract, not a claim that checkpointing or crash recovery is novel.

| Reference | Existing behavior | Gap relative to this task | Evidence type |
| --- | --- | --- | --- |
| [pi-rewind](https://github.com/arpagon/pi-rewind) | Git-backed snapshots, persisted refs, resume and model-turn checkpoints, file/conversation restore commands | The observed core restore accepted an idle human conflict, overwrote the human content, removed an unrelated human-created file, and restored mode `0640` as `0644` | Direct execution of public `createCheckpoint` and `restoreCheckpoint` in the pinned image; see observation JSON |
| [Pi PR #5521](https://github.com/earendil-works/pi/pull/5521) | File checkpoints for built-in edit/write, external-change guards, persisted restore marker and replay | The snapshot documents that Bash changes are not captured and termination before turn-end persistence can lose that turn's manifest; external conflicts are skipped per file rather than rejecting the entire operation | Static inspection of the public diff and its documentation, not an end-to-end adaptation |

The direct core probe uses only exported reference functions and a disposable Git repository. From this task's directory, run `node --experimental-strip-types validation/check_public_rewind.mjs /path/to/the/recorded/core.ts`. The exact source, probe and public-diff hashes are in [public-reference-observation.json](public-reference-observation.json). The source snapshots are not bundled; repeating this historical observation requires supplying the matching snapshot. The public core has a different interface from this task; no Harbor reward is attributed to it.

Neither reference was presented to the solver. This comparison is not evidence that a strong coding agent cannot adapt existing ideas. Actual model difficulty remains uncalibrated until separately authorized model attempts are reviewed.
