# Environment lock

This environment packages the pre-fix source state for
`vllm__pr__34183` while retaining a usable CPU runtime.

## Candidate source

- Upstream repository: `https://github.com/vllm-project/vllm.git`
- Base commit: `e94ec597334d9a3e9b0d04bc17152e2747c83d51`
- Source tree: `bfdf97989c2997f550a44ebc42ad8aa5582d67a7`
- Commit date / dependency cutoff: `2026-02-10T01:18:42Z`
- Acquisition: an exact-commit fetch retaining the 2,000 ancestors reachable
  from Base; tags, remotes, reflogs, fetch metadata, unreachable objects, and
  post-Base objects are removed.
- Runtime Git state: branch `main` at the real Base commit with a clean tree.

The bounded history is intentional. A complete unshallow fetch was unreliable
on the build host, while a depth-one or synthetic history would make ordinary
Agent archaeology much less useful. The retained boundary contains no future
object and is recorded here rather than represented as full upstream history.

## Dependency donor and answer isolation

- Donor image: `vllm/vllm-openai-cpu:v0.17.1-x86_64`
- Linux/amd64 digest:
  `sha256:d19978a2d4bb2289c740a6c89d4cc15fbcf4d20d916f1e268168b8bbad3b776b`
- Python: 3.12.13
- PyTorch: 2.10.0+cpu
- Runtime accelerator: CPU

The donor is used only in a build stage. Its root filesystem is copied into a
new `FROM scratch` stage after excluding its installed vLLM Python package,
package metadata, workspaces, and caches. Only native vLLM shared objects and
`_version.py` are staged into the exact Base checkout. Therefore the final
image does not inherit a layer containing the donor's already-fixed
`vllm/v1/request.py`.

The Dockerfile asserts the exact Base commit and source tree, rejects hidden
Git objects and network references, and rejects any second installed copy of
the target source. Runtime imports resolve to `/workspace/repo/vllm`.

## Build and runtime boundary

Network access is required only while pulling the digest-pinned donor and
fetching the exact source history. Agent and verifier phases run with no
network. The image contains no task-specific reproducer, verifier, Oracle, or
validation artifact; those are mounted only into the separate verifier phase.
