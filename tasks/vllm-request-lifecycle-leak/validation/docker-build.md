# Final image and verifier validation

Validation date: 2026-09-05 (Asia/Shanghai).

## Final image

The task was rebuilt after the review at commit
`dc786dfa05e66036db486467ecd054e3ee33f25a`.

```text
tag: ai-infra-bench/vllm-request-lifecycle-leak:base-e94ec597334d
image: sha256:243698b78997390a803dc06234f9a33194fdfd1cee4d7eefdbb8eeb96a12ae1b
size: 3948995902 bytes
user: agent
workdir: /workspace/repo
```

The build uses the digest-pinned v0.17.1 CPU image only as a donor. It creates
a filtered root filesystem and copies that into a new `FROM scratch` stage,
excluding the donor's installed vLLM Python source, distribution metadata,
caches, and workspaces. Native modules are staged into the exact Base source.

Final-container audit:

```text
HEAD=e94ec597334d9a3e9b0d04bc17152e2747c83d51
tree=bfdf97989c2997f550a44ebc42ad8aa5582d67a7
reachable commits=2000
remotes=0 tags=0 reflogs=0
candidate import=/workspace/repo/vllm/__init__.py
git fsck --unreachable: empty
working tree: clean
```

No `vllm/v1/request.py` exists outside the candidate checkout. `/tests`,
`/solution`, and `/validation` are absent. Docker history contains only the
filtered-root copy and final-stage build steps, not the donor's source-bearing
layers. Runtime validation used `--network none` and the dedicated project
Docker daemon.

## Trusted verifier boundary

`tests/test.sh` execs a root-owned isolated-Python supervisor. The supervisor
creates a root-only reward file initialized to 0 and runs each raw observation
as the unprivileged `agent` user. Case identities, expectations, completeness,
and the final reward remain in the parent. A 256-bit nonce binds each child
observation to its invocation; missing, duplicate, malformed, failing, or
timed-out observations leave reward 0.

The eleven cases cover candidate-source selection, a live request, normal
completion, waiting/running cancellation, streaming wait and true end, initial
and incremental/streaming prefix hashes, and completion without prefix cache.
The lifecycle cases use real `Request` and production Scheduler methods. Only
unrelated engine resources (KV/encoder release managers and connectors) are
minimal local substitutes, since no model execution is required to exercise
the Python ownership bug.

## Final-image control matrix

```text
Base                                      reward 0 (7/11)
Oracle                                    reward 1 (11/11)
Scheduler-side correct alternative        reward 1 (11/11)
finish-only incomplete implementation     reward 0 (8/11)
SystemExit(0) at candidate import          reward 0 (0/11)
os._exit(0) at candidate import            reward 0 (0/11)
```

Base loses ownership but retains the request/payload after normal completion,
both cancellation states, and streaming end. The incomplete repair fixes only
normal stopped completion, then fails both cancellation cases and streaming
end. The correct alternative clears the retaining callback at the Scheduler's
final ownership boundary rather than at the Oracle's construction site, and
passes without changing hash or live-session behavior.

Both early-exit attacks execute at the candidate import boundary and return
process status 0 for every child. The trusted parent nevertheless observes no
completed case and leaves reward 0, demonstrating that grading is not derived
from candidate process exit status.

The repository CI helpers report:

```text
task_ci.py validate: OK vllm-request-lifecycle-leak
task_ci.py cases: Base 0, Oracle 1, alternative 1, incomplete 0,
                  SystemExit 0, os._exit 0
task_ci.py image-check: exact declared image ID and Base commit
```

## Stability and Harbor

Five-round Base/Oracle stability and the final Harbor Oracle run are recorded
in `e2e-evidence.json`. Results there are bound to this image and the final task
file hashes; older CUDA and pre-hardening runs are intentionally not reused.
