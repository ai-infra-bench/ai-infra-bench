Work in `/workspace/repo`.

I am starting to roll out Model Runner V2, but requiring every operator to know
when it is safe and set `VLLM_USE_V2_MODEL_RUNNER` manually has been fragile. I
would like vLLM to choose from the resolved serving configuration when this
setting is absent.

For the initial rollout, supported dense, unquantized Qwen3 text-generation
configurations should select V2 automatically, while configurations that V2
cannot run should remain on V1. I still need an explicit escape hatch: `0`
must select V1 and `1` must select V2. If I explicitly request V2 for an
unsupported configuration, startup should explain the incompatibility instead
of silently changing my choice.

Please make sure the worker created for an engine startup uses the resolved
selection rather than reading a conflicting default.
