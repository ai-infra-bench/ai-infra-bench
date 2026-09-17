# Environment lock

The exact vLLM Base is `36d7f19897843c9cbdb701ba88d0f2c29954fe44`, tree `647523aac911ae44a1dcaab79ef66d58290b478e`. The cutoff is `2026-04-01T05:42:27Z`.

The source stage uses `alpine/git:2.49.1@sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26`. HTTPS fetching runs inside this complete Alpine environment. Copying only Git and its local-command libraries to Ubuntu is insufficient for HTTPS; the original recipe failed with missing curl symbols and has been corrected.

The stage fetches the exact Base and its preceding history, removes the remote and fetch metadata, and checks HEAD, tree, refs and unreachable objects before copying the checkout. It is a real historical checkout, not a synthetic one-commit archive. The runtime retains local Git functionality for normal investigation and patching. Runtime networking is disabled.

The runtime donor remains `vllm/vllm-openai:v0.19.0@sha256:d9a5c1c1614c959fde8d2a4d68449db184572528a6055afdd0caf1e66fb51504` with PyTorch `2.10.0+cu129`. All eight native extensions and `_version.py` come from this single donor and are checked against `native.sha256`. The merge uses Python/PyTorch operations; exact Base provenance for unrelated donor-native operators is not claimed. The installed donor package remains subject to the actual-image visibility/cutoff audit; the checkout's HEAD alone is not an image-wide audit.

`test-tools.txt` fixes the agent's pytest tools and their wheel SHA-256 values. The small pure-Python wheels in `environment/test-wheels/` install offline with `--no-deps --require-hashes`; build and scoring never download them. General test tools need not predate the problem cutoff, but remain pinned. Runtime semantic dependencies continue to come from the immutable donor image.

The agent is non-root and owns `/workspace/repo`. No task solution, hidden test, controls, or task-specific reproduction helpers are in the environment build context. The checkpoint C extension is compiled only from the verifier's read-only harness mount during grading, using the image's compiler and Python headers; it uses CPython's native `_hashlib` HMAC implementation and needs no OpenSSL development package.

See `environment/image-manifest.json` and `validation/e2e-evidence.json` for the retained image identity and actual commands/results for this revision. Historical validation is not evidence for a changed image.
