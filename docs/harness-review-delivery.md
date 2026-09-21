# Harness review integration

This change brings the reviewed Plan Mode and Safe File Rollback revisions into
the current public task layout, adds the NeMo Gym Responses–Messages bridge, and
integrates the reviewed Subagent Messaging scorer repair.

Plan Mode now accepts the public interaction and tool-result presentations
allowed by its statement. It independently restores the original utility tests
while permitting relevant candidate tests. Rollback accepts retained historical
checkpoint listings and tests the public session API without requiring private
helper layout. It also covers tracked files that match ignore rules.

Messaging uses an explicitly reviewed interface/scenario profile for each
submission. Missing or stale adaptation is an integration failure, not a model
score. See [reviewed replay](pi-reviewed-replay.md). Plan UI adaptation is described
in [UI bindings](pi-plan-mode-ui-bindings.md).

NeMo asks for reusable conversion in both directions and a default Messages
route through the existing Responses backend. Its 27 behavior groups cover the
supported public contract, including a real HTTP/SDK boundary. The agent and
verifier remain separate, and CI preserves the complete checkout needed for
transfer. The website includes the same public contract alongside the statement.
NeMo controls apply to Base; Oracle-relative Pi controls declare that separately.
CI checks Harbor's Oracle exit-status record before accepting a reward, so failed
patch application cannot count as a successful positive or negative control.

All four public tasks retain the repository's initial release version `1.0.0`.
Plan `v0.0.11`, Rollback `v0.0.9` and NeMo `v0.0.10` name earlier development
snapshots; their historical results do not identify the new packaging by
version number alone. Source revisions and file hashes identify exact inputs.

The integration is based on `bbb0dbde7fd799d1f62eefe369a8fb6ae383eaa4` from
`agent/full`. It preserves that branch's scorer isolation, standard collection
and canonical resource declarations. CPU validation overrides CPUs to four,
matching CI, and enforces memory limits. No new model calls are part of this
packaging validation.

The reviewed historical evidence includes 29 Pi attempt audits (24 original,
three valid channel fallbacks and two revised-task attempts), eight NeMo
cross-review submissions, three subsequent GPT-6 NeMo submissions, and eight
recovered Messaging submissions. Channel failures stay distinct from feature
failures. The GPT-6 NeMo submissions each passed 27/27 and five independent
combinations; their unchanged lockfiles remain a candidate delivery limitation,
not an extra benchmark requirement. Six colleague-supplied Messaging submissions
were unavailable and are not included in the eight recovered submissions.

Current packaging validation is recorded separately from those historical model
results. The retained images and recipe hashes are in each task's environment
manifest. Incremental builds reuse qualified immutable parents; they are not
presented as fresh full canonical builds. Raw run logs and model trajectories
remain outside the release tasks.

Final integration validation completed 73 declared cases with their expected
outcomes: 19 positive and 54 Base/negative controls. Plan contributes 16 cases,
Rollback 14, Messaging 7 and NeMo 36. See the
[per-case evidence and input hashes](harness-review-validation.json).
Every actual prepared instruction, verifier input and solution/control patch
was compared with this delivery. Oracle execution failures are checked separately
from rewards. NeMo's import-time exit control is intentionally rejected before
behavior groups can start; other NeMo cases execute all 27 groups.

The first packaging runs exposed an old Rollback dependency digest and the wrong
NeMo control patch base. Both were corrected, and those setup results are excluded
from the final matrix. The complete corrected matrices use the same retained
images and unchanged task behavior scorers. Independent remaining cases ran in
parallel; interrupted attempts are retained externally and excluded.

Local verification also passed 69 Python CI tests, 59 website tests, the Pages
build, all four task artifact audits and the repository's config, collection and
image-manifest checks. Rollback retains only the exact known Base auth-test
failure tolerance and requires a separate deterministic auth check to pass.
