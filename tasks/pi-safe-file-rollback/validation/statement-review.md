# Statement review

The original statement was reviewed before the reference implementation and
private tests were written, using only the statement and the pinned repository's
normal development materials. Version `0.0.3` rewrites that request as a
550-word, first-person user prompt. It describes the interrupted-work workflow,
manual-edit protection, recovery expectations and integration entry points in
connected prose instead of a detailed interface specification.

The revision retains the substantive task: persistent request checkpoints,
partial Bash effects, files and effective conversation restored together,
interrupted rollback resumed before execution, manual changes preserved across
requests, and abandoned branches excluded. Its operating assumptions still
bound the safety claim to a local Linux Git workspace and whole-execution-unit
process termination. It does not add a persistence design, source-file locator,
existing solution link, private hook or scoring-fixture hint. Public SDK/RPC
names identify integration entry points, not an implementation strategy.

The interface now deliberately leaves checkpoint metadata beyond `id`, listing
order and successful rollback response data to the implementation. A preflight
conflict need not retain a particular diagnostic status. The verifier follows
those freedoms: it selects checkpoint IDs without relying on order, performs
real rollback to inspect the conversation boundary, and verifies successful
retry after resolving a conflict. All 25 behavioral scenarios remain; these
changes do not remove the core safety requirements to make the task easier.

The revised statement received an independent blind review for clarity and
solution leakage. Persistent sessions, visible terminal IDs, the state
vocabulary and execution gates remain explicit. Automatic recovery may finish
before startup returns or continue asynchronously. Conflict ordering and exact
error wording remain unspecified. Git index preservation concerns entries,
not incidental cache bytes; restoring effective conversation does not require
deleting audit history or resetting accounting and model configuration.

Formal results apply only to the instruction, verifier and image identities
recorded in [e2e-evidence.json](e2e-evidence.json); earlier trial results are not
automatically evidence for this revision. The image itself is unchanged. Its
existing audit inspected the filesystem, every unique historical layer, Docker
metadata and Git objects, finding no private-artifact or private-marker matches.
Only the SDK transport driver and privilege preload become candidate-readable
during verification; scenario definitions and expectations remain private while
checks run. See [image-audit/summary.json](image-audit/summary.json) and
[review-report.md](review-report.md) for audit scope and limitations.
