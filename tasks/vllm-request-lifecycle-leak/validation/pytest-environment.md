# Pytest environment validation — 1.3.1

The image now preinstalls pytest 8.4.1, pytest-asyncio 1.1.0 and tblib 3.1.0 in `/opt/venv`, the agent's existing interpreter. The task contract, source Base and verifier are unchanged.

The full Dockerfile rebuild was interrupted when rebuilding the flattened donor layer left about 11 GiB free. The validated image was built incrementally from the previous validated image using exactly the new installation instruction; this is not evidence that a fresh full Dockerfile build completed. The final tag is `ai-infra-bench/vllm-request-lifecycle-leak:base-e94ec597334d-pytest`. It is local, not registry-published. Image identities and Dockerfile SHA are in [results.json](pytest-environment/results.json), and the actual incremental build recipe is retained alongside it.

In a fresh container, as the image's default non-root agent user and with `--network none`, `python -m pytest --version` reported 8.4.1, `python -m pytest --collect-only -q tests/v1/test_request.py` collected one test, and `python -m pytest -q tests/v1/test_request.py` passed that test. A separate fresh container collected all 87 tests in `tests/v1/core/test_scheduler.py`. Collection does not establish that all scheduler tests or the full upstream suite execute offline.

The unchanged official `/tests/test.sh` entrypoint was run in fresh containers with `--network none --user root --cpus 4 --memory 16g`, mounting tests read-only and a separate verifier log directory for each run. Base returned reward 0 for `normal: completed objects retained`. In the Oracle container, `runuser -u agent -- bash /solution/solve.sh` applied the existing patch before `bash /tests/test.sh`; reward was 1, with all behavior checks and nine OS observations completed. This is an entrypoint regression check, not a new Harbor or Codex rollout. Earlier model trajectories and rewards remain tied to version 1.3.0.

Logs, rewards and OS observations are in [pytest-environment](pytest-environment/). No private test or Oracle content was added to the agent image.
