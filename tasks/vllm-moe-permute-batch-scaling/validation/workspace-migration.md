# Workspace migration

The task uses `/workspace/vllm` throughout instruction, environment configuration, Dockerfile, solution, native build/staging and curator tools. The Python package and native extension live under `/workspace/vllm/vllm`.

Version 1.3.4 was rebuilt from the current Dockerfile and passed the image audit, complete A100 control matrix and final Harbor Oracle trial. `../environment/image-manifest.json` and `../task.toml` identify the rebuilt image. Dependency records match the build, including the pinned Alpine Git runtime and source-path .pth installation. See [tests-hardening.md](tests-hardening.md) and [the 1.3.4 summary](evidence/tests-1.3.4/summary.json) for measured outcomes and scope.

Historical 1.3.3 Docker and DeepSeek runs used a locally migrated `/app` image. Their recorded identities and rewards remain unchanged; those older runs are separate from the final 1.3.4 image acceptance. No image was pushed to a registry.
