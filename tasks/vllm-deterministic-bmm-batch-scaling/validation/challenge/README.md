# Independent challenge

Six dtype/shape cases; seven invalid-input cases and 24 output-copy compatibility cases; launches at batches 1/7/29; three prescribed shapes with five warmups, twenty iterations and five timing rounds. Independent challenge adds empty and singleton dimensions, noncontiguous inputs/output and new geometry. Base is already batch-invariant: its target failure is launch scaling/performance, not loss of determinism.

Run `challenge_bmm.py` in the pinned image with the candidate source at /workspace/repo, after applying the selected Base-relative patch. GPU tasks require the declared A100; streaming runs on CPU. The challenge lives outside the agent image and grading tests. Expected: Oracle and `alternate-persistent-kernel.patch` pass; Base and the task-specific incorrect control fail. These are expectations, not recorded results; actual command, exit code, image and patch hashes are in e2e-evidence.json and its raw logs.
