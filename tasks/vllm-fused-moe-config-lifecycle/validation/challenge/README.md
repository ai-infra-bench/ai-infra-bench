# Independent challenge

This challenge constructs the actual production wrapper and runs its Triton expert kernel with fresh geometry: six tokens, hidden width 96, intermediate width 160, eight experts, top-k three and DP size four. It checks the warning lifecycle, a genuine missing-config diagnostic and workspace ownership under conflicting ambient configurations. The formal verifier separately checks numerical results against parent-owned inputs.

Run `challenge_profile_lifecycle.py` on an A100 in the pinned image after applying the selected patch to `/workspace/repo`. Oracle and the config-wrapper alternative must pass; Base, the global-owner control and the unmodified legacy CustomOp-wrapper candidate must fail their behavioral checks. Commands, outcomes and hashes are recorded in `../e2e-evidence.json`. The challenge stays outside the agent image.
