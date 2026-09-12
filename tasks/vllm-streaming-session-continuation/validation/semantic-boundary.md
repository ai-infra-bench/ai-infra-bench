# Semantic boundary

Public asynchronous generation API -> real vLLN session, scheduler, model execution and streaming output -> public RequestOutput fields.

The verifier uses a deterministic tiny local GPT-2 model on an NVIDIA A100 and observes only request IDs, finished flags, and generated token IDs. It does not inspect candidate-private fields or mock model execution.
