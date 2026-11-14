# syntax=docker/dockerfile:1
# Template inputs below are replaced from task.toml by generate.py. Generated
# task Dockerfiles are self-contained and differ only in their frozen inputs.

ARG VLLM_BASE_SHA=d6f0b7a4166b325b4dda6512e2e06dcb581923ba
ARG VLLM_DEPENDENCY_CUTOFF=2026-10-15T16:08:14Z
ARG VLLM_CACHE_NAMESPACE=d6f0b7a4166b325b4dda6512e2e06dcb581923ba-8b4a915c83ed5f09
ARG VLLM_REPO=https://github.com/vllm-project/vllm.git

######################### PINNED SOURCE #########################
FROM alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc AS source
ARG VLLM_BASE_SHA
ARG VLLM_REPO
RUN test -n "$VLLM_BASE_SHA" \
 && apk add --no-cache ca-certificates git \
 && mkdir -p /src/vllm \
 && git -C /src/vllm init -q \
 && git -C /src/vllm config core.logAllRefUpdates false \
 && git -C /src/vllm remote add origin "$VLLM_REPO" \
 && git -C /src/vllm fetch --no-tags origin "$VLLM_BASE_SHA" \
 && git -C /src/vllm checkout -q -b main "$VLLM_BASE_SHA" \
 && test "$(git -C /src/vllm rev-parse HEAD)" = "$VLLM_BASE_SHA" \
 && git -C /src/vllm remote remove origin \
 && rm -rf /src/vllm/.git/logs \
 && rm -f /src/vllm/.git/FETCH_HEAD /src/vllm/.git/ORIG_HEAD \
 && test "$(git -C /src/vllm branch --show-current)" = main \
 && test "$(git -C /src/vllm rev-list --all --count)" -gt 1 \
 && test ! -e /src/vllm/.git/shallow \
 && test -z "$(git -C /src/vllm remote)" \
 && test -z "$(git -C /src/vllm for-each-ref --format='%(refname)' refs/remotes refs/tags)" \
 && test ! -e /src/vllm/.git/logs \
 && test ! -e /src/vllm/.git/FETCH_HEAD \
 && test ! -e /src/vllm/.git/ORIG_HEAD \
 && test -z "$(git -C /src/vllm fsck --full --no-reflogs --unreachable --no-progress 2>/dev/null)" \
 && test -z "$(git -C /src/vllm status --porcelain)"

######################### ALL-IN-ONE CPU ENVIRONMENT #########################
FROM python:3.12-slim-trixie@sha256:09f7da3bc104798d0afb40bc08d23ab2da20a76130cec1f2ef170848f5d85217
ARG TARGETARCH
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=500 \
    CARGO_HOME=/root/.cargo \
    RUSTUP_HOME=/root/.rustup \
    PATH=/root/.cargo/bin:$PATH \
    CARGO_BUILD_JOBS=4 \
    CARGO_INCREMENTAL=0 \
    CC=/usr/bin/gcc \
    CXX=/usr/bin/g++ \
    CCACHE_DIR=/root/.cache/ccache \
    CMAKE_CXX_COMPILER_LAUNCHER=ccache \
    MAX_JOBS=8

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bash build-essential ca-certificates ccache curl ffmpeg \
      git jq libgl1 libnuma-dev libsm6 libssl-dev libtcmalloc-minimal4 \
      libxext6 lsof make pkg-config sudo unzip wget xz-utils \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.11.28

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
      | sh -s -- -y --profile minimal --default-toolchain none \
 && rustup toolchain install 1.95 --profile minimal --component rustfmt,clippy \
 && rustup default 1.95

RUN case "$TARGETARCH" in \
      amd64) nextest_platform=linux ;; \
      arm64) nextest_platform=linux-arm ;; \
      *) echo "Unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl --http1.1 -L --retry 10 --retry-all-errors --connect-timeout 30 --max-time 600 \
      --proto '=https' --tlsv1.2 -sSf \
      "https://get.nexte.st/0.9.143/$nextest_platform" \
      -o /tmp/cargo-nextest.tar.gz \
 && tar -xzf /tmp/cargo-nextest.tar.gz -C /root/.cargo/bin \
 && rm -f /tmp/cargo-nextest.tar.gz \
 && cargo nextest --version

ARG VLLM_DEPENDENCY_CUTOFF
# Exact task dependency lock (sha256:8b4a915c83ed5f0948705004d49fedd933925bded4912106e56fdfd385003395) is embedded so this
# Dockerfile remains independently buildable with an empty context.
RUN --mount=type=cache,id=vllm-uv-downloads-v3,target=/root/.cache/uv,sharing=locked <<'VLLM_INSTALL_EOF'
set -eu
cat > /tmp/vllm-requirements.lock <<'VLLM_REQUIREMENTS_EOF'
# Generated with uv 0.11.28 from the pinned base requirements and task
# extras for CPython 3.12 on x86_64 manylinux_2_28. Packages newer than
# 2026-10-15T16:08:14Z were excluded during resolution.
agent-detector==2.0.0
    # via fastapi-cloud-cli
aiohappyeyeballs==2.7.1
    # via aiohttp
aiohttp==3.14.5
    # via -r requirements/common.txt
aiosignal==1.4.0
    # via aiohttp
annotated-doc==0.0.5
    # via
    #   fastapi
    #   typer
annotated-types==0.8.0
    # via pydantic
anthropic==1.14.0
    # via -r requirements/common.txt
anyio==4.15.1
    # via
    #   anthropic
    #   httpx
    #   httpx2
    #   mcp
    #   openai
    #   sse-starlette
    #   starlette
    #   watchfiles
apache-tvm-ffi==0.1.14.post1
    # via xgrammar
astor==0.8.1
    # via depyf
attrs==26.1.0
    # via
    #   aiohttp
    #   jsonschema
    #   referencing
blake3==1.0.11
    # via -r requirements/common.txt
cachetools==7.2.1
    # via -r requirements/common.txt
cbor2==6.1.5
    # via -r requirements/common.txt
certifi==2026.7.22
    # via
    #   httpcore
    #   httpx
    #   requests
    #   sentry-sdk
cffi==2.1.1
    # via cryptography
charset-normalizer==3.5.2
    # via requests
click==8.5.0
    # via
    #   huggingface-hub
    #   rich-toolkit
    #   uvicorn
cloudpickle==3.1.2
    # via -r requirements/common.txt
cmake==4.4.4
    # via -r requirements/build/cpu.txt
cohere==7.0.8
    # via -r extras.in
compressed-tensors==0.17.0
    # via -r requirements/common.txt
cryptography==50.0.2
    # via pyjwt
depyf==0.20.0
    # via -r requirements/common.txt
detect-installer==0.2.1
    # via fastapi-cloud-cli
dill==0.4.1
    # via depyf
dnspython==2.9.0
    # via email-validator
docstring-parser==0.18.0
    # via anthropic
einops==0.8.2
    # via -r requirements/common.txt
email-validator==2.3.0
    # via
    #   fastapi
    #   pydantic
fastapi==0.136.3
    # via
    #   -r requirements/common.txt
    #   model-hosting-container-standards
fastapi-cli==0.0.32
    # via fastapi
fastapi-cloud-cli==0.26.0
    # via fastapi-cli
fastar==0.12.0
    # via
    #   fastapi
    #   fastapi-cloud-cli
fastavro==1.13.1
    # via cohere
filelock==4.2.0
    # via
    #   -r requirements/common.txt
    #   huggingface-hub
    #   torch
frozenlist==1.8.0
    # via
    #   aiohttp
    #   aiosignal
fsspec==2026.9.0
    # via
    #   huggingface-hub
    #   torch
googleapis-common-protos==1.75.5
    # via
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
grpcio==1.84.0
    # via opentelemetry-exporter-otlp-proto-grpc
h11==0.16.0
    # via
    #   httpcore
    #   httpcore2
    #   uvicorn
hf-xet==1.7.0
    # via huggingface-hub
httpcore==1.0.9
    # via httpx
httpcore2==2.13.1
    # via httpx2
httptools==0.9.0
    # via uvicorn
httpx==0.28.1
    # via
    #   cohere
    #   fastapi
    #   fastapi-cloud-cli
    #   model-hosting-container-standards
httpx2==2.13.1
    # via
    #   anthropic
    #   huggingface-hub
    #   mcp
    #   openai
huggingface-hub==2.2.0
    # via
    #   -r requirements/common.txt
    #   tokenizers
    #   transformers
idna==3.20
    # via
    #   anyio
    #   email-validator
    #   httpx
    #   httpx2
    #   requests
    #   yarl
ijson==3.6.0
    # via -r requirements/common.txt
iniconfig==2.3.1
    # via pytest
intel-cmplr-lib-ur==2024.2.1
    # via intel-openmp
intel-openmp==2024.2.1
    # via -r requirements/cpu.txt
interegular==0.3.3
    # via lm-format-enforcer
jinja2==3.1.6
    # via
    #   -r requirements/build/cpu.txt
    #   fastapi
    #   torch
jiter==0.17.0
    # via
    #   anthropic
    #   openai
jmespath==1.1.0
    # via model-hosting-container-standards
jsonschema==4.26.0
    # via
    #   -r requirements/common.txt
    #   mcp
    #   mistral-common
jsonschema-specifications==2025.9.1
    # via jsonschema
lark==1.2.2
    # via -r requirements/common.txt
llguidance==1.7.6
    # via -r requirements/common.txt
llvmlite==0.47.0
    # via numba
lm-format-enforcer==0.11.3
    # via -r requirements/common.txt
loguru==0.7.3
    # via compressed-tensors
markdown-it-py==4.2.0
    # via rich
markupsafe==3.0.4
    # via jinja2
mcp==2.3.0
    # via -r requirements/common.txt
mcp-types==2.3.0
    # via mcp
mdurl==0.1.2
    # via markdown-it-py
mistral-common==1.12.0
    # via -r requirements/common.txt
model-hosting-container-standards==0.1.16
    # via -r requirements/common.txt
mpmath==1.3.0
    # via sympy
msgspec==0.22.0
    # via -r requirements/common.txt
multidict==7.1.0
    # via
    #   aiohttp
    #   yarl
networkx==3.7
    # via torch
ninja==1.13.2
    # via
    #   -r requirements/build/cpu.txt
    #   -r requirements/common.txt
numba==0.65.0
    # via -r requirements/cpu.txt
numpy==2.3.5
    # via
    #   -r requirements/common.txt
    #   mistral-common
    #   numba
    #   opencv-python-headless
    #   torchvision
    #   transformers
    #   xgrammar
openai==3.31.0
    # via -r requirements/common.txt
opencv-python-headless==5.0.0.93
    # via
    #   -r requirements/common.txt
    #   mistral-common
opentelemetry-api==1.45.1
    # via
    #   -r requirements/common.txt
    #   anthropic
    #   mcp
    #   opentelemetry-exporter-http-transport
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
    #   opentelemetry-sdk
    #   opentelemetry-semantic-conventions
opentelemetry-exporter-http-transport==0.66b1
    # via opentelemetry-exporter-otlp-proto-http
opentelemetry-exporter-otlp==1.45.1
    # via -r requirements/common.txt
opentelemetry-exporter-otlp-common==0.66b1
    # via
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
opentelemetry-exporter-otlp-proto-common==1.45.1
    # via
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
opentelemetry-exporter-otlp-proto-grpc==1.45.1
    # via opentelemetry-exporter-otlp
opentelemetry-exporter-otlp-proto-http==1.45.1
    # via opentelemetry-exporter-otlp
opentelemetry-proto==1.45.1
    # via
    #   opentelemetry-exporter-otlp-proto-common
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
opentelemetry-sdk==1.45.1
    # via
    #   -r requirements/common.txt
    #   opentelemetry-exporter-otlp-common
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
    #   opentelemetry-semantic-conventions-ai
opentelemetry-semantic-conventions==0.66b1
    # via
    #   opentelemetry-sdk
    #   opentelemetry-semantic-conventions-ai
opentelemetry-semantic-conventions-ai==0.5.1
    # via -r requirements/common.txt
oss-harmony==0.0.11
    # via -r requirements/common.txt
outlines-core==0.2.14
    # via -r requirements/common.txt
packaging==26.3
    # via
    #   -r requirements/build/cpu.txt
    #   huggingface-hub
    #   lm-format-enforcer
    #   pytest
    #   setuptools-scm
    #   transformers
    #   vcs-versioning
    #   wheel
partial-json-parser==0.2.1.1.post7
    # via -r requirements/common.txt
pillow==12.3.0
    # via
    #   -r requirements/common.txt
    #   mistral-common
    #   torchvision
pluggy==1.7.0
    # via pytest
prometheus-client==0.26.0
    # via
    #   -r requirements/common.txt
    #   prometheus-fastapi-instrumentator
prometheus-fastapi-instrumentator==8.1.0
    # via -r requirements/common.txt
propcache==0.5.4
    # via
    #   aiohttp
    #   yarl
protobuf==7.36.2
    # via
    #   -r requirements/common.txt
    #   googleapis-common-protos
    #   opentelemetry-proto
psutil==7.2.2
    # via -r requirements/common.txt
py-cpuinfo==9.0.0
    # via -r requirements/common.txt
pybase64==1.5.1
    # via -r requirements/common.txt
pycountry==26.2.16
    # via pydantic-extra-types
pycparser==3.11
    # via cffi
pydantic==2.14.1
    # via
    #   -r requirements/common.txt
    #   anthropic
    #   cohere
    #   compressed-tensors
    #   fastapi
    #   fastapi-cloud-cli
    #   lm-format-enforcer
    #   mcp
    #   mcp-types
    #   mistral-common
    #   model-hosting-container-standards
    #   openai
    #   oss-harmony
    #   pydantic-extra-types
    #   pydantic-settings
    #   xgrammar
pydantic-core==2.50.1
    # via
    #   cohere
    #   pydantic
pydantic-extra-types==2.11.1
    # via
    #   fastapi
    #   mistral-common
pydantic-settings==2.16.0
    # via fastapi
pygments==2.21.0
    # via
    #   pytest
    #   rich
pyjwt==2.15.1
    # via mcp
pytest==9.1.1
    # via
    #   -r extras.in
    #   pytest-asyncio
pytest-asyncio==1.4.0
    # via -r extras.in
python-dotenv==1.2.4
    # via
    #   pydantic-settings
    #   uvicorn
python-json-logger==4.2.0
    # via -r requirements/common.txt
python-multipart==0.0.32
    # via
    #   fastapi
    #   mcp
pyyaml==6.0.3
    # via
    #   -r requirements/common.txt
    #   huggingface-hub
    #   lm-format-enforcer
    #   transformers
    #   uvicorn
pyzmq==27.2.0
    # via -r requirements/common.txt
referencing==0.37.0
    # via
    #   jsonschema
    #   jsonschema-specifications
regex==2026.9.29
    # via
    #   -r requirements/build/cpu.txt
    #   -r requirements/common.txt
    #   tiktoken
    #   transformers
requests==2.34.2
    # via
    #   -r requirements/common.txt
    #   cohere
    #   mistral-common
    #   opentelemetry-exporter-http-transport
    #   opentelemetry-exporter-otlp-proto-http
    #   tiktoken
rich==15.0.0
    # via
    #   rich-toolkit
    #   typer
rich-toolkit==0.20.6
    # via
    #   fastapi-cli
    #   fastapi-cloud-cli
rignore==0.8.1
    # via fastapi-cloud-cli
rpds-py==2026.9.1
    # via
    #   jsonschema
    #   referencing
safetensors==0.8.0
    # via
    #   -r requirements/common.txt
    #   transformers
semantic-version==2.10.0
    # via setuptools-rust
sentencepiece==0.2.2
    # via -r requirements/common.txt
sentry-sdk==2.72.0
    # via fastapi-cloud-cli
setproctitle==1.3.8
    # via -r requirements/common.txt
setuptools==78.1.1
    # via
    #   -r requirements/build/cpu.txt
    #   -r requirements/common.txt
    #   -r requirements/cpu.txt
    #   model-hosting-container-standards
    #   setuptools-rust
    #   setuptools-scm
    #   torch
setuptools-rust==1.13.0
    # via -r requirements/build/cpu.txt
setuptools-scm==10.3.4
    # via -r requirements/build/cpu.txt
shellingham==1.5.4
    # via typer
six==1.17.0
    # via -r requirements/common.txt
sniffio==1.3.1
    # via
    #   anthropic
    #   openai
sse-starlette==3.5.0
    # via mcp
starlette==1.8.0
    # via
    #   -r requirements/common.txt
    #   fastapi
    #   mcp
    #   model-hosting-container-standards
    #   prometheus-fastapi-instrumentator
    #   sse-starlette
supervisor==4.3.0
    # via model-hosting-container-standards
sympy==1.14.0
    # via torch
tiktoken==0.14.0
    # via
    #   -r requirements/common.txt
    #   mistral-common
tokenizers==0.23.3
    # via
    #   -r requirements/common.txt
    #   cohere
    #   transformers
torch==2.14.0+cpu
    # via
    #   -r requirements/build/cpu.txt
    #   -r requirements/cpu.txt
    #   compressed-tensors
    #   torchvision
    #   xgrammar
torchaudio==2.11.0+cpu
    # via -r requirements/cpu.txt
torchcodec==0.17.0+cpu
    # via -r requirements/cpu.txt
torchvision==0.29.1+cpu
    # via -r requirements/cpu.txt
tqdm==4.70.1
    # via
    #   -r requirements/common.txt
    #   huggingface-hub
    #   transformers
transformers==5.19.0
    # via
    #   -r requirements/common.txt
    #   compressed-tensors
    #   xgrammar
triton @ https://github.com/triton-lang/triton-cpu/releases/download/v3.8.0/triton-3.8.0+cpu-cp312-abi3-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl
    # via
    #   -r requirements/cpu.txt
    #   xgrammar
truststore==0.10.5
    # via
    #   httpcore2
    #   httpx2
typer==0.27.3
    # via
    #   fastapi-cli
    #   fastapi-cloud-cli
    #   transformers
types-requests==2.33.0.20261006
    # via cohere
typing-extensions==4.16.0
    # via
    #   -r requirements/common.txt
    #   aiohttp
    #   aiosignal
    #   anthropic
    #   anyio
    #   apache-tvm-ffi
    #   cohere
    #   fastapi
    #   grpcio
    #   httpx2
    #   huggingface-hub
    #   mcp
    #   mcp-types
    #   mistral-common
    #   openai
    #   opentelemetry-api
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
    #   opentelemetry-sdk
    #   opentelemetry-semantic-conventions
    #   pydantic
    #   pydantic-core
    #   pydantic-extra-types
    #   pydantic-settings
    #   pytest-asyncio
    #   referencing
    #   rich-toolkit
    #   starlette
    #   torch
    #   typing-inspection
    #   xgrammar
typing-inspection==0.4.4
    # via
    #   fastapi
    #   mcp
    #   pydantic
    #   pydantic-settings
urllib3==2.8.0
    # via
    #   requests
    #   sentry-sdk
    #   types-requests
uvicorn==0.54.0
    # via
    #   fastapi
    #   fastapi-cli
    #   fastapi-cloud-cli
    #   mcp
uvloop==0.23.0
    # via uvicorn
vcs-versioning==2.6.0
    # via setuptools-scm
watchfiles==1.3.0
    # via
    #   -r requirements/common.txt
    #   uvicorn
websockets==17.2
    # via uvicorn
wheel==0.48.0
    # via -r requirements/build/cpu.txt
xgrammar==0.2.8
    # via -r requirements/common.txt
yarl==1.25.1
    # via aiohttp
VLLM_REQUIREMENTS_EOF
uv pip install --system --index-strategy first-index \
  --torch-backend cpu -r /tmp/vllm-requirements.lock
rm -f /tmp/vllm-requirements.lock
VLLM_INSTALL_EOF

COPY --from=source /src/vllm/ /workspace/vllm/
WORKDIR /workspace/vllm
ARG VLLM_BASE_SHA
ARG VLLM_CACHE_NAMESPACE
ENV SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0+g${VLLM_BASE_SHA} \
    SETUPTOOLS_SCM_PRETEND_VERSION_FOR_VLLM=0.0.0+g${VLLM_BASE_SHA}

RUN --mount=type=cache,id=vllm-uv-downloads-v3,target=/root/.cache/uv,sharing=locked \
    --mount=type=cache,id=vllm-ccache-${VLLM_CACHE_NAMESPACE},target=/root/.cache/ccache,sharing=locked \
    --mount=type=cache,id=vllm-fetchcontent-${VLLM_CACHE_NAMESPACE},target=/workspace/vllm/.deps,sharing=locked \
    python -c "import importlib.metadata as m; assert not any((d.metadata.get('Name') or '').lower() == 'vllm' for d in m.distributions())" \
 && \
    VLLM_TARGET_DEVICE=cpu \
      uv pip install --system --no-build-isolation --no-deps -e . --torch-backend cpu \
 && if [ -f tests/vllm_test_utils/setup.py ]; then \
      uv pip install --system --no-deps -e tests/vllm_test_utils; \
    fi \
 && python -c "from pathlib import Path; import vllm; assert Path(vllm.__file__).resolve().is_relative_to(Path('/workspace/vllm'))"

RUN if [ -f rust/Cargo.toml ]; then \
      if [ -x tools/install_protoc.sh ]; then tools/install_protoc.sh; fi; \
      cargo fetch --manifest-path rust/Cargo.toml --locked; \
    fi

# Keep .git and every commit reachable from the pinned base on local main.
# Remove fetch-only metadata and reject any hidden, unreachable Git objects.
RUN find . -type d -name __pycache__ -prune -exec rm -rf {} + \
 && find . -type d \( -name '*.egg-info' -o -name '.pytest_cache' \) -prune -exec rm -rf {} + \
 && test "$(git rev-parse HEAD)" = "$VLLM_BASE_SHA" \
 && test "$(git branch --show-current)" = main \
 && test "$(git rev-list --all --count)" -gt 1 \
 && test ! -e .git/shallow \
 && test -z "$(git remote)" \
 && test -z "$(git for-each-ref --format='%(refname)' refs/remotes refs/tags)" \
 && test ! -e .git/logs \
 && test ! -e .git/FETCH_HEAD \
 && test ! -e .git/ORIG_HEAD \
 && test -z "$(git fsck --full --no-reflogs --unreachable --no-progress 2>/dev/null)" \
 && test -z "$(git status --porcelain)"

LABEL ai.infra.bench.environment-template=vllm-harbor-all-in-one \
      ai.infra.bench.base-commit=$VLLM_BASE_SHA \
      ai.infra.bench.dependency-cutoff=$VLLM_DEPENDENCY_CUTOFF \
      ai.infra.bench.cache-namespace=$VLLM_CACHE_NAMESPACE
ENTRYPOINT []
CMD ["sleep", "infinity"]
