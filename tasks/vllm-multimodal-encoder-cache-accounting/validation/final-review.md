# 1.3.0 workspace migration — Docker acceptance passed

All active paths now use /workspace/vllm. The relocated image was built offline
on A100 from committed Dockerfile.workspace and pinned in task.toml. Source
Base/tree/cleanliness and agent imports were checked; no /app alias remains.
The full reconstruction Dockerfile is migrated too.

From pulled source commit 08e68b6, 25/25 real test.sh rewards matched, all 12
positive independent challenges passed, and both Base challenges failed as
expected. The environment canary imported the new source and collected nine
upstream tests. See e2e-evidence.json for hashes and raw results.

Harbor orchestration/host collection smoke remains pending for publication.
These are direct Docker results, not Harbor job results.
