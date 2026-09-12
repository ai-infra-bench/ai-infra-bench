# Docker validation, 2026-09-13

The final local image is `ai-infra-bench/vllm-dp-multi-port-supervisor:hardening-20260913-final`, image ID `sha256:d11035d323cd8044e4a1aea97d0c3f7a03ae7865cadc84893bd045686da65eed`. It has not been pushed. A local image ID is not a registry manifest digest; `repo_digests` records only actual Docker inspection results.

The default Dockerfile retains the original public, pinned vLLM donor and source checkout recipe. This host could not complete outbound APT requests, and anonymous GHCR resolution returned HTTP 401. The successful build used the optional prepared-base path and the already cached CI image, whose resolved ID is `sha256:10d9683beb7ddc09b89e64d745348aaea13f9a201d4f7ddb95ab038be01b3f9d`. No successful fresh network rebuild is claimed.

```sh
DOCKER_BUILDKIT=0 docker build --build-arg PREPARED_BASE=1 --build-arg BASE_IMAGE=ghcr.io/ai-infra-bench/ai-infra-bench-task-envs:vllm-dp-multi-port-supervisor-fe622c4308debd62dcf3c8b6d7faa46f6ee570aa97a9f1777c3ef3c9ea376248 -t ai-infra-bench/vllm-dp-multi-port-supervisor:hardening-20260913-final environment
```

The build checks Base, source tree, clean checkout, absent remotes and task artifacts. The separate smoke test runs as `agent`, without network, and checks full reachable history, no unreachable/future Oracle objects, writable checkout, and source/native imports under `/workspace/repo`. See `evidence/environment-smoke-final.log` and `environment/image-manifest.json`.

Direct verifier cases use isolated network namespaces, 4 CPUs and 16 GiB each, with at most three cases concurrently. The task needs no GPU. Harbor uses the same image and the task's ordinary grading entrypoint. Commands and results are recorded in `e2e-evidence.json`; host scratch logs are under `/data/pr54-hardening-20260913`.
