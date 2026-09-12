I’m running vLLM DP workers behind an external load balancer. I currently have to launch each local rank separately, and there’s no single endpoint that tells Kubernetes whether the whole node is ready. If one rank dies, the other ports can stay up and the node keeps receiving traffic.

Add a mode where one `vllm serve` command starts and supervises one API server per local DP rank. Use consecutive ports starting at `--port`, and assign each rank its share of the devices from the existing launch configuration, including TP, PP and an already restricted device list.

Expose it through `--data-parallel-multi-port-external-lb` and `--data-parallel-supervisor-port`. The supervisor should serve `/health`, `/ready` and `/readyz`. All three should report not ready until every local rank is healthy, and stop reporting ready when a rank fails a health check.

Make the probe interval, request timeout and consecutive-failure threshold configurable through `--dp-supervisor-probe-interval-s`, `--dp-supervisor-probe-timeout-s` and `--dp-supervisor-probe-failure-threshold`. A non-200 response, connection failure or timeout counts as a failed probe. After the group has become ready, count failures separately for each rank, reset its count on success, and stop the group when a rank reaches the threshold. Before initial readiness, allow ranks to finish starting without counting unsuccessful health probes toward that threshold. A rank process exiting should stop the group even during startup.

Reject conflicting launch modes such as headless, hybrid LB and single-rank external LB, as well as invalid rank ranges, nonpositive probe settings and overlapping supervisor and child ports. A failed startup must not leave a partially running group behind.

SIGTERM or SIGINT should shut down the whole group. Clean up the rank processes and any descendants they started, even if a rank has already exited, and release their listening sockets. Don’t break ordinary `vllm serve` when the new mode is disabled. The internal design is up to you.
