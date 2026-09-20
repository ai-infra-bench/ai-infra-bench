# Workspace image build — 1.3.0

A100 build used environment/Dockerfile.workspace at commit 86e7dae, with the
immutable existing 1.2.9 Base-only image as parent. Build ran offline with
DOCKER_BUILDKIT=0 docker build --network none -f environment/Dockerfile.workspace
-t vllm-encoder-local:workspace-1.3.0 environment. No dependencies or target
source were updated. The full from-source recipe environment/Dockerfile is
also updated to the new location.

Actual image identity, size, recipe hashes and source checks are recorded in
environment/image-manifest.json. Build log is in
[archived build log](https://github.com/ouycc/ai-infra-bench/tree/b596d2e67de1e3191ef1b6a587d6b98c015ed48f/tasks/vllm-multimodal-encoder-cache-accounting/validation/evidence/workspace-1.3.0/build.log). Runtime validation used pulled
commit 08e68b6; final documentation/evidence changes do not alter test inputs.
The previous build record is preserved under validation/history.
