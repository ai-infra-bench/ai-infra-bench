# Reference solution

`solve.sh` applies `oracle.patch` to the pinned Base checkout. The patch adds
the background-processes extension, its user documentation, and offline tests.

The behavioral contract is defined by `../instruction.md`; the reference is one
implementation of it. Logs are streamed to disk and paged with bounded reads,
without retaining an offset for every line in memory.

`../validation/ci-cases.json` records the alternative implementations and negative
controls with their patch hashes. Build, replay, and review results are retained
with external Harbor records, outside the task directory.
