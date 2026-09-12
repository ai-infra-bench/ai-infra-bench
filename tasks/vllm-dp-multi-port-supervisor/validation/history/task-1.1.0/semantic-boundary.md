# Semantic boundary and bidirectional coverage

Public CLI and configuration -> real API rank processes and nested engine stand-ins -> real HTTP probe responses and process failures -> aggregate readiness and complete resource release.

The frozen API `run_server`, `setup_server` and `run_server_worker` paths run unchanged. The verifier replaces the model client context and model-specific HTTP serving boundary. It preserves existing callable identity, so early aliases do not bypass substitution. Both the CLI and candidate supervisor still determine process creation, configuration, device assignment, probe scheduling, monitoring and shutdown. Lightweight nested TCP listeners preserve ownership transitions without loading model weights. Ordinary serving passes through the same real entrypoints without the new flag.

| Contract | Observation |
|---|---|
| Every local rank gets a consecutive endpoint | Two- and three-rank HTTP workloads |
| Correct global rank and TP/PP device slices | Offset ranks, TP=2/PP=2, reordered restricted device list through the platform API |
| All three aggregate endpoints gate readiness | All-unready, partly ready, fully ready and failed-health states |
| Probe interval is configurable | Actual probe event spacing with scheduling tolerance |
| Probe timeout is configurable | Delayed responses below and above the configured timeout; actual retry spacing |
| Per-rank consecutive failures and success reset | Short separated failure bursts on both ranks, exact terminal failure count, timeout and connection failures |
| Startup failures leave no partial group | Conflicting flags, rank range, nonpositive probe settings, overlapping ports; actual listeners and adopted processes |
| Rank death terminates the owned group | Kill a real rank before and after initial readiness while it owns a live nested listener; observe retained process identities and listener closure |
| SIGINT/SIGTERM propagate and clean resources | Healthy and pre-readiness groups; direct TCP refusal and process-state checks |
| Ordinary serve remains usable | Existing single-server CLI, health transition and graceful termination |

The verifier is a Linux subreaper so failed candidates cannot make their descendants invisible merely by exiting. This is observation and test cleanup, not candidate cleanup: resource-release assertions run before the verifier kills anything. Process liveness checks avoid interpreting HTTP timeouts or psutil wait failures as release. A still-live nested listener is observed before the rank is killed.

Probe event records come from the task-owned response producer, alongside independent HTTP and OS-level process/socket observations; they are not candidate success reports. Candidate-containing Python processes are not a complete sandbox against arbitrary code tampering. The early successful-exit controls check the demonstrated completion boundary, not universal adversarial security.

The alternative changes concurrent probes into sequential probes and uses an early callable alias. Both choices are permitted: the task does not require parallel health requests or a particular API import spelling. Negative controls separately exercise premature readiness, ignored options, wrong failure counts, startup listener leakage, orphaned engine processes and successful early exits.
