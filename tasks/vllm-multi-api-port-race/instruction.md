We run a data-parallel vLLM deployment with eight API server processes. Startup usually succeeds, but 5 of 79 launches failed after model setup and before the application became ready. The first visible error was from an API server process:

```text
(ApiServer_0 pid=...) zmq.error.ZMQError: Address already in use (addr='tcp://<master>:39381')
...
RuntimeError: Process ApiServer_0 (PID: ...) died with exit code 1
```

The same configuration is stable with one API server. A CPU-only stress run that leaves only a small part of the ephemeral TCP range available makes the multi-server failure much easier to reproduce: the current build passed 1 of 28 launches, while an unaffected launch still produces distinct, usable input and output endpoints for every child.

Make multi-API-server startup reliable when several children bind their engine-facing ZMQ sockets concurrently. Keep the normal one-server and IPC paths working, and do not change frontends that cannot return a newly bound endpoint to the parent. A child that exits before startup completes must fail promptly instead of leaving the parent hung. Our large-model deployment already sets `VLLM_ENGINE_READY_TIMEOUT_S`; that setting must continue to control how long the parent waits for slow API server initialization.
