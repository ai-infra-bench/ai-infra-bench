# syntax=docker/dockerfile:1
# Task-scoped expansion of the vllm-harbor-all-in-one CPU environment.
# Includes required Rust packaging, offline Cargo sources and an embedded lock.
# Builds independently from an empty context; no task artifacts enter the image.

ARG VLLM_BASE_SHA=e473e9036f979d546830aece9855027049faf0ba
ARG VLLM_DEPENDENCY_CUTOFF=2026-09-05T07:29:49Z
ARG VLLM_CACHE_NAMESPACE=e473e9036f979d546830aece9855027049faf0ba-7aaffdcbe61f75a1
ARG VLLM_REPO=https://github.com/vllm-project/vllm.git

######################### PINNED SYSTEM BASE #########################
FROM python:3.12.11-slim-trixie@sha256:47ae396f09c1303b8653019811a8498470603d7ffefc29cb07c88f1f8cb3d19f AS python-base
ARG VLLM_DEPENDENCY_CUTOFF
RUN snapshot_timestamp="$(printf '%s' "$VLLM_DEPENDENCY_CUTOFF" | tr -d ':-')" \
 && printf '%s\n' \
      'Types: deb' \
      "URIs: https://snapshot.debian.org/archive/debian/${snapshot_timestamp}/" \
      'Suites: trixie' \
      'Components: main' \
      'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg' \
      'Check-Valid-Until: no' \
      '' \
      'Types: deb' \
      "URIs: https://snapshot.debian.org/archive/debian-security/${snapshot_timestamp}/" \
      'Suites: trixie-security' \
      'Components: main' \
      'Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg' \
      'Check-Valid-Until: no' \
      > /etc/apt/sources.list.d/debian.sources

######################### PINNED SOURCE #########################
FROM python-base AS source
ARG VLLM_BASE_SHA
ARG VLLM_REPO
RUN test -n "$VLLM_BASE_SHA" \
 && apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git \
 && rm -rf /var/lib/apt/lists/* \
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
FROM python-base
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

ARG RUSTUP_VERSION=1.29.0
ARG RUST_TOOLCHAIN=1.95
RUN case "$TARGETARCH" in \
      amd64) rust_target=x86_64-unknown-linux-gnu; rustup_sha=4acc9acc76d5079515b46346a485974457b5a79893cfb01112423c89aeb5aa10 ;; \
      arm64) rust_target=aarch64-unknown-linux-gnu; rustup_sha=9732d6c5e2a098d3521fca8145d826ae0aaa067ef2385ead08e6feac88fa5792 ;; \
      *) echo "Unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl --http1.1 -L --retry 10 --retry-all-errors --connect-timeout 30 --max-time 600 \
      --proto '=https' --tlsv1.2 -sSf \
      "https://static.rust-lang.org/rustup/archive/${RUSTUP_VERSION}/${rust_target}/rustup-init" \
      -o /tmp/rustup-init \
 && printf '%s  %s\n' "$rustup_sha" /tmp/rustup-init | sha256sum -c - \
 && chmod 0755 /tmp/rustup-init \
 && /tmp/rustup-init -y --profile minimal --default-toolchain none \
 && rm -f /tmp/rustup-init \
 && rustup toolchain install "$RUST_TOOLCHAIN" --profile minimal --component rustfmt,clippy \
 && rustup default "$RUST_TOOLCHAIN"

ARG CARGO_NEXTEST_VERSION=0.9.133
RUN case "$TARGETARCH" in \
      amd64) nextest_target=x86_64-unknown-linux-gnu; nextest_sha=a9f992321e8759818400d93abb9477b4b11422d18d216e8d208505bd73454103 ;; \
      arm64) nextest_target=aarch64-unknown-linux-gnu; nextest_sha=8e4d241c78f9cbf5ca8597b13004f0441c18af484ea105b8f83b44a716c82d3d ;; \
      *) echo "Unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl --http1.1 -L --retry 10 --retry-all-errors --connect-timeout 30 --max-time 600 \
      --proto '=https' --tlsv1.2 -sSf \
      "https://github.com/nextest-rs/nextest/releases/download/cargo-nextest-${CARGO_NEXTEST_VERSION}/cargo-nextest-${CARGO_NEXTEST_VERSION}-${nextest_target}.tar.gz" \
      -o /tmp/cargo-nextest.tar.gz \
 && printf '%s  %s\n' "$nextest_sha" /tmp/cargo-nextest.tar.gz | sha256sum -c - \
 && tar -xzf /tmp/cargo-nextest.tar.gz -C /root/.cargo/bin \
 && rm -f /tmp/cargo-nextest.tar.gz \
 && cargo nextest --version

ARG PROTOC_VERSION=34.2
RUN case "$TARGETARCH" in \
      amd64) protoc_arch=x86_64; protoc_sha=b52e803fad2f63232f75351c0ff735e891f40262de791bade78a3636831a522a ;; \
      arm64) protoc_arch=aarch_64; protoc_sha=63d92a87482d4eaa41a72f9de6ea7f476e1fb4c722700fa0b981cc204f7d3a14 ;; \
      *) echo "Unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac \
 && curl --http1.1 -L --retry 10 --retry-all-errors --connect-timeout 30 --max-time 600 \
      --proto '=https' --tlsv1.2 -sSf \
      "https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOC_VERSION}/protoc-${PROTOC_VERSION}-linux-${protoc_arch}.zip" \
      -o /tmp/protoc.zip \
 && printf '%s  %s\n' "$protoc_sha" /tmp/protoc.zip | sha256sum -c - \
 && unzip -q -o /tmp/protoc.zip -d /usr/local \
 && rm -f /tmp/protoc.zip \
 && protoc --version

ARG VLLM_DEPENDENCY_CUTOFF
# Exact task dependency lock (sha256:7aaffdcbe61f75a1a0935cb9a22f4b7fa0dceb4cc9c688ecada40d691f71e532) is embedded so this
# Dockerfile remains independently buildable with an empty context.
RUN --mount=type=cache,id=vllm-uv-downloads-v3,target=/root/.cache/uv,sharing=locked <<'VLLM_INSTALL_EOF'
set -eu
cat > /tmp/vllm-requirements.lock <<'VLLM_REQUIREMENTS_EOF'
# Generated with uv 0.11.28 from the pinned base requirements and task
# extras for CPython 3.12 on x86_64 manylinux_2_28. Packages newer than
# 2026-09-05T07:29:49Z were excluded during resolution.
agent-detector==2.0.0
    # via fastapi-cloud-cli
aiohappyeyeballs==2.7.1
    # via aiohttp
aiohttp==3.14.3
    # via -r requirements/common.txt
aiosignal==1.4.0
    # via aiohttp
annotated-doc==0.0.5
    # via
    #   fastapi
    #   typer
annotated-types==0.8.0
    # via pydantic
anthropic==1.4.0
    # via -r requirements/common.txt
anyio==4.15.0
    # via
    #   anthropic
    #   httpx
    #   httpx2
    #   mcp
    #   openai
    #   sse-starlette
    #   starlette
    #   watchfiles
apache-tvm-ffi==0.1.13.post3
    # via xgrammar
astor==0.8.1
    # via depyf
attrs==26.1.0
    # via
    #   aiohttp
    #   jsonschema
    #   referencing
blake3==1.0.9
    # via -r requirements/common.txt
cachetools==7.1.8
    # via -r requirements/common.txt
cbor2==6.1.4
    # via -r requirements/common.txt
certifi==2026.7.22
    # via
    #   httpcore
    #   httpx
    #   requests
    #   sentry-sdk
cffi==2.1.1
    # via cryptography
charset-normalizer==3.5.1
    # via requests
click==8.5.0
    # via
    #   huggingface-hub
    #   rich-toolkit
    #   uvicorn
cloudpickle==3.1.2
    # via -r requirements/common.txt
cmake==4.4.3
    # via -r requirements/build/cpu.txt
compressed-tensors==0.17.0
    # via -r requirements/common.txt
cryptography==50.0.1
    # via pyjwt
depyf==0.20.0
    # via -r requirements/common.txt
detect-installer==0.2.1
    # via fastapi-cloud-cli
dill==0.4.1
    # via depyf
dnspython==2.8.0
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
fastapi-cloud-cli==0.25.0
    # via fastapi-cli
fastar==0.12.0
    # via
    #   fastapi
    #   fastapi-cloud-cli
filelock==3.32.5
    # via
    #   -r requirements/common.txt
    #   huggingface-hub
    #   torch
frozenlist==1.8.0
    # via
    #   aiohttp
    #   aiosignal
fsspec==2026.7.0
    # via
    #   huggingface-hub
    #   torch
googleapis-common-protos==1.75.3
    # via
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
grpcio==1.83.1
    # via opentelemetry-exporter-otlp-proto-grpc
h11==0.16.0
    # via
    #   httpcore
    #   httpcore2
    #   uvicorn
hf-xet==1.6.0
    # via huggingface-hub
httpcore==1.0.9
    # via httpx
httpcore2==2.12.0
    # via httpx2
httptools==0.8.0
    # via uvicorn
httpx==0.28.1
    # via
    #   fastapi
    #   fastapi-cloud-cli
    #   huggingface-hub
    #   model-hosting-container-standards
httpx2==2.12.0
    # via
    #   anthropic
    #   mcp
    #   openai
huggingface-hub==1.30.0
    # via
    #   -r requirements/common.txt
    #   tokenizers
    #   transformers
idna==3.19
    # via
    #   anyio
    #   email-validator
    #   httpx
    #   httpx2
    #   requests
    #   yarl
ijson==3.5.1
    # via -r requirements/common.txt
iniconfig==2.3.0
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
jiter==0.16.0
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
markupsafe==3.0.3
    # via jinja2
mcp==2.1.1
    # via -r requirements/common.txt
mcp-types==2.1.1
    # via mcp
mdurl==0.1.2
    # via markdown-it-py
mistral-common==1.11.7
    # via -r requirements/common.txt
model-hosting-container-standards==0.1.16
    # via -r requirements/common.txt
mpmath==1.3.0
    # via sympy
msgspec==0.21.1
    # via -r requirements/common.txt
multidict==6.7.1
    # via
    #   aiohttp
    #   yarl
networkx==3.6.1
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
openai==3.8.0
    # via -r requirements/common.txt
openai-harmony==0.0.8
    # via -r requirements/common.txt
opencv-python-headless==5.0.0.93
    # via
    #   -r requirements/common.txt
    #   mistral-common
opentelemetry-api==1.44.0
    # via
    #   -r requirements/common.txt
    #   mcp
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
    #   opentelemetry-sdk
    #   opentelemetry-semantic-conventions
opentelemetry-exporter-otlp==1.44.0
    # via -r requirements/common.txt
opentelemetry-exporter-otlp-proto-common==1.44.0
    # via
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
opentelemetry-exporter-otlp-proto-grpc==1.44.0
    # via opentelemetry-exporter-otlp
opentelemetry-exporter-otlp-proto-http==1.44.0
    # via opentelemetry-exporter-otlp
opentelemetry-proto==1.44.0
    # via
    #   opentelemetry-exporter-otlp-proto-common
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
opentelemetry-sdk==1.44.0
    # via
    #   -r requirements/common.txt
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
    #   opentelemetry-semantic-conventions-ai
opentelemetry-semantic-conventions==0.65b0
    # via
    #   opentelemetry-sdk
    #   opentelemetry-semantic-conventions-ai
opentelemetry-semantic-conventions-ai==0.5.1
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
pluggy==1.6.0
    # via pytest
prometheus-client==0.26.0
    # via
    #   -r requirements/common.txt
    #   prometheus-fastapi-instrumentator
prometheus-fastapi-instrumentator==8.1.0
    # via -r requirements/common.txt
propcache==0.5.2
    # via
    #   aiohttp
    #   yarl
protobuf==7.36.1
    # via
    #   -r requirements/common.txt
    #   googleapis-common-protos
    #   opentelemetry-proto
psutil==7.2.2
    # via -r requirements/common.txt
py-cpuinfo==9.0.0
    # via -r requirements/common.txt
pybase64==1.5.0
    # via -r requirements/common.txt
pycountry==26.2.16
    # via pydantic-extra-types
pycparser==3.0
    # via cffi
pydantic==2.13.5
    # via
    #   -r requirements/common.txt
    #   anthropic
    #   compressed-tensors
    #   fastapi
    #   fastapi-cloud-cli
    #   lm-format-enforcer
    #   mcp
    #   mcp-types
    #   mistral-common
    #   model-hosting-container-standards
    #   openai
    #   openai-harmony
    #   pydantic-extra-types
    #   pydantic-settings
    #   xgrammar
pydantic-core==2.46.5
    # via pydantic
pydantic-extra-types==2.11.1
    # via
    #   fastapi
    #   mistral-common
pydantic-settings==2.15.0
    # via fastapi
pygments==2.21.0
    # via
    #   pytest
    #   rich
pyjwt==2.13.0
    # via mcp
pytest==9.1.1
    # via
    #   -r extras.in
    #   pytest-asyncio
    #   pytest-timeout
pytest-asyncio==1.4.0
    # via -r extras.in
pytest-timeout==2.4.0
    # via -r extras.in
python-dotenv==1.2.3
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
regex==2026.9.3
    # via
    #   -r requirements/build/cpu.txt
    #   -r requirements/common.txt
    #   tiktoken
    #   transformers
requests==2.34.2
    # via
    #   -r requirements/common.txt
    #   mistral-common
    #   opentelemetry-exporter-otlp-proto-http
    #   tiktoken
rich==15.0.0
    # via
    #   rich-toolkit
    #   typer
rich-toolkit==0.20.4
    # via
    #   fastapi-cli
    #   fastapi-cloud-cli
rignore==0.8.1
    # via fastapi-cloud-cli
rpds-py==2026.6.3
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
sentry-sdk==2.68.1
    # via fastapi-cloud-cli
setproctitle==1.3.7
    # via -r requirements/common.txt
setuptools==77.0.3
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
setuptools-scm==10.2.3
    # via -r requirements/build/cpu.txt
shellingham==1.5.4
    # via typer
six==1.17.0
    # via -r requirements/common.txt
sniffio==1.3.1
    # via
    #   anthropic
    #   openai
sse-starlette==3.4.10
    # via mcp
starlette==1.6.0
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
tokenizers==0.23.2
    # via
    #   -r requirements/common.txt
    #   transformers
torch==2.13.0+cpu
    # via
    #   -r requirements/build/cpu.txt
    #   -r requirements/cpu.txt
    #   compressed-tensors
    #   torchvision
    #   xgrammar
torchaudio==2.11.0+cpu
    # via -r requirements/cpu.txt
torchcodec==0.16.0+cpu
    # via -r requirements/cpu.txt
torchvision==0.28.0+cpu
    # via -r requirements/cpu.txt
tqdm==4.70.0
    # via
    #   -r requirements/common.txt
    #   huggingface-hub
    #   transformers
transformers==5.16.1
    # via
    #   -r requirements/common.txt
    #   compressed-tensors
    #   xgrammar
triton==3.8.0
    # via xgrammar
truststore==0.10.4
    # via
    #   httpcore2
    #   httpx2
typer==0.27.2
    # via
    #   fastapi-cli
    #   fastapi-cloud-cli
    #   transformers
typing-extensions==4.16.0
    # via
    #   -r requirements/common.txt
    #   aiohttp
    #   aiosignal
    #   anthropic
    #   anyio
    #   apache-tvm-ffi
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
urllib3==2.7.0
    # via
    #   requests
    #   sentry-sdk
uvicorn==0.52.4
    # via
    #   fastapi
    #   fastapi-cli
    #   fastapi-cloud-cli
    #   mcp
uvloop==0.22.1
    # via uvicorn
vcs-versioning==2.3.4
    # via setuptools-scm
watchfiles==1.2.0
    # via
    #   -r requirements/common.txt
    #   uvicorn
websockets==17.1
    # via uvicorn
wheel==0.48.0
    # via -r requirements/build/cpu.txt
xgrammar==0.2.3
    # via -r requirements/common.txt
yarl==1.24.5
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
    --mount=type=cache,id=vllm-cargo-registry-${VLLM_CACHE_NAMESPACE},target=/root/.cargo/registry,sharing=locked \
    --mount=type=cache,id=vllm-cargo-git-${VLLM_CACHE_NAMESPACE},target=/root/.cargo/git,sharing=locked \
    python -c "import importlib.metadata as m; assert not any((d.metadata.get('Name') or '').lower() == 'vllm' for d in m.distributions())" \
 && \
    VLLM_REQUIRE_RUST_FRONTEND=1 \
    VLLM_TARGET_DEVICE=cpu \
      uv pip install --system --no-build-isolation --no-deps -e . --torch-backend cpu \
 && if [ -f tests/vllm_test_utils/setup.py ]; then \
      uv pip install --system --no-deps -e tests/vllm_test_utils; \
    fi \
 && test -x vllm/vllm-rs \
 && python -c "from pathlib import Path; import vllm; assert Path(vllm.__file__).resolve().is_relative_to(Path('/workspace/vllm'))"

RUN --mount=type=cache,id=vllm-cargo-registry-${VLLM_CACHE_NAMESPACE},target=/root/.cargo/registry,sharing=locked \
    --mount=type=cache,id=vllm-cargo-git-${VLLM_CACHE_NAMESPACE},target=/root/.cargo/git,sharing=locked \
    if [ -f rust/Cargo.toml ]; then \
      protoc --version; \
      install -d /opt/vllm-cargo-vendor; \
      cargo vendor --locked --manifest-path rust/Cargo.toml \
        /opt/vllm-cargo-vendor > /root/.cargo/config.toml; \
      printf '\n[net]\noffline = true\n' >> /root/.cargo/config.toml; \
      cargo metadata --manifest-path rust/Cargo.toml --locked --offline \
        --no-deps --format-version 1 > /dev/null; \
    fi

# Keep .git and every commit reachable from the pinned base on local main.
# Remove fetch-only metadata and reject any hidden, unreachable Git objects.
RUN find . -type d -name __pycache__ -prune -exec rm -rf {} + \
 && find . -type d \( -name '*.egg-info' -o -name '.pytest_cache' \) -prune -exec rm -rf {} + \
 && find /tmp -mindepth 1 -depth -delete \
 && if [ -d /root/.cache ]; then find /root/.cache -mindepth 1 -depth -delete; fi \
 && rm -rf /root/.rustup/downloads /root/.rustup/tmp \
 && rm -f /root/.cargo/.global-cache /root/.cargo/.package-cache \
      /root/.cargo/.package-cache-mutate \
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

# Optional task-scoped runtime metadata, pinned before the task base commit.
# Only the allow-listed files are downloaded; model tensors are forbidden.
RUN python - <<'VLLM_RUNTIME_ASSET_EOF'
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id='Qwen/Qwen3.6-27B',
    revision='6a9e13bd6fc8f0983b9b99948120bc37f49c13e9',
    local_dir='/opt/models/qwen-template',
    allow_patterns=['config.json', 'tokenizer.json', 'tokenizer_config.json', 'chat_template.jinja'],
)
VLLM_RUNTIME_ASSET_EOF
RUN rm -rf /opt/models/qwen-template/.cache /root/.cache/huggingface \
 && test -f /opt/models/qwen-template/config.json \
 && test -f /opt/models/qwen-template/tokenizer.json \
 && test -f /opt/models/qwen-template/tokenizer_config.json \
 && test -f /opt/models/qwen-template/chat_template.jinja \
 && test -z "$(find /opt/models/qwen-template -type f \
      \( -name '*.bin' -o -name '*.gguf' -o -name '*.pt' -o -name '*.pth' -o -name '*.safetensors' \) \
      -print -quit)"
LABEL ai.infra.bench.runtime-asset-repository=Qwen/Qwen3.6-27B \
      ai.infra.bench.runtime-asset-revision=6a9e13bd6fc8f0983b9b99948120bc37f49c13e9

LABEL ai.infra.bench.environment-template=vllm-harbor-all-in-one \
      ai.infra.bench.base-commit=$VLLM_BASE_SHA \
      ai.infra.bench.dependency-cutoff=$VLLM_DEPENDENCY_CUTOFF \
      ai.infra.bench.cache-namespace=$VLLM_CACHE_NAMESPACE
ENTRYPOINT []
CMD ["sleep", "infinity"]
