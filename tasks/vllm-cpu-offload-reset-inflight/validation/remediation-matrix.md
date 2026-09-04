# Remediation matrix

| ID | Priority | Finding | Approved remediation | Status |
|---|---|---|---|---|
| R1 | P1 | CPU verifier accepted implementations that released transfer-owned blocks before completion. | Observe CPU and GPU block-pool allocation capacity through the real Scheduler boundary, add allocation pressure, and add an early-release adversarial control. | Resolved: four ownership cases and the composed lifecycle test reject the control |
| R2 | P2 | Agent budget was one hour instead of the fixed ten hours. | Set `agent.timeout_sec` to `36000`. | Resolved |
| R3 | P2 | Evidence hashes and the completion-process description were stale. | Refresh executable hashes, describe deterministic worker-completion substitution accurately, and rerun the complete validation matrix. | Resolved: evidence refreshed from the hardened executable snapshot |
