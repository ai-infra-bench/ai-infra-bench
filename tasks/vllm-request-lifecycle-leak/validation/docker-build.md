# Local CPU build

Built the task Dockerfile with the pinned donor and exact Base/tree. The local build used `--build-arg VLLM_REPO=git://127.0.0.1:19455/source-fetch` to transport the already audited complete Base history after public GitHub fetch failures. The argument changes only the Git transport; source hashes and isolation assertions are unchanged. The Dockerfile defaults to the public upstream URL and has no dependency on reviewer fixtures or host files at runtime.

```sh
DOCKER_BUILDKIT=0 docker build --network host -t ai-infra-bench/vllm-request-lifecycle-leak:base-e94ec597334d-avx2 tasks/vllm-request-lifecycle-leak/environment
```

The real AVX2 extension replaces the incompatible default _C binary. No candidate Python module is stubbed or removed. A local minimal 0.0.0+cpu distribution identifier enables CPU platform discovery without exposing later donor source. Image identity is recorded in environment/image-manifest.json. The image is built locally, not pushed.
