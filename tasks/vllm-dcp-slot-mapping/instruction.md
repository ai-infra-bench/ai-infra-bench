Work in `/workspace/repo`.

I am trying to move one of my deployments from the original GPU model runner
to Model Runner V2. It already uses Decode Context Parallelism and works as
expected with the original runner, but enabling V2 makes some requests fail or
produce different output. I see the same problem when CUDA graphs are enabled,
so I cannot roll V2 out for this deployment yet.

Please make the existing DCP configuration work correctly with Model Runner V2.
It needs to remain correct across supported paged-KV-cache layouts and across
successive decode steps, in both eager and CUDA-graph execution. Deployments
that do not use DCP must continue to behave as before.

Please investigate the production behavior and make the fix robust across
these execution modes without changing non-DCP deployments.
