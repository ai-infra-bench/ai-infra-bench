# Remediation matrix

| ID | Priority | Finding | Approved resolution | Validation | Status |
|---|---|---|---|---|---|
| R1 | P1 | The verifier accepted a correct receive fix combined with a broken `vllm serve` entrypoint. | Add real CLI parsing/dispatch and OpenAI-compatible ASGI request/response checks; add a receive-correct but serving-broken adversarial control. | `break-cold-serving.patch` must receive reward 0 while Oracle and both correct alternatives receive reward 1. | Resolved |
| R2 | P1 | Hybrid, mixed-block-size, and Mamba repairs affected reward even though the task contract is the MiniMax single-FullAttention deployment. | Limit reward cases and the receive E2E to single FullAttention groups; retain block-size, TP-rank, non-Eagle, and repeated-request variations. Promote the task-scoped single-group implementation to a correct alternative. | `alternative-single-group-padding.patch` must receive reward 1; no hybrid or Mamba profile is collected or run by the verifier. | Resolved |
| R3 | P2 | The constructed prompt's exact generated corruptions were not captured with the full model deployment. | No change authorized in this hardening pass. | User explicitly deferred this finding. | Deferred |
| R4 | P2 | General image-build tooling is not fully content-pinned. | No change authorized in this hardening pass. | User explicitly deferred this finding. | Deferred |

The frozen reward contract is: for the MiniMax single-FullAttention
configuration, an externally reported Eagle hit must load every chunk in that
reported token range into the target buffers. Non-Eagle loads, TP rotation,
repeated receive requests, CLI dispatch, request validation, and HTTP response
serialization must remain operational. The model forward pass and external
Mooncake transport remain deterministic substitutions because they do not
determine the receive-mask defect.
