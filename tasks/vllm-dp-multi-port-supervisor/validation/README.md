# Validation summary

Task 1.2.0 checks the public CLI, rank/device mapping, readiness and probe settings, invalid launch configurations, ordinary serving, and process/socket cleanup. Cleanup cases include descendants in a separate session and rank exits before and after readiness. The model backend is controlled; serving entrypoints, HTTP, processes and signals are real. No GPU inference or Kubernetes integration is claimed.

| Saved implementation | Full local Docker reward |
|---|---|
| Base | 0 |
| Oracle | 1 |
| Sequential probes with a callable alias | 1 |
| Original Codex answer | 0: detached descendant and listener leaked |
| Same Codex session after one feedback message | 1 |

These results use the pinned image in `task.toml`, 4 CPUs and 16 GiB per run. The feedback-assisted result is separate from the original task 1.1.0 reward of 1. The follow-up ran full Docker scoring, not a fresh Harbor rollout. Seven other negative controls retain historical task 1.1.0 local evidence; these were not all rerun locally against 1.2.0. Current repository CI determines merge readiness.

`ci-cases.json` and its nine patches are executable CI inputs. Detailed logs, historical reports, pre/post input hashes, build records, rollout review and feedback trajectories are retained in the [validation evidence ZIP](https://raw.githubusercontent.com/YaooXu/ai-infra-bench/b267b9983a96efcfed659c2c677a19efd4eff339/pr54-validation-evidence.zip). The archive includes the complete task snapshot before this documentation cleanup; large workspace tar files and Docker images are not included.

ZIP SHA256: `8d3f1bc9cd723e4fbe377cbd49e442fb149ffa5e7aca2a0bcf6bf75d3c09083a`.
