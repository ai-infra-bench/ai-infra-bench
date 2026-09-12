# PR #74 · Fused MoE

The production factory constructs the actual modular wrapper, and the fixture calls its production apply interface without reading internal kernel storage. Model weights and deterministic router outputs are supplied at the normal layer interface. Input snapshots allow legitimate in-place output. Oracle and valid controls avoid the unrelated ambient CustomOp lookup; a renamed-storage alternative verifies implementation freedom. The original wrapper candidate remains a negative control. Warning behavior, workspace extent and numerical output remain independently checked.

Version `1.2.6` passed the local statement, environment and verifier review. The statement is three prose paragraphs. The image, Base and cutoff are unchanged; performance timing and thresholds are unchanged.

15 full Harbor runs and 6 independent challenges met their expected outcomes. Base received 0; the final Oracle and every declared correct alternative received 1. Harbor reported zero errored trials. The final Oracle used the exact final executable snapshot.

| Control | Expected | Observed |
| --- | --- | --- |
| base | 0 | 0 |
| oracle | 1 | 1 |
| alternate-config-wrapper | 1 | 1 |
| constructor-global-cache | 0 | 0 |
| early-exit-os-exit | 0 | 0 |
| early-exit-system-exit | 0 | 0 |
| forged-report-exit | 0 | 0 |
| constant-numerical-output | 0 | 0 |
| replay-observations | 0 | 0 |
| alternate-production-quant-owner | 1 | 1 |
| alternate-workspace-diagnostic | 1 | 1 |
| undersized-profile-workspace | 0 | 0 |
| legacy-custom-op-wrapper | 0 | 0 |
| alternate-wrapper-storage | 1 | 1 |
| oracle | 1 | 1 |

Current hashes, commands, image identities and raw evidence are in `e2e-evidence.json`. Earlier evidence and publication records describe previous revisions. Historical model rewards remain unchanged; missing final-code archives still limit complete historical replay. These changes are local and have not been committed or pushed.
