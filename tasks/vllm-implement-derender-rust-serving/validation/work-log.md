# Construction record

The construction and initial qualification below are historical at `2e654d4`. Current post-review results are in the final section and `e2e-evidence.json`.

- Benchmark branch: `tasks/vllm-implement-derender-rust-serving` (renamed from
  `codex/vllm-rust-derender-task` for publication at the user's request).
- Benchmark worktree: `/home/qunhong/workspace/ai-infra-bench-rust-derender`.
- Created from freshly fetched `origin/main`: `497a5b6e0c0c3c8a538ee1f09e25aac4967d5b1c`.
- Skill revision: the same clean remote-main worktree; task review skill,
  review rubric, validation playbook and create-task skill read from it.
- Frozen query: exact user-provided English text in `instruction.md`.
- Candidate upstream source: `e473e9036f979d546830aece9855027049faf0ba`.

## Completed work

- Built and qualified the pinned CPU environment and standalone render CLI.
- Adapted and validated a native Rust reference solution.
- Implemented independent HTTP behavior tests and Python/reference controls.
- Validated four incomplete implementations and a correct alternative.
- Completed stability, Harbor and isolation checks with actual evidence.
- Completed task README and strict artifact audit.

## Qualification history

- Built and retained the canonical image:
  `ai-infra-bench/vllm-implement-derender-rust-serving:base-e473e9036f97`,
  `sha256:b7e97708ef2d0f3455034d533f9a9a3e80eaa106ba72b5af568b2ccbc87ec1c1`.
- Exact instruction SHA-256:
  `fcb75e51e21e0088ce5044802068bfa1561879d4c5c762781a8d3d0c1e1619c0`.
- A no-test-mount Base render-only process returned health/models/render 200
  and both derender routes 404, without an engine or model weights.
- Image Git isolation, absent PR heads, absent task mounts, runtime resource
  hashes and `uv pip check` passed in a fresh container.
- First Python reference matrix: 47 passed, no errors or skips.
- First Rust reference matrix: 47 passed. Adding an independent special-token
  continuation challenge expanded it to 49, all passing.
- Existing Rust server and chat suites passed 382 and 291 cases respectively.
- Expanded Base matrix: 9 passed, 40 failed, no errors/skips; reward 0 and
  the 673 server/chat regression cases passed.
- A broader diagnostic also ran vllm-text: 89 passed, one failed because its
  unrelated Qwen3-0.6B network-download test cannot run offline, and one
  explicitly network-dependent test was ignored. It is not a rewarded suite.
- Control qualification completed. The first discard-state mutation compiled
  successfully, passed old APIs and failed seven continuation cases. The
  original-server-exit case was subsequently strengthened to cut inside a
  Unicode character; the final rerun failed nine cases as intended.

Working artifacts and raw logs are under
`/home/qunhong/workspace/ai-infra-bench-rust-derender-work/`.
The curator vLLM checkout is `vllm/`, at the exact Base with the provisional
Oracle patch applied. Oracle source derives from the public Rust derender
proposal and is adapted to the newer decoded-event and usage types.

Development containers `derender-base-dev` and `derender-oracle-dev` were
removed after their source and results were exported. Canonical and matching
cache-rebuild image tags remain retained. The working vLLM source and raw logs
remain at the path above.

The final 49-case matrix passes on Python, Oracle and the alternative. Five
Base rounds return 0; five final Oracle rounds return 1. The fresh Harbor
Oracle job `0a19ba8a-55c0-4408-b6b1-b33355b17703` completed with reward 1 and
zero framework errors. Strict artifact/image/patch audit returned five passing
checks, zero errors and zero warnings. See `e2e-evidence.json` for authoritative
hashes, actual results and the qualification-container timestamp-cache note.

The user authorized a standalone task PR from the `tasks/` publication branch.
Only this task directory is included; the Git commit and PR identify the
published snapshot. The branch rename and this record update do not change
the frozen instruction, environment, Oracle, verifier or validation controls.

## Post-review hardening

The user supplied an independent PR #52 report and requested assessment and
repair where needed. Both P1s were confirmed. The native server execution
boundary and terminal decoder behavior were repaired; the frozen instruction,
task metadata and canonical image were retained. Final qualification runs all
67 HTTP cases and 673 Rust regressions for Base, Oracle, a correct replay
alternative and six negative controls. Three fresh Harbor trials, repeated HTTP
matrices and independent boundary/terminal challenges provide final evidence.
Raw development and final artifacts are at
`/home/qunhong/workspace/ai-infra-bench-derender-hardening-work/`.
