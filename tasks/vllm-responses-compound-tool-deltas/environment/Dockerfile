# syntax=docker/dockerfile:1
# Template inputs below are replaced from task.toml by generate.py. Generated
# task Dockerfiles are self-contained and differ only in their frozen inputs.

ARG VLLM_BASE_SHA=626fa9bba5663a5cf6a870debf031ee344ddb822
ARG VLLM_DEPENDENCY_CUTOFF=2026-05-28T04:59:34Z
ARG VLLM_CACHE_NAMESPACE=626fa9bba5663a5cf6a870debf031ee344ddb822-ea0a2002b8105f9e-58c4f34b2c181742
ARG VLLM_REPO=https://github.com/vllm-project/vllm.git

######################### PINNED SYSTEM BASE #########################
# This image was published before every benchmark cutoff. System packages are
# installed from the task cutoff's immutable Debian snapshot rather than from a
# moving distribution mirror.
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
ARG RUST_TOOLCHAIN=1.95.0
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

ARG VLLM_DEPENDENCY_CUTOFF
# Exact task dependency lock (sha256:ea0a2002b8105f9e84d12078294d88b42949f87dbbd6a4e616abde1a3864c3e9) is embedded so this
# Dockerfile remains independently buildable with an empty context.
RUN --mount=type=cache,id=vllm-uv-downloads-v3,target=/root/.cache/uv,sharing=locked <<'VLLM_INSTALL_EOF'
set -eu
cat > /tmp/vllm-requirements.lock <<'VLLM_REQUIREMENTS_EOF'
# Generated with uv 0.11.28 from the pinned base requirements and task
# extras for CPython 3.12 on x86_64 manylinux_2_28. Packages newer than
# 2026-05-28T04:59:34Z were excluded during resolution.
aiohappyeyeballs==2.6.2
    # via aiohttp
aiohttp==3.13.5
    # via -r requirements/common.txt
aiosignal==1.4.0
    # via aiohttp
annotated-doc==0.0.4
    # via
    #   fastapi
    #   typer
annotated-types==0.7.0
    # via pydantic
anthropic==0.104.1
    # via -r requirements/common.txt
anyio==4.13.0
    # via
    #   anthropic
    #   httpx
    #   mcp
    #   openai
    #   sse-starlette
    #   starlette
    #   watchfiles
apache-tvm-ffi==0.1.11
    # via xgrammar
astor==0.8.1
    # via depyf
attrs==26.1.0
    # via
    #   aiohttp
    #   jsonschema
    #   referencing
blake3==1.0.8
    # via -r requirements/common.txt
cachetools==7.1.4
    # via -r requirements/common.txt
cbor2==6.1.1
    # via -r requirements/common.txt
certifi==2026.5.20
    # via
    #   httpcore
    #   httpx
    #   requests
    #   sentry-sdk
cffi==2.0.0
    # via cryptography
charset-normalizer==3.4.7
    # via requests
click==8.4.1
    # via
    #   huggingface-hub
    #   rich-toolkit
    #   typer
    #   uvicorn
cloudpickle==3.1.2
    # via -r requirements/common.txt
cmake==4.3.2
    # via -r requirements/build/cpu.txt
compressed-tensors==0.15.0.1
    # via -r requirements/common.txt
cryptography==48.0.0
    # via pyjwt
depyf==0.20.0
    # via -r requirements/common.txt
detect-installer==0.1.0
    # via fastapi-cloud-cli
dill==0.4.1
    # via depyf
diskcache==5.6.3
    # via -r requirements/common.txt
distro==1.9.0
    # via
    #   anthropic
    #   openai
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
fastapi-cli==0.0.24
    # via fastapi
fastapi-cloud-cli==0.18.0
    # via fastapi-cli
fastar==0.11.0
    # via
    #   fastapi
    #   fastapi-cloud-cli
filelock==3.29.0
    # via
    #   -r requirements/common.txt
    #   huggingface-hub
    #   torch
frozenlist==1.8.0
    # via
    #   aiohttp
    #   aiosignal
fsspec==2026.4.0
    # via
    #   huggingface-hub
    #   torch
gguf==0.19.0
    # via -r requirements/common.txt
googleapis-common-protos==1.75.0
    # via
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
grpcio==1.80.0
    # via opentelemetry-exporter-otlp-proto-grpc
h11==0.16.0
    # via
    #   httpcore
    #   uvicorn
hf-xet==1.5.0
    # via huggingface-hub
httpcore==1.0.9
    # via httpx
httptools==0.8.0
    # via uvicorn
httpx==0.28.1
    # via
    #   -r extras.in
    #   anthropic
    #   fastapi
    #   fastapi-cloud-cli
    #   huggingface-hub
    #   mcp
    #   model-hosting-container-standards
    #   openai
httpx-sse==0.4.3
    # via mcp
huggingface-hub==1.16.4
    # via
    #   tokenizers
    #   transformers
idna==3.16
    # via
    #   anyio
    #   email-validator
    #   httpx
    #   requests
    #   yarl
ijson==3.5.0
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
jiter==0.15.0
    # via
    #   anthropic
    #   openai
jmespath==1.1.0
    # via model-hosting-container-standards
jsonschema==4.26.0
    # via
    #   mcp
    #   mistral-common
jsonschema-specifications==2025.9.1
    # via jsonschema
lark==1.2.2
    # via -r requirements/common.txt
llguidance==1.7.5
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
mcp==1.27.1
    # via -r requirements/common.txt
mdurl==0.1.2
    # via markdown-it-py
mistral-common==1.11.2
    # via -r requirements/common.txt
model-hosting-container-standards==0.1.15
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
ninja==1.13.0
    # via
    #   -r requirements/build/cpu.txt
    #   -r requirements/common.txt
numba==0.65.0
    # via -r requirements/cpu.txt
numpy==2.3.5
    # via
    #   -r requirements/common.txt
    #   gguf
    #   mistral-common
    #   numba
    #   opencv-python-headless
    #   torchvision
    #   transformers
    #   xgrammar
openai==2.38.0
    # via -r requirements/common.txt
openai-harmony==0.0.8
    # via -r requirements/common.txt
opencv-python-headless==4.13.0.92
    # via
    #   -r requirements/common.txt
    #   mistral-common
opentelemetry-api==1.42.1
    # via
    #   -r requirements/common.txt
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
    #   opentelemetry-sdk
    #   opentelemetry-semantic-conventions
opentelemetry-exporter-otlp==1.42.1
    # via -r requirements/common.txt
opentelemetry-exporter-otlp-proto-common==1.42.1
    # via
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
opentelemetry-exporter-otlp-proto-grpc==1.42.1
    # via opentelemetry-exporter-otlp
opentelemetry-exporter-otlp-proto-http==1.42.1
    # via opentelemetry-exporter-otlp
opentelemetry-proto==1.42.1
    # via
    #   opentelemetry-exporter-otlp-proto-common
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
opentelemetry-sdk==1.42.1
    # via
    #   -r requirements/common.txt
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
    #   opentelemetry-semantic-conventions-ai
opentelemetry-semantic-conventions==0.63b1
    # via
    #   opentelemetry-sdk
    #   opentelemetry-semantic-conventions-ai
opentelemetry-semantic-conventions-ai==0.5.1
    # via -r requirements/common.txt
outlines-core==0.2.14
    # via -r requirements/common.txt
packaging==26.2
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
pillow==12.2.0
    # via
    #   -r requirements/common.txt
    #   mistral-common
    #   torchvision
pluggy==1.6.0
    # via pytest
prometheus-client==0.25.0
    # via
    #   -r requirements/common.txt
    #   prometheus-fastapi-instrumentator
prometheus-fastapi-instrumentator==7.1.0
    # via -r requirements/common.txt
propcache==0.5.2
    # via
    #   aiohttp
    #   yarl
protobuf==6.33.6
    # via
    #   -r requirements/common.txt
    #   googleapis-common-protos
    #   opentelemetry-proto
psutil==7.2.2
    # via -r requirements/common.txt
py-cpuinfo==9.0.0
    # via -r requirements/common.txt
pybase64==1.4.3
    # via -r requirements/common.txt
pycountry==26.2.16
    # via pydantic-extra-types
pycparser==3.0
    # via cffi
pydantic==2.13.4
    # via
    #   -r requirements/common.txt
    #   anthropic
    #   compressed-tensors
    #   fastapi
    #   fastapi-cloud-cli
    #   lm-format-enforcer
    #   mcp
    #   mistral-common
    #   model-hosting-container-standards
    #   openai
    #   openai-harmony
    #   pydantic-extra-types
    #   pydantic-settings
    #   xgrammar
pydantic-core==2.46.4
    # via pydantic
pydantic-extra-types==2.11.1
    # via
    #   fastapi
    #   mistral-common
pydantic-settings==2.14.1
    # via
    #   fastapi
    #   mcp
pygments==2.20.0
    # via
    #   pytest
    #   rich
pyjwt==2.13.0
    # via mcp
pytest==9.0.3
    # via
    #   -r extras.in
    #   pytest-asyncio
    #   pytest-timeout
pytest-asyncio==1.4.0
    # via -r extras.in
pytest-timeout==2.4.0
    # via -r extras.in
python-dotenv==1.2.2
    # via
    #   pydantic-settings
    #   uvicorn
python-json-logger==4.1.0
    # via -r requirements/common.txt
python-multipart==0.0.29
    # via
    #   fastapi
    #   mcp
pyyaml==6.0.3
    # via
    #   -r requirements/common.txt
    #   gguf
    #   huggingface-hub
    #   lm-format-enforcer
    #   transformers
    #   uvicorn
pyzmq==27.1.0
    # via -r requirements/common.txt
referencing==0.37.0
    # via
    #   jsonschema
    #   jsonschema-specifications
regex==2026.5.9
    # via
    #   -r requirements/build/cpu.txt
    #   -r requirements/common.txt
    #   tiktoken
    #   transformers
requests==2.34.2
    # via
    #   -r requirements/common.txt
    #   gguf
    #   mistral-common
    #   opentelemetry-exporter-otlp-proto-http
    #   tiktoken
rich==15.0.0
    # via
    #   rich-toolkit
    #   typer
rich-toolkit==0.19.10
    # via
    #   fastapi-cli
    #   fastapi-cloud-cli
rignore==0.7.6
    # via fastapi-cloud-cli
rpds-py==0.30.0
    # via
    #   jsonschema
    #   referencing
safetensors==0.7.0
    # via
    #   -r requirements/common.txt
    #   transformers
semantic-version==2.10.0
    # via setuptools-rust
sentencepiece==0.2.1
    # via -r requirements/common.txt
sentry-sdk==2.60.0
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
setuptools-rust==1.12.1
    # via -r requirements/build/cpu.txt
setuptools-scm==10.0.5
    # via -r requirements/build/cpu.txt
shellingham==1.5.4
    # via typer
six==1.17.0
    # via -r requirements/common.txt
sniffio==1.3.1
    # via
    #   anthropic
    #   openai
sse-starlette==3.4.4
    # via mcp
starlette==0.52.1
    # via
    #   fastapi
    #   mcp
    #   model-hosting-container-standards
    #   prometheus-fastapi-instrumentator
    #   sse-starlette
supervisor==4.3.0
    # via model-hosting-container-standards
sympy==1.14.0
    # via torch
tiktoken==0.13.0
    # via
    #   -r requirements/common.txt
    #   mistral-common
tokenizers==0.22.2
    # via
    #   -r requirements/common.txt
    #   transformers
torch==2.11.0+cpu
    # via
    #   -r requirements/build/cpu.txt
    #   -r requirements/cpu.txt
    #   compressed-tensors
    #   torchvision
    #   xgrammar
torchaudio==2.11.0+cpu
    # via -r requirements/cpu.txt
torchvision==0.26.0+cpu
    # via -r requirements/cpu.txt
tqdm==4.67.3
    # via
    #   -r requirements/common.txt
    #   gguf
    #   huggingface-hub
    #   openai
    #   transformers
transformers==5.9.0
    # via
    #   -r requirements/common.txt
    #   compressed-tensors
    #   xgrammar
triton==3.7.0
    # via xgrammar
typer==0.25.1
    # via
    #   fastapi-cli
    #   fastapi-cloud-cli
    #   huggingface-hub
    #   transformers
typing-extensions==4.15.0
    # via
    #   -r requirements/common.txt
    #   aiosignal
    #   anthropic
    #   anyio
    #   apache-tvm-ffi
    #   fastapi
    #   grpcio
    #   huggingface-hub
    #   mcp
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
typing-inspection==0.4.2
    # via
    #   fastapi
    #   mcp
    #   pydantic
    #   pydantic-settings
urllib3==2.7.0
    # via
    #   requests
    #   sentry-sdk
uvicorn==0.48.0
    # via
    #   -r extras.in
    #   fastapi
    #   fastapi-cli
    #   fastapi-cloud-cli
    #   mcp
uvloop==0.22.1
    # via uvicorn
vcs-versioning==1.1.1
    # via setuptools-scm
watchfiles==1.2.0
    # via
    #   -r requirements/common.txt
    #   uvicorn
websockets==16.0
    # via uvicorn
wheel==0.47.0
    # via -r requirements/build/cpu.txt
xgrammar==0.2.1
    # via -r requirements/common.txt
yarl==1.24.2
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
 && find vllm -maxdepth 1 -type f -name '_C*.so' \
      -exec strip --strip-debug {} + \
 && find vllm -maxdepth 1 -type f -name '_C*.so' \
      -exec objcopy --remove-section .note.gnu.build-id {} \; \
 && python -c "from pathlib import Path; import vllm; assert Path(vllm.__file__).resolve().is_relative_to(Path('/workspace/vllm'))"

ARG PROTOC_VERSION=34.2
RUN if [ -f rust/Cargo.toml ]; then \
      case "$TARGETARCH" in \
        amd64) protoc_arch=x86_64; protoc_sha=b52e803fad2f63232f75351c0ff735e891f40262de791bade78a3636831a522a ;; \
        arm64) protoc_arch=aarch_64; protoc_sha=63d92a87482d4eaa41a72f9de6ea7f476e1fb4c722700fa0b981cc204f7d3a14 ;; \
        *) echo "Unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
      esac; \
      curl --http1.1 -L --retry 10 --retry-all-errors --connect-timeout 30 --max-time 600 \
        --proto '=https' --tlsv1.2 -sSf \
        "https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOC_VERSION}/protoc-${PROTOC_VERSION}-linux-${protoc_arch}.zip" \
        -o /tmp/protoc.zip; \
      printf '%s  %s\n' "$protoc_sha" /tmp/protoc.zip | sha256sum -c -; \
      unzip -q -o /tmp/protoc.zip -d /usr/local; \
      rm -f /tmp/protoc.zip; \
      protoc --version; \
      install -d /opt/vllm-cargo-vendor; \
      cargo vendor --locked --manifest-path rust/Cargo.toml \
        /opt/vllm-cargo-vendor > /root/.cargo/config.toml; \
      printf '\n[net]\noffline = true\n' >> /root/.cargo/config.toml; \
      rm -rf /root/.cargo/registry /root/.cargo/git; \
      cargo metadata --manifest-path rust/Cargo.toml --locked --offline \
        --no-deps --format-version 1 > /dev/null; \
      rustup default 1.95; \
      rustup toolchain uninstall "$RUST_TOOLCHAIN"; \
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

RUN install -d /opt/repro && install -d /opt/repro \
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGpzb24KaW1wb3J0IHNvY2tldAppbXBvcnQgdGhyZWFkaW5nCmltcG9ydCB0aW1lCmZyb20gY29sbGVjdGlvbnMuYWJjIGltcG9ydCBBc3luY0l0ZXJhdG9yCmZyb20gdW5pdHRlc3QubW9jayBpbXBvcnQgQXN5bmNNb2NrLCBNYWdpY01vY2sKCmltcG9ydCBodHRweAppbXBvcnQgdXZpY29ybgpmcm9tIGZhc3RhcGkgaW1wb3J0IEZhc3RBUEkKCmZyb20gdmxsbS5lbnRyeXBvaW50cy5vcGVuYWkuZW5naW5lLnByb3RvY29sIGltcG9ydCAoCiAgICBEZWx0YUZ1bmN0aW9uQ2FsbCwKICAgIERlbHRhTWVzc2FnZSwKICAgIERlbHRhVG9vbENhbGwsCikKZnJvbSB2bGxtLmVudHJ5cG9pbnRzLm9wZW5haS5yZXNwb25zZXMuYXBpX3JvdXRlciBpbXBvcnQgYXR0YWNoX3JvdXRlcgpmcm9tIHZsbG0uZW50cnlwb2ludHMub3BlbmFpLnJlc3BvbnNlcy5zZXJ2aW5nIGltcG9ydCBPcGVuQUlTZXJ2aW5nUmVzcG9uc2VzCmZyb20gdmxsbS5pbnB1dHMgaW1wb3J0IHRva2Vuc19pbnB1dApmcm9tIHZsbG0ub3V0cHV0cyBpbXBvcnQgQ29tcGxldGlvbk91dHB1dCwgUmVxdWVzdE91dHB1dAoKCkVYUEVDVEVEID0gJ3sicGF0aCI6Ii90bXAveC5weSIsImNvbnRlbnQiOiJwcmludChcXCJoaVxcIikifScKCgpjbGFzcyBEZXRlcm1pbmlzdGljUGFyc2VyOgogICAgcmVhc29uaW5nX3BhcnNlciA9IE1hZ2ljTW9jaygpCiAgICB0b29sX3BhcnNlciA9IE5vbmUKCiAgICBkZWYgX19pbml0X18oc2VsZikgLT4gTm9uZToKICAgICAgICBzZWxmLnVzZWQgPSBGYWxzZQoKICAgIGRlZiBwYXJzZV9kZWx0YShzZWxmLCAqKl9rd2FyZ3MpOgogICAgICAgIGlmIHNlbGYudXNlZDoKICAgICAgICAgICAgcmV0dXJuIE5vbmUKICAgICAgICBzZWxmLnVzZWQgPSBUcnVlCiAgICAgICAgcmV0dXJuIERlbHRhTWVzc2FnZSgKICAgICAgICAgICAgdG9vbF9jYWxscz1bCiAgICAgICAgICAgICAgICBEZWx0YVRvb2xDYWxsKAogICAgICAgICAgICAgICAgICAgIGluZGV4PTAsCiAgICAgICAgICAgICAgICAgICAgaWQ9ImNhbGxfd3JpdGUiLAogICAgICAgICAgICAgICAgICAgIHR5cGU9ImZ1bmN0aW9uIiwKICAgICAgICAgICAgICAgICAgICBmdW5jdGlvbj1EZWx0YUZ1bmN0aW9uQ2FsbChuYW1lPSJ3cml0ZSIpLAogICAgICAgICAgICAgICAgKSwKICAgICAgICAgICAgICAgIERlbHRhVG9vbENhbGwoCiAgICAgICAgICAgICAgICAgICAgaW5kZXg9MCwKICAgICAgICAgICAgICAgICAgICBmdW5jdGlvbj1EZWx0YUZ1bmN0aW9uQ2FsbChhcmd1bWVudHM9RVhQRUNURUQpLAogICAgICAgICAgICAgICAgKSwKICAgICAgICAgICAgXQogICAgICAgICkKCiAgICBkZWYgaXNfcmVhc29uaW5nX2VuZChzZWxmLCAqX2FyZ3MsICoqX2t3YXJncykgLT4gYm9vbDoKICAgICAgICByZXR1cm4gRmFsc2UKCiAgICBkZWYgZXh0cmFjdF9yZXNwb25zZV9vdXRwdXRzKHNlbGYsICoqX2t3YXJncykgLT4gbGlzdDoKICAgICAgICByZXR1cm4gW10KCgpjbGFzcyBQYXJzZXJGYWN0b3J5OgogICAgcmVhc29uaW5nX3BhcnNlcl9jbHMgPSBOb25lCiAgICB0b29sX3BhcnNlcl9jbHMgPSBOb25lCgogICAgZGVmIF9fY2FsbF9fKHNlbGYsICpfYXJncywgKipfa3dhcmdzKSAtPiBEZXRlcm1pbmlzdGljUGFyc2VyOgogICAgICAgIHJldHVybiBEZXRlcm1pbmlzdGljUGFyc2VyKCkKCgpkZWYgc2VydmluZygpIC0+IE9wZW5BSVNlcnZpbmdSZXNwb25zZXM6CiAgICBlbmdpbmUgPSBNYWdpY01vY2soKQogICAgZW5naW5lLmVycm9yZWQgPSBGYWxzZQogICAgZW5naW5lLm1vZGVsX2NvbmZpZy5tYXhfbW9kZWxfbGVuID0gNDA5NgogICAgZW5naW5lLm1vZGVsX2NvbmZpZy5tb2RlbCA9ICJtb29uc2hvdGFpL0tpbWktSzIuNSIKICAgIGVuZ2luZS5tb2RlbF9jb25maWcuZ2VuZXJhdGlvbl9jb25maWcgPSAidmxsbSIKICAgIGVuZ2luZS5tb2RlbF9jb25maWcub3ZlcnJpZGVfZ2VuZXJhdGlvbl9jb25maWcgPSB7fQogICAgZW5naW5lLm1vZGVsX2NvbmZpZy5oZl9jb25maWcubW9kZWxfdHlwZSA9ICJ0ZXN0IgogICAgZW5naW5lLm1vZGVsX2NvbmZpZy5oZl90ZXh0X2NvbmZpZyA9IE1hZ2ljTW9jaygpCiAgICBlbmdpbmUubW9kZWxfY29uZmlnLmdldF9kaWZmX3NhbXBsaW5nX3BhcmFtLnJldHVybl92YWx1ZSA9IHt9CiAgICBlbmdpbmUuaW5wdXRfcHJvY2Vzc29yID0gTWFnaWNNb2NrKCkKICAgIGVuZ2luZS5yZW5kZXJlciA9IE1hZ2ljTW9jaygpCiAgICBlbmdpbmUucmVuZGVyZXIuZ2V0X3Rva2VuaXplci5yZXR1cm5fdmFsdWUgPSBNYWdpY01vY2soKQogICAgZW5naW5lLmlzX3RyYWNpbmdfZW5hYmxlZCA9IEFzeW5jTW9jayhyZXR1cm5fdmFsdWU9RmFsc2UpCgogICAgYXN5bmMgZGVmIGdlbmVyYXRlKCpfYXJncywgKipfa3dhcmdzKSAtPiBBc3luY0l0ZXJhdG9yW1JlcXVlc3RPdXRwdXRdOgogICAgICAgIHlpZWxkIFJlcXVlc3RPdXRwdXQoCiAgICAgICAgICAgIHJlcXVlc3RfaWQ9InJlcSIsCiAgICAgICAgICAgIHByb21wdD0icHJvbXB0IiwKICAgICAgICAgICAgcHJvbXB0X3Rva2VuX2lkcz1bMSwgMl0sCiAgICAgICAgICAgIHByb21wdF9sb2dwcm9icz1Ob25lLAogICAgICAgICAgICBvdXRwdXRzPVsKICAgICAgICAgICAgICAgIENvbXBsZXRpb25PdXRwdXQoCiAgICAgICAgICAgICAgICAgICAgaW5kZXg9MCwKICAgICAgICAgICAgICAgICAgICB0ZXh0PSJtb2RlbCB1cGRhdGUiLAogICAgICAgICAgICAgICAgICAgIHRva2VuX2lkcz1bMTBdLAogICAgICAgICAgICAgICAgICAgIGN1bXVsYXRpdmVfbG9ncHJvYj0wLjAsCiAgICAgICAgICAgICAgICAgICAgbG9ncHJvYnM9Tm9uZSwKICAgICAgICAgICAgICAgICAgICBmaW5pc2hfcmVhc29uPSJzdG9wIiwKICAgICAgICAgICAgICAgICAgICBzdG9wX3JlYXNvbj1Ob25lLAogICAgICAgICAgICAgICAgKQogICAgICAgICAgICBdLAogICAgICAgICAgICBmaW5pc2hlZD1UcnVlLAogICAgICAgICAgICBudW1fY2FjaGVkX3Rva2Vucz0wLAogICAgICAgICkKCiAgICBlbmdpbmUuZ2VuZXJhdGUgPSBnZW5lcmF0ZQogICAgcmVuZGVyID0gTWFnaWNNb2NrKCkKICAgIHJlbmRlci5wcmVwcm9jZXNzX2NoYXQgPSBBc3luY01vY2soCiAgICAgICAgcmV0dXJuX3ZhbHVlPShbXSwgW3Rva2Vuc19pbnB1dChbMSwgMl0pXSkKICAgICkKICAgIG1vZGVscyA9IE1hZ2ljTW9jaygpCiAgICBtb2RlbHMuaXNfYmFzZV9tb2RlbC5yZXR1cm5fdmFsdWUgPSBUcnVlCiAgICBtb2RlbHMubW9kZWxfbmFtZS5yZXR1cm5fdmFsdWUgPSAibW9vbnNob3RhaS9LaW1pLUsyLjUiCiAgICBtb2RlbHMubG9yYV9yZXF1ZXN0cyA9IHt9CiAgICBoYW5kbGVyID0gT3BlbkFJU2VydmluZ1Jlc3BvbnNlcygKICAgICAgICBlbmdpbmVfY2xpZW50PWVuZ2luZSwKICAgICAgICBtb2RlbHM9bW9kZWxzLAogICAgICAgIG9wZW5haV9zZXJ2aW5nX3JlbmRlcj1yZW5kZXIsCiAgICAgICAgcmVxdWVzdF9sb2dnZXI9Tm9uZSwKICAgICAgICBjaGF0X3RlbXBsYXRlPU5vbmUsCiAgICAgICAgY2hhdF90ZW1wbGF0ZV9jb250ZW50X2Zvcm1hdD0iYXV0byIsCiAgICApCiAgICBoYW5kbGVyLnBhcnNlciA9IFBhcnNlckZhY3RvcnkoKQogICAgcmV0dXJuIGhhbmRsZXIKCgpkZWYgbWFpbigpIC0+IGludDoKICAgIGFwcCA9IEZhc3RBUEkoKQogICAgYXR0YWNoX3JvdXRlcihhcHApCiAgICBhcHAuc3RhdGUub3BlbmFpX3NlcnZpbmdfcmVzcG9uc2VzID0gc2VydmluZygpCgogICAgbGlzdGVuZXIgPSBzb2NrZXQuc29ja2V0KCkKICAgIGxpc3RlbmVyLmJpbmQoKCIxMjcuMC4wLjEiLCAwKSkKICAgIGxpc3RlbmVyLmxpc3RlbigpCiAgICBwb3J0ID0gbGlzdGVuZXIuZ2V0c29ja25hbWUoKVsxXQogICAgc2VydmVyID0gdXZpY29ybi5TZXJ2ZXIoCiAgICAgICAgdXZpY29ybi5Db25maWcoYXBwLCBsb2dfbGV2ZWw9Indhcm5pbmciLCBsaWZlc3Bhbj0ib2ZmIikKICAgICkKICAgIHRocmVhZCA9IHRocmVhZGluZy5UaHJlYWQoCiAgICAgICAgdGFyZ2V0PXNlcnZlci5ydW4sCiAgICAgICAga3dhcmdzPXsic29ja2V0cyI6IFtsaXN0ZW5lcl19LAogICAgICAgIGRhZW1vbj1UcnVlLAogICAgKQogICAgdGhyZWFkLnN0YXJ0KCkKICAgIGRlYWRsaW5lID0gdGltZS5tb25vdG9uaWMoKSArIDE1CiAgICB3aGlsZSBub3Qgc2VydmVyLnN0YXJ0ZWQgYW5kIHRpbWUubW9ub3RvbmljKCkgPCBkZWFkbGluZToKICAgICAgICB0aW1lLnNsZWVwKDAuMDUpCiAgICBhc3NlcnQgc2VydmVyLnN0YXJ0ZWQKCiAgICByZXF1ZXN0ID0gewogICAgICAgICJtb2RlbCI6ICJtb29uc2hvdGFpL0tpbWktSzIuNSIsCiAgICAgICAgInN0cmVhbSI6IFRydWUsCiAgICAgICAgInN0b3JlIjogRmFsc2UsCiAgICAgICAgImlucHV0IjogKAogICAgICAgICAgICAnQ2FsbCB0aGUgd3JpdGUgdG9vbCB0byBwdXQgcHJpbnQoImhpIikgaW50byAvdG1wL3gucHkuICcKICAgICAgICAgICAgIk5vIGV4cGxhbmF0aW9uLiIKICAgICAgICApLAogICAgICAgICJ0b29scyI6IFsKICAgICAgICAgICAgewogICAgICAgICAgICAgICAgInR5cGUiOiAiZnVuY3Rpb24iLAogICAgICAgICAgICAgICAgIm5hbWUiOiAid3JpdGUiLAogICAgICAgICAgICAgICAgImRlc2NyaXB0aW9uIjogIldyaXRlIGNvbnRlbnQgdG8gYSBmaWxlLiIsCiAgICAgICAgICAgICAgICAicGFyYW1ldGVycyI6IHsKICAgICAgICAgICAgICAgICAgICAidHlwZSI6ICJvYmplY3QiLAogICAgICAgICAgICAgICAgICAgICJwcm9wZXJ0aWVzIjogewogICAgICAgICAgICAgICAgICAgICAgICAicGF0aCI6IHsidHlwZSI6ICJzdHJpbmcifSwKICAgICAgICAgICAgICAgICAgICAgICAgImNvbnRlbnQiOiB7InR5cGUiOiAic3RyaW5nIn0sCiAgICAgICAgICAgICAgICAgICAgfSwKICAgICAgICAgICAgICAgICAgICAicmVxdWlyZWQiOiBbInBhdGgiLCAiY29udGVudCJdLAogICAgICAgICAgICAgICAgfSwKICAgICAgICAgICAgfQogICAgICAgIF0sCiAgICB9CiAgICBldmVudHMgPSBbXQogICAgdHJ5OgogICAgICAgIHdpdGggaHR0cHguc3RyZWFtKAogICAgICAgICAgICAiUE9TVCIsCiAgICAgICAgICAgIGYiaHR0cDovLzEyNy4wLjAuMTp7cG9ydH0vdjEvcmVzcG9uc2VzIiwKICAgICAgICAgICAganNvbj1yZXF1ZXN0LAogICAgICAgICAgICB0aW1lb3V0PTMwLAogICAgICAgICkgYXMgcmVzcG9uc2U6CiAgICAgICAgICAgIHByaW50KGYiUE9TVCAvdjEvcmVzcG9uc2VzIHtyZXNwb25zZS5zdGF0dXNfY29kZX0iKQogICAgICAgICAgICBmb3IgbGluZSBpbiByZXNwb25zZS5pdGVyX2xpbmVzKCk6CiAgICAgICAgICAgICAgICBpZiBsaW5lLnN0YXJ0c3dpdGgoImRhdGE6ICIpOgogICAgICAgICAgICAgICAgICAgIGV2ZW50ID0ganNvbi5sb2FkcyhsaW5lWzY6XSkKICAgICAgICAgICAgICAgICAgICBldmVudHMuYXBwZW5kKGV2ZW50KQogICAgICAgICAgICAgICAgICAgIHByaW50KGYie2V2ZW50Wyd0eXBlJ119OiB7bGluZVs2Ol19IikKICAgIGZpbmFsbHk6CiAgICAgICAgc2VydmVyLnNob3VsZF9leGl0ID0gVHJ1ZQogICAgICAgIHRocmVhZC5qb2luKHRpbWVvdXQ9MTApCiAgICAgICAgbGlzdGVuZXIuY2xvc2UoKQoKICAgIGRvbmUgPSBuZXh0KAogICAgICAgIGV2ZW50WyJpdGVtIl1bImFyZ3VtZW50cyJdCiAgICAgICAgZm9yIGV2ZW50IGluIGV2ZW50cwogICAgICAgIGlmIGV2ZW50WyJ0eXBlIl0gPT0gInJlc3BvbnNlLm91dHB1dF9pdGVtLmRvbmUiCiAgICAgICAgYW5kIGV2ZW50WyJpdGVtIl1bInR5cGUiXSA9PSAiZnVuY3Rpb25fY2FsbCIKICAgICkKICAgIHRyeToKICAgICAgICBwYXJzZWQgPSBqc29uLmxvYWRzKGRvbmUpCiAgICBleGNlcHQganNvbi5KU09ORGVjb2RlRXJyb3IgYXMgZXJyb3I6CiAgICAgICAgcHJpbnQoZiJkb25lLmFyZ3VtZW50cz17ZG9uZSFyfSIpCiAgICAgICAgcHJpbnQoZiJqc29uX2Vycm9yPXtlcnJvci5tc2d9IikKICAgICAgICByZXR1cm4gMwogICAgcHJpbnQoZiJkb25lLmFyZ3VtZW50cz17ZG9uZSFyfSIpCiAgICBwcmludChmIm1hdGNoZXNfcmVxdWVzdD17cGFyc2VkID09IGpzb24ubG9hZHMoRVhQRUNURUQpfSIpCiAgICByZXR1cm4gMCBpZiBwYXJzZWQgPT0ganNvbi5sb2FkcyhFWFBFQ1RFRCkgZWxzZSAzCgoKaWYgX19uYW1lX18gPT0gIl9fbWFpbl9fIjoKICAgIHJhaXNlIFN5c3RlbUV4aXQobWFpbigpKQo= | base64 -d > /opt/repro/responses_tool_stream.py
LABEL ai.infra.bench.environment-template=vllm-harbor-all-in-one \
      ai.infra.bench.base-commit=$VLLM_BASE_SHA \
      ai.infra.bench.dependency-cutoff=$VLLM_DEPENDENCY_CUTOFF \
      ai.infra.bench.cache-namespace=$VLLM_CACHE_NAMESPACE
ENTRYPOINT []
CMD ["sleep", "infinity"]
