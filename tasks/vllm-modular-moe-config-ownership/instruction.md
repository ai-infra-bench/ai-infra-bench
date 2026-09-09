We create two otherwise similar `FusedMoE` layers with different DP+EP
parallel configurations. When their modular kernels are built and profiled, a
kernel can behave as though it belongs to the other layer or to an older
process-wide configuration.

Please make each production modular factory and affected backend follow the
MoE configuration of the active layer. That configuration must determine the
kernel's behavior even if another layer or ambient configuration has
conflicting DP/EP values, changes after construction, or is absent.
Downstream consumers must stay tied to the active layer rather than a previous
layer or process-global value.
Compatibility construction without a layer configuration must remain non-DP+EP
and must not require global state.

Work in `/workspace/repo`. The real single-rank Triton MoE numerical path must
remain unchanged. Non-modular functional backends must not gain a dependency
on generic process-wide parallel configuration. The implementation is free to
choose its constructor keywords, attributes, and kernel storage as long as the
factory, kernel profiling, and backend consumers show the behavior above.

During DP+EP profiling, preserve the backend's worst-case workspace reservation
even when routing uses only a small local token batch. An ordinary layer must
keep its ordinary workspace requirements when the ambient configuration belongs
to a DP+EP layer. Workspace shape-query count and internal storage are not
prescribed.
The default routing chunk bound for this workspace profile is 16,384 tokens;
retain that bound while fixing configuration ownership.
