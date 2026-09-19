# Workspace migration

The task uses `/workspace/vllm` throughout instruction, environment configuration, Dockerfile, solution, native build/staging and curator tools. The Python package and native extension live under `/workspace/vllm/vllm`.

Version 1.3.5 reuses the CI image built after the incremental-history fetch change. `../environment/image-manifest.json` and `../task.toml` identify those immutable bytes and the current Dockerfile hash. Its verifier results are recorded in [e2e-evidence.json](e2e-evidence.json). Dependency records retain the pinned Alpine Git runtime and source-path .pth installation. The earlier [1.3.4 summary](evidence/tests-1.3.4/summary.json) refers to its original image and does not certify the expanded verifier.

Historical 1.3.3 Docker and DeepSeek runs used a locally migrated `/app` image. Their recorded identities and rewards remain unchanged; those older runs are separate from the final 1.3.4 image acceptance. No image was pushed to a registry.
