While profiling a valid DP+EP fused-MoE layer through the normal layer and
factory path, I see `Current vLLM config is not set.` even though the layer has
a usable parallel configuration. The same warning can also appear during its
forward pass.

Please fix this lifecycle: configured profiles and forwards must not warn,
even when temporary global configuration context is absent or changes between
construction and forward. If there is conflicting ambient state, the active layer's
own configuration must win. A real access with no available
configuration must still emit the warning.

Work in `/workspace/repo` and keep the real Triton MoE forward behavior. Do not
solve the problem by globally suppressing, downgrading, filtering, or
monkeypatching the diagnostic. Constructor parameters and attributes can be
organized however the implementation needs. Reproduce the warning yourself by
building a configured fused-MoE kernel through the normal factory path and
profiling its construction and forward while the temporary global configuration
context is absent or changes between construction and forward.

During DP+EP profiling, preserve the backend's worst-case workspace reservation
even when routing uses only a small local token batch. An ordinary layer must
keep its ordinary workspace requirements when the ambient configuration belongs
to a DP+EP layer. Workspace shape-query count and internal storage are not
prescribed.
The default routing chunk bound for this workspace profile is 16,384 tokens;
retain that bound while fixing configuration ownership.
