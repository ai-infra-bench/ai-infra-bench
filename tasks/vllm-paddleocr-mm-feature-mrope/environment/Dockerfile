# syntax=docker/dockerfile:1
# Template inputs below are replaced from task.toml by generate.py. Generated
# task Dockerfiles are self-contained and differ only in their frozen inputs.

ARG VLLM_BASE_SHA=29e5d102050669d03992a2eb863ad364ea50fab2
ARG VLLM_DEPENDENCY_CUTOFF=2026-04-15T09:09:20Z
ARG VLLM_CACHE_NAMESPACE=29e5d102050669d03992a2eb863ad364ea50fab2-407fd562f8bf40c3-7aeb85dc45afb45f
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
ARG RUST_TOOLCHAIN=1.94.1
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
# Exact task dependency lock (sha256:407fd562f8bf40c38f5f571deb7a88d4433ef3137ed563d15d44b20c301c4eb7) is embedded so this
# Dockerfile remains independently buildable with an empty context.
RUN --mount=type=cache,id=vllm-uv-downloads-v3,target=/root/.cache/uv,sharing=locked <<'VLLM_INSTALL_EOF'
set -eu
cat > /tmp/vllm-requirements.lock <<'VLLM_REQUIREMENTS_EOF'
# Generated with uv 0.11.28 from the pinned base requirements and task
# extras for CPython 3.12 on x86_64 manylinux_2_28. Packages newer than
# 2026-04-15T09:09:20Z were excluded during resolution.
aiohappyeyeballs==2.6.1
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
anthropic==0.95.0
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
astor==0.8.1
    # via depyf
attrs==26.1.0
    # via
    #   aiohttp
    #   jsonschema
    #   referencing
blake3==1.0.8
    # via -r requirements/common.txt
cachetools==7.0.5
    # via -r requirements/common.txt
cbor2==5.9.0
    # via -r requirements/common.txt
certifi==2026.2.25
    # via
    #   httpcore
    #   httpx
    #   requests
    #   sentry-sdk
cffi==2.0.0
    # via cryptography
charset-normalizer==3.4.7
    # via requests
click==8.3.2
    # via
    #   rich-toolkit
    #   typer
    #   uvicorn
cloudpickle==3.1.2
    # via -r requirements/common.txt
cmake==4.3.1
    # via -r requirements/build/cpu.txt
compressed-tensors==0.14.0.1
    # via -r requirements/common.txt
cryptography==46.0.7
    # via pyjwt
depyf==0.20.0
    # via -r requirements/common.txt
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
fastapi==0.135.3
    # via
    #   -r requirements/common.txt
    #   model-hosting-container-standards
fastapi-cli==0.0.24
    # via fastapi
fastapi-cloud-cli==0.16.1
    # via fastapi-cli
fastar==0.11.0
    # via fastapi-cloud-cli
filelock==3.28.0
    # via
    #   -r requirements/common.txt
    #   huggingface-hub
    #   torch
    #   transformers
frozenlist==1.8.0
    # via
    #   aiohttp
    #   aiosignal
fsspec==2026.3.0
    # via
    #   huggingface-hub
    #   torch
gguf==0.18.0
    # via -r requirements/common.txt
googleapis-common-protos==1.74.0
    # via
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
grpcio==1.80.0
    # via opentelemetry-exporter-otlp-proto-grpc
h11==0.16.0
    # via
    #   httpcore
    #   uvicorn
hf-xet==1.4.3
    # via huggingface-hub
httpcore==1.0.9
    # via httpx
httptools==0.7.1
    # via uvicorn
httpx==0.28.1
    # via
    #   anthropic
    #   fastapi
    #   fastapi-cloud-cli
    #   mcp
    #   model-hosting-container-standards
    #   openai
httpx-sse==0.4.3
    # via mcp
huggingface-hub==0.36.2
    # via
    #   tokenizers
    #   transformers
idna==3.11
    # via
    #   anyio
    #   email-validator
    #   httpx
    #   requests
    #   yarl
ijson==3.5.0
    # via -r requirements/common.txt
importlib-metadata==8.7.1
    # via opentelemetry-api
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
jiter==0.14.0
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
llguidance==1.3.0
    # via -r requirements/common.txt
llvmlite==0.44.0
    # via numba
lm-format-enforcer==0.11.3
    # via -r requirements/common.txt
loguru==0.7.3
    # via compressed-tensors
markdown-it-py==4.0.0
    # via rich
markupsafe==3.0.3
    # via jinja2
mcp==1.27.0
    # via -r requirements/common.txt
mdurl==0.1.2
    # via markdown-it-py
mistral-common==1.11.0
    # via -r requirements/common.txt
model-hosting-container-standards==0.1.14
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
numba==0.61.2
    # via -r requirements/cpu.txt
numpy==2.2.6
    # via
    #   -r requirements/common.txt
    #   gguf
    #   mistral-common
    #   numba
    #   opencv-python-headless
    #   torchvision
    #   transformers
    #   xgrammar
openai==2.31.0
    # via -r requirements/common.txt
openai-harmony==0.0.8
    # via -r requirements/common.txt
opencv-python-headless==4.13.0.92
    # via
    #   -r requirements/common.txt
    #   mistral-common
opentelemetry-api==1.41.0
    # via
    #   -r requirements/common.txt
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
    #   opentelemetry-sdk
    #   opentelemetry-semantic-conventions
opentelemetry-exporter-otlp==1.41.0
    # via -r requirements/common.txt
opentelemetry-exporter-otlp-proto-common==1.41.0
    # via
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
opentelemetry-exporter-otlp-proto-grpc==1.41.0
    # via opentelemetry-exporter-otlp
opentelemetry-exporter-otlp-proto-http==1.41.0
    # via opentelemetry-exporter-otlp
opentelemetry-proto==1.41.0
    # via
    #   opentelemetry-exporter-otlp-proto-common
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
opentelemetry-sdk==1.41.0
    # via
    #   -r requirements/common.txt
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
    #   opentelemetry-semantic-conventions-ai
opentelemetry-semantic-conventions==0.62b0
    # via
    #   opentelemetry-sdk
    #   opentelemetry-semantic-conventions-ai
opentelemetry-semantic-conventions-ai==0.5.1
    # via -r requirements/common.txt
outlines-core==0.2.11
    # via -r requirements/common.txt
packaging==26.1
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
propcache==0.4.1
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
pydantic==2.13.0
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
pydantic-core==2.46.0
    # via pydantic
pydantic-extra-types==2.11.1
    # via
    #   fastapi
    #   mistral-common
pydantic-settings==2.13.1
    # via
    #   fastapi
    #   mcp
pygments==2.20.0
    # via
    #   pytest
    #   rich
pyjwt==2.12.1
    # via mcp
pytest==9.0.3
    # via
    #   -r extras.in
    #   pytest-timeout
pytest-timeout==2.4.0
    # via -r extras.in
python-dotenv==1.2.2
    # via
    #   pydantic-settings
    #   uvicorn
python-json-logger==4.1.0
    # via -r requirements/common.txt
python-multipart==0.0.26
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
regex==2026.4.4
    # via
    #   -r requirements/build/cpu.txt
    #   -r requirements/common.txt
    #   tiktoken
    #   transformers
requests==2.33.1
    # via
    #   -r requirements/common.txt
    #   gguf
    #   huggingface-hub
    #   mistral-common
    #   opentelemetry-exporter-otlp-proto-http
    #   tiktoken
    #   transformers
rich==15.0.0
    # via
    #   rich-toolkit
    #   typer
rich-toolkit==0.19.7
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
    # via transformers
sentencepiece==0.2.1
    # via -r requirements/common.txt
sentry-sdk==2.58.0
    # via fastapi-cloud-cli
setproctitle==1.3.7
    # via -r requirements/common.txt
setuptools==77.0.3
    # via
    #   -r requirements/build/cpu.txt
    #   -r requirements/common.txt
    #   -r requirements/cpu.txt
    #   model-hosting-container-standards
    #   setuptools-scm
    #   torch
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
sse-starlette==3.3.4
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
tiktoken==0.12.0
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
transformers==4.57.6
    # via
    #   -r requirements/common.txt
    #   compressed-tensors
    #   xgrammar
triton==3.6.0
    # via xgrammar
typer==0.24.1
    # via
    #   fastapi-cli
    #   fastapi-cloud-cli
typing-extensions==4.15.0
    # via
    #   -r requirements/common.txt
    #   aiosignal
    #   anthropic
    #   anyio
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
urllib3==2.6.3
    # via
    #   requests
    #   sentry-sdk
uvicorn==0.44.0
    # via
    #   fastapi
    #   fastapi-cli
    #   fastapi-cloud-cli
    #   mcp
uvloop==0.22.1
    # via uvicorn
vcs-versioning==1.1.1
    # via setuptools-scm
watchfiles==1.1.1
    # via
    #   -r requirements/common.txt
    #   uvicorn
websockets==16.0
    # via uvicorn
wheel==0.46.3
    # via -r requirements/build/cpu.txt
xgrammar==0.1.33
    # via -r requirements/common.txt
yarl==1.23.0
    # via aiohttp
zipp==3.23.1
    # via importlib-metadata
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

ARG PROTOC_VERSION=34.1
RUN if [ -f rust/Cargo.toml ]; then \
      case "$TARGETARCH" in \
        amd64) protoc_arch=x86_64; protoc_sha=af27ea66cd26938fe48587804ca7d4817457a08350021a1c6e23a27ccc8c6904 ;; \
        arm64) protoc_arch=aarch_64; protoc_sha=31c5e9e3c7bf013cf41fb97765ee255c140024a6b175b6cc9b64beddd7c23ba7 ;; \
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
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKZnJvbSBkYXRhY2xhc3NlcyBpbXBvcnQgZGF0YWNsYXNzLCBmaWVsZAoKaW1wb3J0IG51bXB5IGFzIG5wCmltcG9ydCB0b3JjaAoKZnJvbSB2bGxtLm1vZGVsX2V4ZWN1dG9yLm1vZGVscy5wYWRkbGVvY3JfdmwgaW1wb3J0ICgKICAgIFBhZGRsZU9DUlZMRm9yQ29uZGl0aW9uYWxHZW5lcmF0aW9uLAopCmZyb20gdmxsbS5tdWx0aW1vZGFsLmlucHV0cyBpbXBvcnQgKAogICAgTXVsdGlNb2RhbEZlYXR1cmVTcGVjLAogICAgTXVsdGlNb2RhbEZpZWxkRWxlbSwKICAgIE11bHRpTW9kYWxLd2FyZ3NJdGVtLAogICAgUGxhY2Vob2xkZXJSYW5nZSwKKQoKCkBkYXRhY2xhc3MKY2xhc3MgVmlzaW9uQ29uZmlnOgogICAgc3BhdGlhbF9tZXJnZV9zaXplOiBpbnQgPSAyCiAgICBwYXRjaF9zaXplOiBpbnQgPSAxNAogICAgdG9rZW5zX3Blcl9zZWNvbmQ6IGZsb2F0ID0gMi4wCgoKQGRhdGFjbGFzcwpjbGFzcyBNb2RlbENvbmZpZzoKICAgIGltYWdlX3Rva2VuX2lkOiBpbnQgPSAxNTE2NTUKICAgIHZpZGVvX3Rva2VuX2lkOiBpbnQgPSAxNTE2NTQKICAgIHZpc2lvbl9zdGFydF90b2tlbl9pZDogaW50ID0gMTUxNjUyCiAgICB2aXNpb25fZW5kX3Rva2VuX2lkOiBpbnQgPSAxNTE2NTMKICAgIHZpc2lvbl9jb25maWc6IFZpc2lvbkNvbmZpZyA9IGZpZWxkKGRlZmF1bHRfZmFjdG9yeT1WaXNpb25Db25maWcpCgoKZGVmIG1ha2VfbW9kZWwoKToKICAgIG1vZGVsID0gb2JqZWN0Ll9fbmV3X18oUGFkZGxlT0NSVkxGb3JDb25kaXRpb25hbEdlbmVyYXRpb24pCiAgICBtb2RlbC5jb25maWcgPSBNb2RlbENvbmZpZygpCiAgICByZXR1cm4gbW9kZWwKCgpkZWYgX2ZpZWxkKHZhbHVlKSAtPiBNdWx0aU1vZGFsRmllbGRFbGVtOgogICAgcmV0dXJuIE11bHRpTW9kYWxGaWVsZEVsZW0oZGF0YT10b3JjaC5hc190ZW5zb3IodmFsdWUpLCBmaWVsZD1Ob25lKQoKCmRlZiBpbWFnZV9mZWF0dXJlKAogICAgb2Zmc2V0OiBpbnQsCiAgICBncmlkOiB0dXBsZVtpbnQsIGludCwgaW50XSwKICAgICosCiAgICBpZGVudGlmaWVyOiBzdHIgPSAiaW1hZ2UiLAopIC0+IE11bHRpTW9kYWxGZWF0dXJlU3BlYzoKICAgIHQsIGgsIHcgPSBncmlkCiAgICBtZXJnZSA9IDIKICAgIGxlbmd0aCA9IHQgKiBoICogdwogICAgcmV0dXJuIE11bHRpTW9kYWxGZWF0dXJlU3BlYygKICAgICAgICBkYXRhPU11bHRpTW9kYWxLd2FyZ3NJdGVtKAogICAgICAgICAgICB7ImltYWdlX2dyaWRfdGh3IjogX2ZpZWxkKCh0LCBoICogbWVyZ2UsIHcgKiBtZXJnZSkpfQogICAgICAgICksCiAgICAgICAgbW9kYWxpdHk9ImltYWdlIiwKICAgICAgICBpZGVudGlmaWVyPWlkZW50aWZpZXIsCiAgICAgICAgbW1fcG9zaXRpb249UGxhY2Vob2xkZXJSYW5nZShvZmZzZXQ9b2Zmc2V0LCBsZW5ndGg9bGVuZ3RoKSwKICAgICkKCgpkZWYgdmlkZW9fZmVhdHVyZSgKICAgIG9mZnNldDogaW50LAogICAgZ3JpZDogdHVwbGVbaW50LCBpbnQsIGludF0sCiAgICAqLAogICAgc2Vjb25kc19wZXJfZ3JpZDogZmxvYXQsCiAgICBpZGVudGlmaWVyOiBzdHIgPSAidmlkZW8iLAopIC0+IE11bHRpTW9kYWxGZWF0dXJlU3BlYzoKICAgIHQsIGgsIHcgPSBncmlkCiAgICBtZXJnZSA9IDIKICAgIGxlbmd0aCA9IHQgKiBoICogdwogICAgcmV0dXJuIE11bHRpTW9kYWxGZWF0dXJlU3BlYygKICAgICAgICBkYXRhPU11bHRpTW9kYWxLd2FyZ3NJdGVtKAogICAgICAgICAgICB7CiAgICAgICAgICAgICAgICAidmlkZW9fZ3JpZF90aHciOiBfZmllbGQoKHQsIGggKiBtZXJnZSwgdyAqIG1lcmdlKSksCiAgICAgICAgICAgICAgICAic2Vjb25kX3Blcl9ncmlkX3RzIjogX2ZpZWxkKHNlY29uZHNfcGVyX2dyaWQpLAogICAgICAgICAgICB9CiAgICAgICAgKSwKICAgICAgICBtb2RhbGl0eT0idmlkZW8iLAogICAgICAgIGlkZW50aWZpZXI9aWRlbnRpZmllciwKICAgICAgICBtbV9wb3NpdGlvbj1QbGFjZWhvbGRlclJhbmdlKG9mZnNldD1vZmZzZXQsIGxlbmd0aD1sZW5ndGgpLAogICAgKQoKCmRlZiByZWZlcmVuY2VfcG9zaXRpb25zKAogICAgaW5wdXRfdG9rZW5zOiBsaXN0W2ludF0sCiAgICBmZWF0dXJlczogbGlzdFtNdWx0aU1vZGFsRmVhdHVyZVNwZWNdLAogICAgKiwKICAgIHRva2Vuc19wZXJfc2Vjb25kOiBmbG9hdCA9IDIuMCwKKSAtPiB0dXBsZVt0b3JjaC5UZW5zb3IsIGludF06CiAgICBwYXJ0czogbGlzdFtucC5uZGFycmF5XSA9IFtdCiAgICBjdXJzb3IgPSAwCiAgICBjdXJyZW50X21heCA9IC0xCiAgICBmb3IgZmVhdHVyZSBpbiBzb3J0ZWQoZmVhdHVyZXMsIGtleT1sYW1iZGEgaXRlbTogaXRlbS5tbV9wb3NpdGlvbi5vZmZzZXQpOgogICAgICAgIG9mZnNldCA9IGZlYXR1cmUubW1fcG9zaXRpb24ub2Zmc2V0CiAgICAgICAgdGV4dF9sZW4gPSBvZmZzZXQgLSBjdXJzb3IKICAgICAgICBzdGFydCA9IGN1cnJlbnRfbWF4ICsgMQogICAgICAgIGlmIHRleHRfbGVuOgogICAgICAgICAgICB0ZXh0ID0gbnAuYnJvYWRjYXN0X3RvKG5wLmFyYW5nZSh0ZXh0X2xlbiksICgzLCB0ZXh0X2xlbikpICsgc3RhcnQKICAgICAgICAgICAgcGFydHMuYXBwZW5kKHRleHQpCiAgICAgICAgICAgIGN1cnJlbnRfbWF4ID0gaW50KHRleHQubWF4KCkpCgogICAgICAgIGFzc2VydCBmZWF0dXJlLmRhdGEgaXMgbm90IE5vbmUKICAgICAgICBpZiBmZWF0dXJlLm1vZGFsaXR5ID09ICJpbWFnZSI6CiAgICAgICAgICAgIHQsIHJhd19oLCByYXdfdyA9IGZlYXR1cmUuZGF0YVsiaW1hZ2VfZ3JpZF90aHciXS5kYXRhLnRvbGlzdCgpCiAgICAgICAgICAgIGZhY3RvciA9IDEuMAogICAgICAgIGVsc2U6CiAgICAgICAgICAgIHQsIHJhd19oLCByYXdfdyA9IGZlYXR1cmUuZGF0YVsidmlkZW9fZ3JpZF90aHciXS5kYXRhLnRvbGlzdCgpCiAgICAgICAgICAgIGZhY3RvciA9IGZsb2F0KGZlYXR1cmUuZGF0YVsic2Vjb25kX3Blcl9ncmlkX3RzIl0uZGF0YS5pdGVtKCkpCiAgICAgICAgICAgIGZhY3RvciAqPSB0b2tlbnNfcGVyX3NlY29uZAogICAgICAgIGgsIHcgPSByYXdfaCAvLyAyLCByYXdfdyAvLyAyCiAgICAgICAgZ3JpZCA9IG5wLmluZGljZXMoKHQsIGgsIHcpKQogICAgICAgIGlmIGZhY3RvciAhPSAxLjA6CiAgICAgICAgICAgIGdyaWRbMF0gPSAoZ3JpZFswXSAqIGZhY3RvcikuYXN0eXBlKG5wLmludDY0KQogICAgICAgIHZpc2lvbiA9IGdyaWQucmVzaGFwZSgzLCAtMSkgKyB0ZXh0X2xlbiArIHN0YXJ0CiAgICAgICAgcGFydHMuYXBwZW5kKHZpc2lvbikKICAgICAgICBjdXJyZW50X21heCA9IG1heChjdXJyZW50X21heCwgaW50KHZpc2lvbi5tYXgoKSkpCiAgICAgICAgY3Vyc29yID0gb2Zmc2V0ICsgdCAqIGggKiB3CgogICAgaWYgY3Vyc29yIDwgbGVuKGlucHV0X3Rva2Vucyk6CiAgICAgICAgdGV4dF9sZW4gPSBsZW4oaW5wdXRfdG9rZW5zKSAtIGN1cnNvcgogICAgICAgIHN0YXJ0ID0gY3VycmVudF9tYXggKyAxCiAgICAgICAgdGFpbCA9IG5wLmJyb2FkY2FzdF90byhucC5hcmFuZ2UodGV4dF9sZW4pLCAoMywgdGV4dF9sZW4pKSArIHN0YXJ0CiAgICAgICAgcGFydHMuYXBwZW5kKHRhaWwpCiAgICBwb3NpdGlvbnMgPSBucC5jb25jYXRlbmF0ZShwYXJ0cywgYXhpcz0xKS5yZXNoYXBlKDMsIC0xKQogICAgZGVsdGEgPSBpbnQocG9zaXRpb25zLm1heCgpICsgMSAtIGxlbihpbnB1dF90b2tlbnMpKQogICAgcmV0dXJuIHRvcmNoLmZyb21fbnVtcHkocG9zaXRpb25zKSwgZGVsdGEKCgpkZWYgc3RhbmRhcmRfaW1hZ2VfcHJvbXB0KAogICAgcHJlZml4OiBsaXN0W2ludF0sCiAgICBncmlkOiB0dXBsZVtpbnQsIGludCwgaW50XSwKICAgIHN1ZmZpeDogbGlzdFtpbnRdLAopIC0+IHR1cGxlW2xpc3RbaW50XSwgTXVsdGlNb2RhbEZlYXR1cmVTcGVjXToKICAgIG1vZGVsX2NvbmZpZyA9IE1vZGVsQ29uZmlnKCkKICAgIGNvdW50ID0gaW50KG5wLnByb2QoZ3JpZCkpCiAgICBvZmZzZXQgPSBsZW4ocHJlZml4KSArIDEKICAgIHRva2VucyA9ICgKICAgICAgICBwcmVmaXgKICAgICAgICArIFttb2RlbF9jb25maWcudmlzaW9uX3N0YXJ0X3Rva2VuX2lkXQogICAgICAgICsgW21vZGVsX2NvbmZpZy5pbWFnZV90b2tlbl9pZF0gKiBjb3VudAogICAgICAgICsgW21vZGVsX2NvbmZpZy52aXNpb25fZW5kX3Rva2VuX2lkXQogICAgICAgICsgc3VmZml4CiAgICApCiAgICByZXR1cm4gdG9rZW5zLCBpbWFnZV9mZWF0dXJlKG9mZnNldCwgZ3JpZCkKCgpkZWYgY29tcHV0ZShpbnB1dF90b2tlbnM6IGxpc3RbaW50XSwgZmVhdHVyZXM6IGxpc3RbTXVsdGlNb2RhbEZlYXR1cmVTcGVjXSk6CiAgICBtb2RlbCA9IG1ha2VfbW9kZWwoKQogICAgcmV0dXJuIG1vZGVsLmdldF9tcm9wZV9pbnB1dF9wb3NpdGlvbnMoaW5wdXRfdG9rZW5zLCBmZWF0dXJlcykK | base64 -d > /opt/repro/mrope_fixture.py && install -d /opt/repro \
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGpzb24KaW1wb3J0IHRpbWUKCmltcG9ydCB0b3JjaAoKZnJvbSBtcm9wZV9maXh0dXJlIGltcG9ydCBjb21wdXRlLCByZWZlcmVuY2VfcG9zaXRpb25zLCBzdGFuZGFyZF9pbWFnZV9wcm9tcHQKCgpkZWYgbWFpbigpIC0+IGludDoKICAgIHN0YW5kYXJkLCBmZWF0dXJlID0gc3RhbmRhcmRfaW1hZ2VfcHJvbXB0KFsxMF0sICgxLCAyLCAyKSwgWzMwLCAzMV0pCiAgICBtdXRhdGVkID0gbGlzdChzdGFuZGFyZCkKICAgIHN0YXJ0ID0gZmVhdHVyZS5tbV9wb3NpdGlvbi5vZmZzZXQKICAgIG11dGF0ZWRbc3RhcnQgOiBzdGFydCArIGZlYXR1cmUubW1fcG9zaXRpb24ubGVuZ3RoXSA9IFs3NzddICogZmVhdHVyZS5tbV9wb3NpdGlvbi5sZW5ndGgKCiAgICBleHBlY3RlZCwgZXhwZWN0ZWRfZGVsdGEgPSByZWZlcmVuY2VfcG9zaXRpb25zKG11dGF0ZWQsIFtmZWF0dXJlXSkKICAgIHN0YW5kYXJkX3Bvc2l0aW9ucywgc3RhbmRhcmRfZGVsdGEgPSBjb21wdXRlKHN0YW5kYXJkLCBbZmVhdHVyZV0pCiAgICBzdGFydGVkID0gdGltZS5wZXJmX2NvdW50ZXIoKQogICAgbXV0YXRlZF9wb3NpdGlvbnMsIG11dGF0ZWRfZGVsdGEgPSBjb21wdXRlKG11dGF0ZWQsIFtmZWF0dXJlXSkKICAgIGVsYXBzZWQgPSB0aW1lLnBlcmZfY291bnRlcigpIC0gc3RhcnRlZAoKICAgIHJlc3VsdCA9IHsKICAgICAgICAiZmVhdHVyZV9vZmZzZXQiOiBmZWF0dXJlLm1tX3Bvc2l0aW9uLm9mZnNldCwKICAgICAgICAiZmVhdHVyZV9sZW5ndGgiOiBmZWF0dXJlLm1tX3Bvc2l0aW9uLmxlbmd0aCwKICAgICAgICAic3RhbmRhcmRfbWF0Y2hlc19yZWZlcmVuY2UiOiB0b3JjaC5lcXVhbChzdGFuZGFyZF9wb3NpdGlvbnMsIGV4cGVjdGVkKSwKICAgICAgICAic3RhbmRhcmRfZGVsdGEiOiBzdGFuZGFyZF9kZWx0YSwKICAgICAgICAibXV0YXRlZF9tYXRjaGVzX3JlZmVyZW5jZSI6IHRvcmNoLmVxdWFsKG11dGF0ZWRfcG9zaXRpb25zLCBleHBlY3RlZCksCiAgICAgICAgIm11dGF0ZWRfZGVsdGEiOiBtdXRhdGVkX2RlbHRhLAogICAgICAgICJleHBlY3RlZF9kZWx0YSI6IGV4cGVjdGVkX2RlbHRhLAogICAgICAgICJtaXNtYXRjaGVkX2Nvb3JkaW5hdGVzIjogaW50KChtdXRhdGVkX3Bvc2l0aW9ucyAhPSBleHBlY3RlZCkuc3VtKCkuaXRlbSgpKSwKICAgICAgICAiZWxhcHNlZF9zZWNvbmRzIjogZWxhcHNlZCwKICAgIH0KICAgIHByaW50KGpzb24uZHVtcHMocmVzdWx0LCBpbmRlbnQ9MikpCiAgICBwYXNzZWQgPSByZXN1bHRbIm11dGF0ZWRfbWF0Y2hlc19yZWZlcmVuY2UiXSBhbmQgbXV0YXRlZF9kZWx0YSA9PSBleHBlY3RlZF9kZWx0YQogICAgcHJpbnQoZiJtbV9mZWF0dXJlX3Bvc2l0aW9uX2NvbnRyYWN0PXtwYXNzZWR9IikKICAgIHJldHVybiAwIGlmIHBhc3NlZCBlbHNlIDMKCgppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOgogICAgcmFpc2UgU3lzdGVtRXhpdChtYWluKCkpCg== | base64 -d > /opt/repro/mrope_trace.py
LABEL ai.infra.bench.environment-template=vllm-harbor-all-in-one \
      ai.infra.bench.base-commit=$VLLM_BASE_SHA \
      ai.infra.bench.dependency-cutoff=$VLLM_DEPENDENCY_CUTOFF \
      ai.infra.bench.cache-namespace=$VLLM_CACHE_NAMESPACE
ENTRYPOINT []
CMD ["sleep", "infinity"]
