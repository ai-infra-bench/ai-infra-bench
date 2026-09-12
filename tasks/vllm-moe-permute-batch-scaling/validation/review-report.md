# PR #72 · MoE permutation

Correctness now includes 64/1023/1024/1025 experts in both alignment modes. All five output buffers, including untouched padding, are compared byte for byte, and the trusted parent independently derives their digests. A correct Oracle with only a 1023-expert cap is the new negative control. The independent challenge uses 2049 experts with different routing and geometry.

Version `1.3.2` passed the local statement, environment and verifier review. The statement is three prose paragraphs. The image, Base and cutoff are unchanged; performance timing and thresholds are unchanged.

9 full Harbor runs and 4 independent challenges met their expected outcomes. Base received 0; the final Oracle and every declared correct alternative received 1. Harbor reported zero errored trials. The final Oracle used the exact final executable snapshot.

| Control | Expected | Observed |
| --- | --- | --- |
| base | 0 | 0 |
| oracle | 1 | 1 |
| alternate-cuda-scaling | 1 | 1 |
| diagnosis-only-linear-scan | 0 | 0 |
| early-native-exit | 0 | 0 |
| early-native-immediate-exit | 0 | 0 |
| root-python-startup | 0 | 0 |
| expert-count-cap | 0 | 0 |
| oracle | 1 | 1 |

Current hashes, commands, image identities and raw evidence are in `e2e-evidence.json`. Earlier evidence and publication records describe previous revisions. Historical model rewards remain unchanged; missing final-code archives still limit complete historical replay. These changes are local and have not been committed or pushed.
