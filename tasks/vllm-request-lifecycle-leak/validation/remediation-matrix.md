# Review remediation matrix

The original runtime evidence below is historical (PR #4 at `77f40e0`).
The permission follow-up stages read-only harness scripts into a protected
container-local directory and uses root-owned 0755/0644 output permissions so
non-root Harbor can collect results without granting candidate write access.
It also reports the exact file identity/mode on a failed trust check.
Runtime validation was deferred by the maintainer; current status is pending.

| Review finding | Remediation | Acceptance evidence |
| --- | --- | --- |
| P0: a candidate import can terminate the verifier successfully | `test.sh` invokes a protected root-owned supervisor. The supervisor initializes reward 0, owns all case names and expectations, launches each candidate observation as unprivileged `agent`, and writes 1 only after receiving and grading all 11 nonce-bound observations. | Both `SystemExit(0)` and `os._exit(0)` at the candidate import boundary reach candidate code but leave reward 0. |
| P1: the prior probe did not exercise request ownership/completion | The verifier now uses production `Scheduler.add_request`, `finish_requests`, `_handle_stopped_request`, running/waiting ownership queues, and the streaming duplicate/sentinel end path. | It covers normal completion, waiting and running cancellation, streaming wait/end, a still-live request, prefix caching on/off, initial/append/streaming block hashes, and object reclamation. |
| P1: implementation independence | Assertions are behavioral: scheduler ownership, weak lifetime observations, and produced hash sequences. They do not inspect source, AST, helper names, fields, or repair location. | A correct Scheduler-side cleanup patch—at a different repair location than Oracle—passes all 11 cases. An incomplete finish-only repair fails cancellation and streaming-end paths. |
| Gate 2: inherited donor layer exposes the accepted fix | The CPU release is now a build donor only. A filtered rootfs is copied into a new `FROM scratch` stage with installed vLLM source/metadata and caches excluded; only native artifacts are staged into the exact Base checkout. | Final history has no donor ancestry; runtime import is `/workspace/repo/vllm`; no second `vllm/v1/request.py`, task payload, remote/tag/reflog, unreachable object, or future Oracle object is present. |
| Environment provenance | Exact Base HEAD/tree are asserted, 2,000 reachable pre-Base commits are retained, and the shallow boundary is documented. | Final-image audit reports exact HEAD, 2,000 commits, clean tree, no remotes/tags, and clean `git fsck --unreachable`. |

GPU inference is not part of this task's scored boundary: the defect is Python
request ownership and reclamation. Large deterministic weak-referenceable
objects stand in for media tensors, while real `Request`, Scheduler lifecycle,
multimodal descriptors, block hasher, queues, and completion statuses remain
in the path under test.
