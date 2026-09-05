Work in `/workspace/repo`.

I am deploying vLLM data-parallel workers behind an external load balancer. At
the moment I have to launch every local rank separately, so Kubernetes has no
single process or endpoint that represents the health of the whole node. I have
also seen one rank die while the other ports stayed up and the node continued
receiving traffic.

I would like one `vllm serve` invocation to start one API endpoint per local DP
rank on consecutive ports beginning at `--port`, and to supervise those ranks
as one group. Each local DP rank should receive the corresponding accelerator
assignment from the existing launch configuration.

Please expose this mode through `--data-parallel-multi-port-external-lb` and
`--data-parallel-supervisor-port`. The supervisor port should provide aggregate
`/health`, `/ready`, and `/readyz` endpoints, and it must not report readiness
until every local rank is healthy.

I also need the child-health probe interval, timeout, and consecutive-failure
threshold to be configurable with `--dp-supervisor-probe-interval-s`,
`--dp-supervisor-probe-timeout-s`, and
`--dp-supervisor-probe-failure-threshold`, respectively.

Startup and shutdown also need to be safe. Incompatible settings or overlapping
ports should be rejected without leaving a partially started group behind. If
a child exits or becomes unhealthy, the whole group should stop, and termination
must reach every child so that no process or listening socket is orphaned.

I do not require a particular internal design, but the public command and its
process lifecycle should behave consistently with existing `vllm serve` usage.
