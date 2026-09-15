# Added behavior coverage (v0.0.8)

The statement is unchanged. These scenarios exercise its existing partial-failure,
message-size, and communication-resource cleanup promises. They use real Pi
processes and candidate transport code. The scripted provider controls inputs and
causal barriers; it does not deliver messages or release candidate resources.

| Case | Construction and observation | Incorrect control |
|---|---|---|
| broadcast_partial | A/B/C are live. B and C are blocked in external work. Temporarily remove write permission on C's actual mailbox; leave B writable. A broadcasts through the real tool. Require B accepted, C explicitly failed with a reason, complete delivery to B and no delivery to C. Restore only the injected permission before releasing work. | hide_partial hides actual broadcast failures while keeping successful sends |
| size_below | Send complete UTF-8 content one byte below the reviewed implementation's documented maximum. Check exact content in the recipient's next model input. | truncate silently cuts content to 32K characters |
| size_at | Same at the inclusive maximum; markers at both ends and multibyte content distinguish bytes from characters. | truncate |
| size_over | Send one byte above the maximum. Require explicit rejection; then send a valid finding and confirm the rejected message was not leaked and normal delivery still works. | accept_oversize counts characters instead of UTF-8 bytes and admits an oversized message |
| cleanup_repeated | Run four sequential communicating teams in one living parent. Observe process listeners and non-provider communication handles immediately before actual parent model requests. Allow one-time initialization, then reject growth after the warmup dispatch. | leak_listener retains the actual per-dispatch exit callback |
| cancel_queued | Hold B in an external tool; let A's real send be accepted; then cancel the parent before B can consume it. Check child termination and the actually-used mailboxes for retained undelivered findings. | leak_queue removes mailbox disposal while keeping listener cleanup |

An already-finished worker may legitimately be omitted from broadcast targets.
The partial-failure scenario therefore uses a live recipient with a real OS write
failure; it does not require reporting an excluded worker as a failed target.

Ordinary retained logs and empty directories are not failures. The cleanup checks
observe growing live resources and retained delivery-queue content, rather than
requiring a particular temporary-directory name to disappear. Normal-exit and
cancellation checks cover different failure modes; they are not exhaustive proof
about every possible resource type.

## Curator-owned scenario profiles

`tests/scenario.py` contains the reviewed profile for the reference file transport.
The renamed JSONL-spool alternative uses the same resource ownership model.
A separate 4 KiB-limit correct control supplies `tests/scenario_binding.py` and
runs the exact same boundary logic at 4095/4096/4097 bytes; the default reference
profile uses its declared 1 MiB limit. The statement imposes neither value.

A different transport or limit requires a reviewed scenario profile via
`--scenario` / `/tests/scenario_binding.py`, alongside the public-tool binding.
The profile may identify real resources, inject a real delivery failure, restore
that fault, and inspect cleanup. It must not fabricate send results, enqueue or
inject messages, drain queues, or clean up the implementation on its behalf.
Candidate-provided Python must never be loaded as a trusted profile.

Resource hints come from the observation extension running in the real process.
The scorer cannot read `/proc/<other-uid>/environ` in this container; the first
smoke exposed that limitation. Paths supplied by those hints must stay beneath
the case's disposable scratch tree and are opened component by component with
`O_NOFOLLOW`; arbitrary privileged filesystem paths are not accepted.

The v0.0.7 G6/G56 scores remain historical. These new scenarios do not establish
new scores for those submissions until their different transports and declared
limits have reviewed scenario profiles. Missing adaptation is an integration
problem, not evidence that an implementation violates the feature contract.

An implementation without a declared finite limit must not be assigned an invented maximum. Review an appropriate large-message acceptance-or-explicit-rejection scenario before grading it with this version; the supplied finite-limit profile does not certify that case.
