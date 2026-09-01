# syntax=docker/dockerfile:1
# Template inputs below are replaced from task.toml by generate.py. Generated
# task Dockerfiles are self-contained and differ only in their frozen inputs.

ARG VLLM_BASE_SHA=d4004455d2357985830af10e432709b42c820455
ARG VLLM_DEPENDENCY_CUTOFF=2026-05-25T09:49:19Z
ARG VLLM_CACHE_NAMESPACE=d4004455d2357985830af10e432709b42c820455-984a41fb44695a0f-58c4f34b2c181742
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
# Exact task dependency lock (sha256:984a41fb44695a0fa1d99d658020a2120c052338bf66908acaed29b6757123c5) is embedded so this
# Dockerfile remains independently buildable with an empty context.
RUN --mount=type=cache,id=vllm-uv-downloads-v3,target=/root/.cache/uv,sharing=locked <<'VLLM_INSTALL_EOF'
set -eu
cat > /tmp/vllm-requirements.lock <<'VLLM_REQUIREMENTS_EOF'
# Generated with uv 0.11.28 from the pinned base requirements and task
# extras for CPython 3.12 on x86_64 manylinux_2_28. Packages newer than
# 2026-05-25T09:49:19Z were excluded during resolution.
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
httptools==0.7.1
    # via uvicorn
httpx==0.28.1
    # via
    #   anthropic
    #   fastapi
    #   fastapi-cloud-cli
    #   huggingface-hub
    #   mcp
    #   model-hosting-container-standards
    #   openai
httpx-sse==0.4.3
    # via mcp
huggingface-hub==1.16.1
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
    #   pytest-timeout
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
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGFyZ3BhcnNlCmltcG9ydCBjb250ZXh0bGliCmltcG9ydCBqc29uCmltcG9ydCBvcwppbXBvcnQgc29ja2V0CmltcG9ydCB0ZW1wZmlsZQppbXBvcnQgdGltZQpmcm9tIHBhdGhsaWIgaW1wb3J0IFBhdGgKZnJvbSB0eXBpbmcgaW1wb3J0IEFueQoKCmRlZiBfdGlueV9tb2RlbChwYXRoOiBzdHIpIC0+IHN0cjoKICAgIHJvb3QgPSBQYXRoKHBhdGgpCiAgICByb290Lm1rZGlyKHBhcmVudHM9VHJ1ZSwgZXhpc3Rfb2s9VHJ1ZSkKICAgIGNvbmZpZyA9IHJvb3QgLyAiY29uZmlnLmpzb24iCiAgICBpZiBub3QgY29uZmlnLmV4aXN0cygpOgogICAgICAgIGNvbmZpZy53cml0ZV90ZXh0KAogICAgICAgICAgICBqc29uLmR1bXBzKAogICAgICAgICAgICAgICAgewogICAgICAgICAgICAgICAgICAgICJhcmNoaXRlY3R1cmVzIjogWyJPUFRGb3JDYXVzYWxMTSJdLAogICAgICAgICAgICAgICAgICAgICJtb2RlbF90eXBlIjogIm9wdCIsCiAgICAgICAgICAgICAgICAgICAgImhpZGRlbl9zaXplIjogNjQsCiAgICAgICAgICAgICAgICAgICAgImZmbl9kaW0iOiAxMjgsCiAgICAgICAgICAgICAgICAgICAgIm51bV9hdHRlbnRpb25faGVhZHMiOiA0LAogICAgICAgICAgICAgICAgICAgICJudW1faGlkZGVuX2xheWVycyI6IDEsCiAgICAgICAgICAgICAgICAgICAgInZvY2FiX3NpemUiOiAxMjgsCiAgICAgICAgICAgICAgICAgICAgIm1heF9wb3NpdGlvbl9lbWJlZGRpbmdzIjogNTEyLAogICAgICAgICAgICAgICAgICAgICJ3b3JkX2VtYmVkX3Byb2pfZGltIjogNjQsCiAgICAgICAgICAgICAgICB9CiAgICAgICAgICAgICkKICAgICAgICApCiAgICByZXR1cm4gc3RyKHJvb3QpCgoKZGVmIG1ha2VfY29uZmlnKG1vZGVsX2Rpcjogc3RyLCAqLCB0Y3A6IGJvb2wpOgogICAgZnJvbSB2bGxtLmNvbmZpZyBpbXBvcnQgKAogICAgICAgIENhY2hlQ29uZmlnLAogICAgICAgIE1vZGVsQ29uZmlnLAogICAgICAgIFBhcmFsbGVsQ29uZmlnLAogICAgICAgIFNjaGVkdWxlckNvbmZpZywKICAgICAgICBWbGxtQ29uZmlnLAogICAgKQoKICAgIG1vZGVsID0gTW9kZWxDb25maWcoCiAgICAgICAgbW9kZWw9X3RpbnlfbW9kZWwobW9kZWxfZGlyKSwKICAgICAgICBkdHlwZT0iZmxvYXQxNiIsCiAgICAgICAgc2tpcF90b2tlbml6ZXJfaW5pdD1UcnVlLAogICAgKQogICAgcGFyYWxsZWwgPSBQYXJhbGxlbENvbmZpZygKICAgICAgICBkYXRhX3BhcmFsbGVsX3NpemU9MiBpZiB0Y3AgZWxzZSAxLAogICAgICAgIGRhdGFfcGFyYWxsZWxfc2l6ZV9sb2NhbD0xLAogICAgICAgIGRhdGFfcGFyYWxsZWxfcmFuaz0wLAogICAgICAgIGRhdGFfcGFyYWxsZWxfbWFzdGVyX2lwPSIxMjcuMC4wLjEiLAogICAgKQogICAgcmV0dXJuIFZsbG1Db25maWcoCiAgICAgICAgbW9kZWxfY29uZmlnPW1vZGVsLAogICAgICAgIHBhcmFsbGVsX2NvbmZpZz1wYXJhbGxlbCwKICAgICAgICBzY2hlZHVsZXJfY29uZmlnPVNjaGVkdWxlckNvbmZpZygKICAgICAgICAgICAgbWF4X251bV9zZXFzPTgsCiAgICAgICAgICAgIG1heF9udW1fYmF0Y2hlZF90b2tlbnM9MTI4LAogICAgICAgICAgICBtYXhfbW9kZWxfbGVuPTUxMiwKICAgICAgICAgICAgaXNfZW5jb2Rlcl9kZWNvZGVyPW1vZGVsLmlzX2VuY29kZXJfZGVjb2RlciwKICAgICAgICApLAogICAgICAgIGNhY2hlX2NvbmZpZz1DYWNoZUNvbmZpZygKICAgICAgICAgICAgYmxvY2tfc2l6ZT0xNiwKICAgICAgICAgICAgZ3B1X21lbW9yeV91dGlsaXphdGlvbj0wLjksCiAgICAgICAgICAgIGNhY2hlX2R0eXBlPSJhdXRvIiwKICAgICAgICApLAogICAgKQoKCmRlZiBtcGNsaWVudF93b3JrZXIoX2xpc3RlbiwgX3NvY2ssIGFyZ3MsIGNsaWVudF9jb25maWcpIC0+IE5vbmU6CiAgICBmcm9tIHZsbG0udjEuZW5naW5lLmNvcmVfY2xpZW50IGltcG9ydCBNUENsaWVudAoKICAgIGlmIGFyZ3Mud29ya2VyX2RlbGF5OgogICAgICAgIHRpbWUuc2xlZXAoYXJncy53b3JrZXJfZGVsYXkpCiAgICBjb25maWcgPSBtYWtlX2NvbmZpZyhhcmdzLm1vZGVsX2RpciwgdGNwPWFyZ3MudGNwKQogICAgTVBDbGllbnQoCiAgICAgICAgYXN5bmNpb19tb2RlPUZhbHNlLAogICAgICAgIHZsbG1fY29uZmlnPWNvbmZpZywKICAgICAgICBleGVjdXRvcl9jbGFzcz1vYmplY3QsCiAgICAgICAgbG9nX3N0YXRzPUZhbHNlLAogICAgICAgIGNsaWVudF9hZGRyZXNzZXM9Y2xpZW50X2NvbmZpZywKICAgICkKCgpkZWYgY3Jhc2hpbmdfd29ya2VyKF9saXN0ZW4sIF9zb2NrLCBfYXJncywgX2NsaWVudF9jb25maWcpIC0+IE5vbmU6CiAgICByYWlzZSBSdW50aW1lRXJyb3IoInN5bnRoZXRpYyBBUEkgd29ya2VyIHN0YXJ0dXAgZmFpbHVyZSIpCgoKZGVmIF9wb3J0KHVyaTogc3RyKSAtPiBpbnQ6CiAgICBpZiBub3QgdXJpLnN0YXJ0c3dpdGgoInRjcDovLyIpOgogICAgICAgIHJldHVybiAtMQogICAgcmV0dXJuIGludCh1cmkucnNwbGl0KCI6IiwgMSlbMV0pCgoKZGVmIHJ1bl9zY2VuYXJpbygKICAgIG1vZGU6IHN0ciwKICAgICosCiAgICBzZXJ2ZXJzOiBpbnQsCiAgICB3b3JrZXJfZGVsYXk6IGZsb2F0ID0gMC4wLAopIC0+IGRpY3Rbc3RyLCBBbnldOgogICAgaW1wb3J0IHZsbG0KICAgIGltcG9ydCB2bGxtLnYxLmVuZ2luZS51dGlscyBhcyBlbmdpbmVfdXRpbHMKICAgIGltcG9ydCB2bGxtLnYxLnV0aWxzIGFzIHByb2Nlc3NfdXRpbHMKICAgIGZyb20gdmxsbS5lbnRyeXBvaW50cy5jbGkgaW1wb3J0IHNlcnZlCgogICAgbW9kZWxfZGlyID0gdGVtcGZpbGUubWtkdGVtcChwcmVmaXg9InBvcnQtcmFjZS1tb2RlbC0iKQogICAgdGNwID0gbW9kZSAhPSAiaXBjIgogICAgY29uZmlnID0gbWFrZV9jb25maWcobW9kZWxfZGlyLCB0Y3A9dGNwKQogICAgc3RhdGU6IGRpY3Rbc3RyLCBBbnldID0ge30KICAgIHNxdWF0dGVyczogbGlzdFtzb2NrZXQuc29ja2V0XSA9IFtdCiAgICBvcmlnaW5hbF9hc3luY19lbmdpbmVfYXJncyA9IHZsbG0uQXN5bmNFbmdpbmVBcmdzCiAgICBvcmlnaW5hbF9leGVjdXRvcl9nZXRfY2xhc3MgPSBzZXJ2ZS5FeGVjdXRvci5fX2RpY3RfX1siZ2V0X2NsYXNzIl0KICAgIG9yaWdpbmFsX3NldHVwX3Byb21ldGhldXMgPSBzZXJ2ZS5zZXR1cF9tdWx0aXByb2Nlc3NfcHJvbWV0aGV1cwogICAgb3JpZ2luYWxfc2V0dXBfc2VydmVyID0gc2VydmUuc2V0dXBfc2VydmVyCiAgICBvcmlnaW5hbF9sYXVuY2ggPSBzZXJ2ZS5sYXVuY2hfY29yZV9lbmdpbmVzCiAgICBvcmlnaW5hbF93YWl0ID0gc2VydmUud2FpdF9mb3JfY29tcGxldGlvbl9vcl9mYWlsdXJlCiAgICBvcmlnaW5hbF93b3JrZXIgPSBwcm9jZXNzX3V0aWxzLnJ1bl9hcGlfc2VydmVyX3dvcmtlcl9wcm9jCiAgICBvcmlnaW5hbF9ydXN0X3BhdGggPSBzZXJ2ZS5lbnZzLlZMTE1fUlVTVF9GUk9OVEVORF9QQVRICiAgICBvcmlnaW5hbF9ydXN0X21hbmFnZXIgPSBzZXJ2ZS5SdXN0RnJvbnRlbmRQcm9jZXNzTWFuYWdlcgoKICAgIGNsYXNzIEZha2VBc3luY0VuZ2luZUFyZ3M6CiAgICAgICAgZGlzYWJsZV9sb2dfc3RhdHMgPSBUcnVlCgogICAgICAgIEBjbGFzc21ldGhvZAogICAgICAgIGRlZiBmcm9tX2NsaV9hcmdzKGNscywgX2FyZ3MpOgogICAgICAgICAgICByZXR1cm4gY2xzKCkKCiAgICAgICAgZGVmIGNyZWF0ZV9lbmdpbmVfY29uZmlnKHNlbGYsICoqX2t3YXJncyk6CiAgICAgICAgICAgIHJldHVybiBjb25maWcKCiAgICBAY29udGV4dGxpYi5jb250ZXh0bWFuYWdlcgogICAgZGVmIGZha2VfbGF1bmNoKF9jb25maWcsIF9leGVjdXRvciwgX2xvZ19zdGF0cywgYWRkcmVzc2VzLCBfY291bnQ9MSk6CiAgICAgICAgeWllbGQgTm9uZSwgTm9uZSwgYWRkcmVzc2VzLCBOb25lCiAgICAgICAgc3RhdGVbImlucHV0cyJdID0gbGlzdChhZGRyZXNzZXMuaW5wdXRzKQogICAgICAgIHN0YXRlWyJvdXRwdXRzIl0gPSBsaXN0KGFkZHJlc3Nlcy5vdXRwdXRzKQoKICAgIGRlZiBmYWtlX3dhaXQoKiwgYXBpX3NlcnZlcl9tYW5hZ2VyLCAqKl9rd2FyZ3MpOgogICAgICAgIGlmIG5vdCBhcGlfc2VydmVyX21hbmFnZXIucHJvY2Vzc2VzOgogICAgICAgICAgICByZXR1cm4KICAgICAgICAjIEEgY29ycmVjdGVkIHN0YXJ0dXAgaGFzIGFscmVhZHkgcmVjZWl2ZWQgZXZlcnkgY2hpbGQncyBib3VuZAogICAgICAgICMgZW5kcG9pbnRzIGJlZm9yZSByZWFjaGluZyB0aGlzIGhvb2suIFRoZSBsZWdhY3kgcGF0aCBoYXMgbm8gc3VjaAogICAgICAgICMgaGFuZHNoYWtlLCBzbyBnaXZlIGEgcHJlc3N1cmVkIG9yIGNyYXNoaW5nIGNoaWxkIHRpbWUgdG8gcmVhY2ggaXRzCiAgICAgICAgIyByZWFsIFpNUSBiaW5kIGluc3RlYWQgb2YgdHJlYXRpbmcgYSBmcmVzaGx5IHNwYXduZWQgUElEIGFzIHJlYWR5LgogICAgICAgIG11c3Rfb2JzZXJ2ZV9leGl0ID0gbW9kZSA9PSAiY3Jhc2giIG9yIChtb2RlID09ICJyYWNlIiBhbmQgc3F1YXR0ZXJzKQogICAgICAgIGRlYWRsaW5lID0gdGltZS5tb25vdG9uaWMoKSArIDEyLjAKCiAgICAgICAgZGVmIGVuZHBvaW50X3JlYWR5KHVyaTogc3RyKSAtPiBib29sOgogICAgICAgICAgICBpZiB1cmkuc3RhcnRzd2l0aCgiaXBjOi8vIik6CiAgICAgICAgICAgICAgICByZXR1cm4gUGF0aCh1cmkucmVtb3ZlcHJlZml4KCJpcGM6Ly8iKSkuZXhpc3RzKCkKICAgICAgICAgICAgcG9ydCA9IF9wb3J0KHVyaSkKICAgICAgICAgICAgaWYgcG9ydCA8PSAwOgogICAgICAgICAgICAgICAgcmV0dXJuIEZhbHNlCiAgICAgICAgICAgIHByb2JlID0gc29ja2V0LnNvY2tldChzb2NrZXQuQUZfSU5FVCwgc29ja2V0LlNPQ0tfU1RSRUFNKQogICAgICAgICAgICBwcm9iZS5zZXR0aW1lb3V0KDAuMDUpCiAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgIHJldHVybiBwcm9iZS5jb25uZWN0X2V4KCgiMTI3LjAuMC4xIiwgcG9ydCkpID09IDAKICAgICAgICAgICAgZmluYWxseToKICAgICAgICAgICAgICAgIHByb2JlLmNsb3NlKCkKCiAgICAgICAgd2hpbGUgdGltZS5tb25vdG9uaWMoKSA8IGRlYWRsaW5lOgogICAgICAgICAgICBmYWlsZWQgPSBbCiAgICAgICAgICAgICAgICBwcm9jCiAgICAgICAgICAgICAgICBmb3IgcHJvYyBpbiBhcGlfc2VydmVyX21hbmFnZXIucHJvY2Vzc2VzCiAgICAgICAgICAgICAgICBpZiBwcm9jLmV4aXRjb2RlIGlzIG5vdCBOb25lIGFuZCBwcm9jLmV4aXRjb2RlICE9IDAKICAgICAgICAgICAgXQogICAgICAgICAgICBpZiBmYWlsZWQ6CiAgICAgICAgICAgICAgICBwcm9jID0gZmFpbGVkWzBdCiAgICAgICAgICAgICAgICByYWlzZSBSdW50aW1lRXJyb3IoCiAgICAgICAgICAgICAgICAgICAgZiJQcm9jZXNzIHtwcm9jLm5hbWV9IGRpZWQgd2l0aCBleGl0IGNvZGUge3Byb2MuZXhpdGNvZGV9IgogICAgICAgICAgICAgICAgKQogICAgICAgICAgICBlbmRwb2ludHMgPSBbKnN0YXRlLmdldCgiaW5wdXRzIiwgW10pLCAqc3RhdGUuZ2V0KCJvdXRwdXRzIiwgW10pXQogICAgICAgICAgICBpZiAoCiAgICAgICAgICAgICAgICBub3QgbXVzdF9vYnNlcnZlX2V4aXQKICAgICAgICAgICAgICAgIGFuZCBlbmRwb2ludHMKICAgICAgICAgICAgICAgIGFuZCBhbGwoZW5kcG9pbnRfcmVhZHkodXJpKSBmb3IgdXJpIGluIGVuZHBvaW50cykKICAgICAgICAgICAgKToKICAgICAgICAgICAgICAgIGFwaV9zZXJ2ZXJfbWFuYWdlci5zaHV0ZG93bih0aW1lb3V0PTEuMCkKICAgICAgICAgICAgICAgIHJldHVybgogICAgICAgICAgICB0aW1lLnNsZWVwKDAuMDEpCiAgICAgICAgaWYgbXVzdF9vYnNlcnZlX2V4aXQ6CiAgICAgICAgICAgIHJhaXNlIFJ1bnRpbWVFcnJvcigicHJlc3N1cmVkIEFQSSBzZXJ2ZXIgdW5leHBlY3RlZGx5IHJlbWFpbmVkIGFsaXZlIikKICAgICAgICByYWlzZSBSdW50aW1lRXJyb3IoIkFQSSBzZXJ2ZXIgc29ja2V0cyBkaWQgbm90IGJlY29tZSByZWFjaGFibGUiKQoKICAgIG9yaWdpbmFsX2FkZHJlc3NlcyA9IGVuZ2luZV91dGlscy5nZXRfZW5naW5lX3ptcV9hZGRyZXNzZXMKCiAgICBkZWYgcHJlc3N1cmVkX2FkZHJlc3NlcygqYXJncywgKiprd2FyZ3MpOgogICAgICAgIGFkZHJlc3NlcyA9IG9yaWdpbmFsX2FkZHJlc3NlcygqYXJncywgKiprd2FyZ3MpCiAgICAgICAgaWYgbW9kZSAhPSAicmFjZSI6CiAgICAgICAgICAgIHJldHVybiBhZGRyZXNzZXMKICAgICAgICBmb3IgdXJpIGluIGRpY3QuZnJvbWtleXMoWyphZGRyZXNzZXMuaW5wdXRzLCAqYWRkcmVzc2VzLm91dHB1dHNdKToKICAgICAgICAgICAgcG9ydCA9IF9wb3J0KHVyaSkKICAgICAgICAgICAgaWYgcG9ydCA8PSAwOgogICAgICAgICAgICAgICAgY29udGludWUKICAgICAgICAgICAgc29jayA9IHNvY2tldC5zb2NrZXQoc29ja2V0LkFGX0lORVQsIHNvY2tldC5TT0NLX1NUUkVBTSkKICAgICAgICAgICAgdHJ5OgogICAgICAgICAgICAgICAgc29jay5iaW5kKCgiMTI3LjAuMC4xIiwgcG9ydCkpCiAgICAgICAgICAgICAgICBzb2NrLmxpc3RlbigxKQogICAgICAgICAgICBleGNlcHQgT1NFcnJvcjoKICAgICAgICAgICAgICAgIHNvY2suY2xvc2UoKQogICAgICAgICAgICBlbHNlOgogICAgICAgICAgICAgICAgc3F1YXR0ZXJzLmFwcGVuZChzb2NrKQogICAgICAgIHJldHVybiBhZGRyZXNzZXMKCiAgICBjbGFzcyBGYWtlUnVzdE1hbmFnZXI6CiAgICAgICAgcHJvY2Vzc2VzOiBsaXN0W0FueV0gPSBbXQoKICAgICAgICBkZWYgX19pbml0X18oc2VsZiwgKiprd2FyZ3MpOgogICAgICAgICAgICBzdGF0ZVsiaW5wdXRzIl0gPSBba3dhcmdzWyJpbnB1dF9hZGRyZXNzIl1dCiAgICAgICAgICAgIHN0YXRlWyJvdXRwdXRzIl0gPSBba3dhcmdzWyJvdXRwdXRfYWRkcmVzcyJdXQoKICAgICAgICBkZWYgc2h1dGRvd24oc2VsZiwgdGltZW91dD1Ob25lKToKICAgICAgICAgICAgcmV0dXJuIE5vbmUKCiAgICBhcmdzID0gYXJncGFyc2UuTmFtZXNwYWNlKAogICAgICAgIGhlYWRsZXNzPUZhbHNlLAogICAgICAgIGFwaV9zZXJ2ZXJfY291bnQ9c2VydmVycywKICAgICAgICBtb2RlbF9kaXI9bW9kZWxfZGlyLAogICAgICAgIHdvcmtlcl9kZWxheT13b3JrZXJfZGVsYXksCiAgICAgICAgdGNwPXRjcCwKICAgICkKICAgIHNlcnZlLnNldHVwX211bHRpcHJvY2Vzc19wcm9tZXRoZXVzID0gbGFtYmRhOiBOb25lCiAgICBzZXJ2ZS5zZXR1cF9zZXJ2ZXIgPSBsYW1iZGEgX2FyZ3M6ICgiMTI3LjAuMC4xOjAiLCBOb25lKQogICAgdmxsbS5Bc3luY0VuZ2luZUFyZ3MgPSBGYWtlQXN5bmNFbmdpbmVBcmdzCiAgICBzZXJ2ZS5FeGVjdXRvci5nZXRfY2xhc3MgPSBzdGF0aWNtZXRob2QobGFtYmRhIF9jb25maWc6IG9iamVjdCkKICAgIHNlcnZlLmxhdW5jaF9jb3JlX2VuZ2luZXMgPSBmYWtlX2xhdW5jaAogICAgc2VydmUud2FpdF9mb3JfY29tcGxldGlvbl9vcl9mYWlsdXJlID0gZmFrZV93YWl0CiAgICBlbmdpbmVfdXRpbHMuZ2V0X2VuZ2luZV96bXFfYWRkcmVzc2VzID0gcHJlc3N1cmVkX2FkZHJlc3NlcwogICAgcHJvY2Vzc191dGlscy5ydW5fYXBpX3NlcnZlcl93b3JrZXJfcHJvYyA9ICgKICAgICAgICBjcmFzaGluZ193b3JrZXIgaWYgbW9kZSA9PSAiY3Jhc2giIGVsc2UgbXBjbGllbnRfd29ya2VyCiAgICApCiAgICBpZiBtb2RlID09ICJydXN0IjoKICAgICAgICBzZXJ2ZS5lbnZzLlZMTE1fUlVTVF9GUk9OVEVORF9QQVRIID0gIi90bXAvZmFrZS12bGxtLXJzIgogICAgICAgIHNlcnZlLlJ1c3RGcm9udGVuZFByb2Nlc3NNYW5hZ2VyID0gRmFrZVJ1c3RNYW5hZ2VyCiAgICBlbHNlOgogICAgICAgIHNlcnZlLmVudnMuVkxMTV9SVVNUX0ZST05URU5EX1BBVEggPSBOb25lCgogICAgc3RhcnRlZCA9IHRpbWUubW9ub3RvbmljKCkKICAgIHRyeToKICAgICAgICBzZXJ2ZS5ydW5fbXVsdGlfYXBpX3NlcnZlcihhcmdzKQogICAgZXhjZXB0IEJhc2VFeGNlcHRpb24gYXMgZXhjOgogICAgICAgIHJlc3VsdDogZGljdFtzdHIsIEFueV0gPSB7CiAgICAgICAgICAgICJzdGF0dXMiOiAiZXJyb3IiLAogICAgICAgICAgICAiZXJyb3JfdHlwZSI6IHR5cGUoZXhjKS5fX25hbWVfXywKICAgICAgICAgICAgImVycm9yIjogc3RyKGV4YyksCiAgICAgICAgfQogICAgZWxzZToKICAgICAgICByZXN1bHQgPSB7InN0YXR1cyI6ICJvayJ9CiAgICBmaW5hbGx5OgogICAgICAgIGZvciBzb2NrIGluIHNxdWF0dGVyczoKICAgICAgICAgICAgc29jay5jbG9zZSgpCiAgICAgICAgdmxsbS5Bc3luY0VuZ2luZUFyZ3MgPSBvcmlnaW5hbF9hc3luY19lbmdpbmVfYXJncwogICAgICAgIHNlcnZlLkV4ZWN1dG9yLmdldF9jbGFzcyA9IG9yaWdpbmFsX2V4ZWN1dG9yX2dldF9jbGFzcwogICAgICAgIHNlcnZlLnNldHVwX211bHRpcHJvY2Vzc19wcm9tZXRoZXVzID0gb3JpZ2luYWxfc2V0dXBfcHJvbWV0aGV1cwogICAgICAgIHNlcnZlLnNldHVwX3NlcnZlciA9IG9yaWdpbmFsX3NldHVwX3NlcnZlcgogICAgICAgIHNlcnZlLmxhdW5jaF9jb3JlX2VuZ2luZXMgPSBvcmlnaW5hbF9sYXVuY2gKICAgICAgICBzZXJ2ZS53YWl0X2Zvcl9jb21wbGV0aW9uX29yX2ZhaWx1cmUgPSBvcmlnaW5hbF93YWl0CiAgICAgICAgZW5naW5lX3V0aWxzLmdldF9lbmdpbmVfem1xX2FkZHJlc3NlcyA9IG9yaWdpbmFsX2FkZHJlc3NlcwogICAgICAgIHByb2Nlc3NfdXRpbHMucnVuX2FwaV9zZXJ2ZXJfd29ya2VyX3Byb2MgPSBvcmlnaW5hbF93b3JrZXIKICAgICAgICBzZXJ2ZS5lbnZzLlZMTE1fUlVTVF9GUk9OVEVORF9QQVRIID0gb3JpZ2luYWxfcnVzdF9wYXRoCiAgICAgICAgc2VydmUuUnVzdEZyb250ZW5kUHJvY2Vzc01hbmFnZXIgPSBvcmlnaW5hbF9ydXN0X21hbmFnZXIKICAgIHJlc3VsdFsiZWxhcHNlZF9zZWNvbmRzIl0gPSB0aW1lLm1vbm90b25pYygpIC0gc3RhcnRlZAogICAgcmVzdWx0WyJtb2RlIl0gPSBtb2RlCiAgICByZXN1bHRbInNlcnZlcnMiXSA9IHNlcnZlcnMKICAgIHJlc3VsdFsiaW5wdXRzIl0gPSBzdGF0ZS5nZXQoImlucHV0cyIsIFtdKQogICAgcmVzdWx0WyJvdXRwdXRzIl0gPSBzdGF0ZS5nZXQoIm91dHB1dHMiLCBbXSkKICAgIHJlc3VsdFsicG9ydHMiXSA9IFsKICAgICAgICBfcG9ydCh1cmkpIGZvciB1cmkgaW4gWypyZXN1bHRbImlucHV0cyJdLCAqcmVzdWx0WyJvdXRwdXRzIl1dCiAgICBdCiAgICByZXR1cm4gcmVzdWx0Cg== | base64 -d > /opt/repro/port_harness.py && install -d /opt/repro \
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGpzb24KCmZyb20gcG9ydF9oYXJuZXNzIGltcG9ydCBydW5fc2NlbmFyaW8KCgpkZWYgbWFpbigpIC0+IGludDoKICAgIGF0dGVtcHRzID0gW3J1bl9zY2VuYXJpbygicmFjZSIsIHNlcnZlcnM9NCkgZm9yIF8gaW4gcmFuZ2UoNCldCiAgICBwcmludChqc29uLmR1bXBzKGF0dGVtcHRzLCBpbmRlbnQ9MikpCiAgICBwYXNzZWQgPSBhbGwoCiAgICAgICAgaXRlbVsic3RhdHVzIl0gPT0gIm9rIgogICAgICAgIGFuZCBsZW4oaXRlbVsicG9ydHMiXSkgPT0gOAogICAgICAgIGFuZCBhbGwocG9ydCA+IDAgZm9yIHBvcnQgaW4gaXRlbVsicG9ydHMiXSkKICAgICAgICBhbmQgbGVuKHNldChpdGVtWyJwb3J0cyJdKSkgPT0gOAogICAgICAgIGZvciBpdGVtIGluIGF0dGVtcHRzCiAgICApCiAgICBwcmludChmIm11bHRpX2FwaV9zdGFydHVwX2NvbnRyYWN0PXtwYXNzZWR9IikKICAgIHJldHVybiAwIGlmIHBhc3NlZCBlbHNlIDMKCgppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOgogICAgcmFpc2UgU3lzdGVtRXhpdChtYWluKCkpCg== | base64 -d > /opt/repro/port_startup_trace.py
LABEL ai.infra.bench.environment-template=vllm-harbor-all-in-one \
      ai.infra.bench.base-commit=$VLLM_BASE_SHA \
      ai.infra.bench.dependency-cutoff=$VLLM_DEPENDENCY_CUTOFF \
      ai.infra.bench.cache-namespace=$VLLM_CACHE_NAMESPACE
ENTRYPOINT []
CMD ["sleep", "infinity"]
