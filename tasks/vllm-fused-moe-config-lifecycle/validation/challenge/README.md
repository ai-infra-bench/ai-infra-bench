# Independent challenge

Configured construction/profile, missing ambient lifecycle, conflicting DP+EP/ordinary owners, genuine missing-config diagnostic, and four numerical forwards. Challenge uses fresh 6/96/160/8/3 geometry and DP size 4. Alternative retains the owning VllmConfig and resolves parallel state lazily instead of the Oracle cached boolean.

Run `challenge_profile_lifecycle.py` in the pinned image with the candidate source at /workspace/repo, after applying the selected Base-relative patch. GPU tasks require the declared A100; streaming runs on CPU. The challenge lives outside the agent image and grading tests. Expected: Oracle and `alternate-config-wrapper.patch` pass; Base and the task-specific incorrect control fail. These are expectations, not recorded results; actual command, exit code, image and patch hashes are in e2e-evidence.json and its raw logs.
