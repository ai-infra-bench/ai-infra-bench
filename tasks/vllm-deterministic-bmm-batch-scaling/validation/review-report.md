# PR #73 · BMM

Long FP32 reductions now run under the same numerical tolerance as short reductions. The trusted parent computes the reference in float64 from its own operands. Oracle and both accepted alternatives use TF32x3 precision; the previous Oracle is retained as a precision-loss negative control. The fresh challenge adds two different long reductions and no longer demands unsupported batch-zero behavior.

Version `1.2.4` passed the local statement, environment and verifier review. The statement is three prose paragraphs. The image, Base and cutoff are unchanged; performance timing and thresholds are unchanged.

13 full Harbor runs and 4 independent challenges met their expected outcomes. Base received 0; the final Oracle and every declared correct alternative received 1. Harbor reported zero errored trials. The final Oracle used the exact final executable snapshot.

| Control | Expected | Observed |
| --- | --- | --- |
| base | 0 | 0 |
| oracle | 1 | 1 |
| alternate-persistent-kernel | 1 | 1 |
| diagnosis-only-batch-loop | 0 | 0 |
| early-exit-os-exit | 0 | 0 |
| early-exit-system-exit | 0 | 0 |
| forged-report-exit | 0 | 0 |
| replay-observations | 0 | 0 |
| out-view-return | 0 | 0 |
| strict-out-rejection | 0 | 0 |
| alternate-copy-compatible-agent | 1 | 1 |
| long-k-tf32-loss | 0 | 0 |
| oracle | 1 | 1 |

Current hashes, commands, image identities and raw evidence are in `e2e-evidence.json`. Earlier evidence and publication records describe previous revisions. Historical model rewards remain unchanged; missing final-code archives still limit complete historical replay. These changes are local and have not been committed or pushed.
