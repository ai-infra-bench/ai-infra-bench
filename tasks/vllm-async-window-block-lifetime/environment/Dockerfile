# syntax=docker/dockerfile:1
# Template inputs below are replaced from task.toml by generate.py. Generated
# task Dockerfiles are self-contained and differ only in their frozen inputs.

ARG VLLM_BASE_SHA=934eeaecfb13c4e5d5aa5a4a420cff35f5bd9821
ARG VLLM_DEPENDENCY_CUTOFF=2026-07-08T12:12:54Z
ARG VLLM_CACHE_NAMESPACE=934eeaecfb13c4e5d5aa5a4a420cff35f5bd9821-082a6a2e18de08af-2f1688856bf1e683
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

ARG CARGO_NEXTEST_VERSION=0.9.140
RUN case "$TARGETARCH" in \
      amd64) nextest_target=x86_64-unknown-linux-gnu; nextest_sha=4ee9aaa0d0171a985a5d0eb735b87355894c1c455972e9674fb9fdbd1387c9a3 ;; \
      arm64) nextest_target=aarch64-unknown-linux-gnu; nextest_sha=8b3f4d4560b6b0f83774fecc6be07e47716dbad0eb0bb6c3890f478f4affe4b6 ;; \
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
# Exact task dependency lock (sha256:082a6a2e18de08af5d9c40756a8ca8c14c152daa6958c1072ba9095be3fd78a1) is embedded so this
# Dockerfile remains independently buildable with an empty context.
RUN --mount=type=cache,id=vllm-uv-downloads-v3,target=/root/.cache/uv,sharing=locked <<'VLLM_INSTALL_EOF'
set -eu
cat > /tmp/vllm-requirements.lock <<'VLLM_REQUIREMENTS_EOF'
# Generated with uv 0.11.28 from the pinned base requirements and task
# extras for CPython 3.12 on x86_64 manylinux_2_28. Packages newer than
# 2026-07-08T12:12:54Z were excluded during resolution.
aiohappyeyeballs==2.7.1
    # via aiohttp
aiohttp==3.14.1
    # via -r requirements/common.txt
aiosignal==1.4.0
    # via aiohttp
annotated-doc==0.0.4
    # via
    #   fastapi
    #   typer
annotated-types==0.7.0
    # via pydantic
anthropic==0.116.0
    # via -r requirements/common.txt
anyio==4.14.1
    # via
    #   anthropic
    #   httpx
    #   mcp
    #   openai
    #   sse-starlette
    #   starlette
    #   watchfiles
apache-tvm-ffi==0.1.12
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
cachetools==7.1.4
    # via -r requirements/common.txt
cbor2==6.1.3
    # via -r requirements/common.txt
certifi==2026.6.17
    # via
    #   httpcore
    #   httpx
    #   requests
    #   sentry-sdk
cffi==2.1.0
    # via cryptography
charset-normalizer==3.4.9
    # via requests
click==8.4.2
    # via
    #   huggingface-hub
    #   rich-toolkit
    #   uvicorn
cloudpickle==3.1.2
    # via -r requirements/common.txt
cmake==4.3.4
    # via -r requirements/build/cpu.txt
compressed-tensors==0.17.0
    # via -r requirements/common.txt
cryptography==49.0.0
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
fastapi-cli==0.0.28
    # via fastapi
fastapi-cloud-cli==0.22.1
    # via fastapi-cli
fastar==0.11.0
    # via
    #   fastapi
    #   fastapi-cloud-cli
filelock==3.29.7
    # via
    #   -r requirements/common.txt
    #   huggingface-hub
    #   torch
frozenlist==1.8.0
    # via
    #   aiohttp
    #   aiosignal
fsspec==2026.6.0
    # via
    #   huggingface-hub
    #   torch
googleapis-common-protos==1.75.0
    # via
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
grpcio==1.81.1
    # via opentelemetry-exporter-otlp-proto-grpc
h11==0.16.0
    # via
    #   httpcore
    #   uvicorn
hf-xet==1.5.1
    # via huggingface-hub
httpcore==1.0.9
    # via httpx
httptools==0.8.0
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
huggingface-hub==1.22.0
    # via
    #   tokenizers
    #   transformers
idna==3.18
    # via
    #   anyio
    #   email-validator
    #   httpx
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
mcp==1.28.1
    # via -r requirements/common.txt
mdurl==0.1.2
    # via markdown-it-py
mistral-common==1.11.5
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
ninja==1.13.0
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
openai==2.44.0
    # via -r requirements/common.txt
openai-harmony==0.0.8
    # via -r requirements/common.txt
opencv-python-headless==5.0.0.93
    # via
    #   -r requirements/common.txt
    #   mistral-common
opentelemetry-api==1.43.0
    # via
    #   -r requirements/common.txt
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
    #   opentelemetry-sdk
    #   opentelemetry-semantic-conventions
opentelemetry-exporter-otlp==1.43.0
    # via -r requirements/common.txt
opentelemetry-exporter-otlp-proto-common==1.43.0
    # via
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
opentelemetry-exporter-otlp-proto-grpc==1.43.0
    # via opentelemetry-exporter-otlp
opentelemetry-exporter-otlp-proto-http==1.43.0
    # via opentelemetry-exporter-otlp
opentelemetry-proto==1.43.0
    # via
    #   opentelemetry-exporter-otlp-proto-common
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
opentelemetry-sdk==1.43.0
    # via
    #   -r requirements/common.txt
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
    #   opentelemetry-semantic-conventions-ai
opentelemetry-semantic-conventions==0.64b0
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
pillow==12.3.0
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
prometheus-fastapi-instrumentator==8.0.2
    # via -r requirements/common.txt
propcache==0.5.2
    # via
    #   aiohttp
    #   yarl
protobuf==7.35.1
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
pydantic-settings==2.14.2
    # via
    #   fastapi
    #   mcp
pygments==2.20.0
    # via
    #   pytest
    #   rich
pyjwt==2.13.0
    # via mcp
pytest==9.1.1
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
pyzmq==27.1.0
    # via -r requirements/common.txt
referencing==0.37.0
    # via
    #   jsonschema
    #   jsonschema-specifications
regex==2026.6.28
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
rich-toolkit==0.20.1
    # via
    #   fastapi-cli
    #   fastapi-cloud-cli
rignore==0.7.6
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
sentencepiece==0.2.1
    # via -r requirements/common.txt
sentry-sdk==2.64.0
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
setuptools-scm==10.2.0
    # via -r requirements/build/cpu.txt
shellingham==1.5.4
    # via typer
six==1.17.0
    # via -r requirements/common.txt
sniffio==1.3.1
    # via
    #   anthropic
    #   openai
sse-starlette==3.4.5
    # via mcp
starlette==1.3.1
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
torchcodec==0.14.0+cpu
    # via -r requirements/cpu.txt
torchvision==0.26.0+cpu
    # via -r requirements/cpu.txt
tqdm==4.68.4
    # via
    #   -r requirements/common.txt
    #   huggingface-hub
    #   openai
    #   transformers
transformers==5.13.0
    # via
    #   -r requirements/common.txt
    #   compressed-tensors
    #   xgrammar
triton==3.7.1
    # via xgrammar
typer==0.26.8
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
uvicorn==0.51.0
    # via
    #   fastapi
    #   fastapi-cli
    #   fastapi-cloud-cli
    #   mcp
uvloop==0.22.1
    # via uvicorn
vcs-versioning==2.2.2
    # via setuptools-scm
watchfiles==1.2.0
    # via
    #   -r requirements/common.txt
    #   uvicorn
websockets==16.0
    # via uvicorn
wheel==0.47.0
    # via -r requirements/build/cpu.txt
xgrammar==0.2.3
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
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGpzb24KaW1wb3J0IHRlbXBmaWxlCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAoKZnJvbSBzY2hlZHVsZXJfZml4dHVyZSBpbXBvcnQgKAogICAgYXN5bmNfZnJlZV90aW1lbGluZSwKICAgIGNvbXBldGluZ19sb2FkX3JldXNlLAogICAgc3BlY3VsYXRpdmVfcm9sbGJhY2tfd2luZG93LAogICAgc3luY19mcmVlX3RpbWVsaW5lLAopCgoKZGVmIG1haW4oKSAtPiBpbnQ6CiAgICByb290ID0gUGF0aCh0ZW1wZmlsZS5ta2R0ZW1wKHByZWZpeD0iYXN5bmMtd2luZG93LXRyYWNlLSIpKQogICAgYXN5bmNfc3dhID0gYXN5bmNfZnJlZV90aW1lbGluZShyb290IC8gImFzeW5jLXN3YSIsICJzd2EiKQogICAgYXN5bmNfY2h1bmtlZCA9IGFzeW5jX2ZyZWVfdGltZWxpbmUocm9vdCAvICJhc3luYy1jaHVua2VkIiwgImNodW5rZWQiKQogICAgc3luY19zd2EgPSBzeW5jX2ZyZWVfdGltZWxpbmUocm9vdCAvICJzeW5jLXN3YSIsICJzd2EiKQogICAgbG9hZF9yZXVzZSA9IGNvbXBldGluZ19sb2FkX3JldXNlKHJvb3QgLyAibG9hZC1yZXVzZSIsICJzd2EiKQogICAgcm9sbGJhY2sgPSBzcGVjdWxhdGl2ZV9yb2xsYmFja193aW5kb3coCiAgICAgICAgcm9vdCAvICJyb2xsYmFjayIsCiAgICAgICAgInN3YSIsCiAgICAgICAgcm9sbGJhY2tfdG9rZW5zPTMyLAogICAgKQogICAgcHJpbnQoCiAgICAgICAganNvbi5kdW1wcygKICAgICAgICAgICAgewogICAgICAgICAgICAgICAgImFzeW5jX3N3YSI6IGFzeW5jX3N3YSwKICAgICAgICAgICAgICAgICJhc3luY19jaHVua2VkIjogYXN5bmNfY2h1bmtlZCwKICAgICAgICAgICAgICAgICJzeW5jX3N3YSI6IHN5bmNfc3dhLAogICAgICAgICAgICAgICAgImxvYWRfcmV1c2UiOiBsb2FkX3JldXNlLAogICAgICAgICAgICAgICAgInNwZWN1bGF0aXZlX3JvbGxiYWNrIjogcm9sbGJhY2ssCiAgICAgICAgICAgIH0sCiAgICAgICAgICAgIGluZGVudD0yLAogICAgICAgICkKICAgICkKICAgIGNvcnJlY3QgPSAoCiAgICAgICAgYXN5bmNfc3dhWyJiZWZvcmVfcHJvY2VzcyJdID09IGFzeW5jX3N3YVsiYWZ0ZXJfcHJlZmlsbCJdCiAgICAgICAgYW5kIGFzeW5jX2NodW5rZWRbImJlZm9yZV9wcm9jZXNzIl0gPT0gYXN5bmNfY2h1bmtlZFsiYWZ0ZXJfcHJlZmlsbCJdCiAgICAgICAgYW5kIHN5bmNfc3dhWyJhZnRlcl9kZWNvZGUiXSA+IHN5bmNfc3dhWyJiZWZvcmVfZGVjb2RlIl0KICAgICAgICBhbmQgbm90IGxvYWRfcmV1c2VbInByZW1hdHVyZV9vdmVybGFwIl0KICAgICAgICBhbmQgcm9sbGJhY2tbInJlcXVpcmVkX2Jsb2Nrc19yZXRhaW5lZCJdCiAgICApCiAgICBwcmludChmImluZmxpZ2h0X3dpbmRvd19saWZldGltZV9jb250cmFjdD17Y29ycmVjdH0iKQogICAgcmV0dXJuIDAgaWYgY29ycmVjdCBlbHNlIDMKCgppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOgogICAgcmFpc2UgU3lzdGVtRXhpdChtYWluKCkpCg== | base64 -d > /opt/repro/async_window_trace.py && install -d /opt/repro \
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGpzb24KZnJvbSBwYXRobGliIGltcG9ydCBQYXRoCmltcG9ydCB0b3JjaAoKZnJvbSB2bGxtLmNvbmZpZyBpbXBvcnQgQ2FjaGVDb25maWcsIE1vZGVsQ29uZmlnLCBTY2hlZHVsZXJDb25maWcsIFZsbG1Db25maWcKZnJvbSB2bGxtLnNhbXBsaW5nX3BhcmFtcyBpbXBvcnQgU2FtcGxpbmdQYXJhbXMKZnJvbSB2bGxtLnV0aWxzLmhhc2hpbmcgaW1wb3J0IHNoYTI1Ngpmcm9tIHZsbG0udjEuY29yZS5rdl9jYWNoZV91dGlscyBpbXBvcnQgZ2V0X3JlcXVlc3RfYmxvY2tfaGFzaGVyLCBpbml0X25vbmVfaGFzaApmcm9tIHZsbG0udjEuY29yZS5zY2hlZC5hc3luY19zY2hlZHVsZXIgaW1wb3J0IEFzeW5jU2NoZWR1bGVyCmZyb20gdmxsbS52MS5jb3JlLnNjaGVkLnNjaGVkdWxlciBpbXBvcnQgU2NoZWR1bGVyCmZyb20gdmxsbS52MS5jb3JlLnNpbmdsZV90eXBlX2t2X2NhY2hlX21hbmFnZXIgaW1wb3J0IHJlZ2lzdGVyX2FsbF9rdmNhY2hlX3NwZWNzCmZyb20gdmxsbS52MS5rdl9jYWNoZV9pbnRlcmZhY2UgaW1wb3J0ICgKICAgIENodW5rZWRMb2NhbEF0dGVudGlvblNwZWMsCiAgICBGdWxsQXR0ZW50aW9uU3BlYywKICAgIEtWQ2FjaGVDb25maWcsCiAgICBLVkNhY2hlR3JvdXBTcGVjLAogICAgU2xpZGluZ1dpbmRvd1NwZWMsCikKZnJvbSB2bGxtLnYxLm91dHB1dHMgaW1wb3J0IE1vZGVsUnVubmVyT3V0cHV0CmZyb20gdmxsbS52MS5yZXF1ZXN0IGltcG9ydCBSZXF1ZXN0LCBSZXF1ZXN0U3RhdHVzCmZyb20gdmxsbS52MS5zdHJ1Y3R1cmVkX291dHB1dCBpbXBvcnQgU3RydWN0dXJlZE91dHB1dE1hbmFnZXIKCgpCTE9DS19TSVpFID0gMTYKUFJPTVBUX1RPS0VOUyA9IDEwMApfaGFzaF9yZWFkeSA9IEZhbHNlCgoKZGVmIHRpbnlfbW9kZWwocGF0aDogUGF0aCkgLT4gc3RyOgogICAgcGF0aC5ta2RpcihwYXJlbnRzPVRydWUsIGV4aXN0X29rPVRydWUpCiAgICBjb25maWcgPSBwYXRoIC8gImNvbmZpZy5qc29uIgogICAgaWYgbm90IGNvbmZpZy5leGlzdHMoKToKICAgICAgICBjb25maWcud3JpdGVfdGV4dCgKICAgICAgICAgICAganNvbi5kdW1wcygKICAgICAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgICAgICAiYXJjaGl0ZWN0dXJlcyI6IFsiT1BURm9yQ2F1c2FsTE0iXSwKICAgICAgICAgICAgICAgICAgICAibW9kZWxfdHlwZSI6ICJvcHQiLAogICAgICAgICAgICAgICAgICAgICJoaWRkZW5fc2l6ZSI6IDY0LAogICAgICAgICAgICAgICAgICAgICJmZm5fZGltIjogMTI4LAogICAgICAgICAgICAgICAgICAgICJudW1fYXR0ZW50aW9uX2hlYWRzIjogNCwKICAgICAgICAgICAgICAgICAgICAibnVtX2hpZGRlbl9sYXllcnMiOiAxLAogICAgICAgICAgICAgICAgICAgICJ2b2NhYl9zaXplIjogMTI4LAogICAgICAgICAgICAgICAgICAgICJtYXhfcG9zaXRpb25fZW1iZWRkaW5ncyI6IDUxMiwKICAgICAgICAgICAgICAgICAgICAid29yZF9lbWJlZF9wcm9qX2RpbSI6IDY0LAogICAgICAgICAgICAgICAgfQogICAgICAgICAgICApCiAgICAgICAgKQogICAgcmV0dXJuIHN0cihwYXRoKQoKCmRlZiBzcGVjKGtpbmQ6IHN0cik6CiAgICBjb21tb24gPSB7CiAgICAgICAgImJsb2NrX3NpemUiOiBCTE9DS19TSVpFLAogICAgICAgICJudW1fa3ZfaGVhZHMiOiAxLAogICAgICAgICJoZWFkX3NpemUiOiAxLAogICAgICAgICJkdHlwZSI6IHRvcmNoLmZsb2F0MzIsCiAgICB9CiAgICBpZiBraW5kID09ICJzd2EiOgogICAgICAgIHJldHVybiBTbGlkaW5nV2luZG93U3BlYygqKmNvbW1vbiwgc2xpZGluZ193aW5kb3c9MTYpCiAgICBpZiBraW5kID09ICJjaHVua2VkIjoKICAgICAgICByZXR1cm4gQ2h1bmtlZExvY2FsQXR0ZW50aW9uU3BlYygqKmNvbW1vbiwgYXR0ZW50aW9uX2NodW5rX3NpemU9MzIpCiAgICBpZiBraW5kID09ICJmdWxsIjoKICAgICAgICByZXR1cm4gRnVsbEF0dGVudGlvblNwZWMoKipjb21tb24pCiAgICByYWlzZSBBc3NlcnRpb25FcnJvcihraW5kKQoKCmRlZiBtYWtlX3ZsbG1fY29uZmlnKHBhdGg6IFBhdGgsICosIGFzeW5jX3NjaGVkdWxpbmc6IGJvb2wpIC0+IFZsbG1Db25maWc6CiAgICBtb2RlbCA9IE1vZGVsQ29uZmlnKAogICAgICAgIG1vZGVsPXRpbnlfbW9kZWwocGF0aCksCiAgICAgICAgZHR5cGU9ImZsb2F0MTYiLAogICAgICAgIHNraXBfdG9rZW5pemVyX2luaXQ9VHJ1ZSwKICAgICkKICAgIGNvbmZpZyA9IFZsbG1Db25maWcoCiAgICAgICAgbW9kZWxfY29uZmlnPW1vZGVsLAogICAgICAgIHNjaGVkdWxlcl9jb25maWc9U2NoZWR1bGVyQ29uZmlnKAogICAgICAgICAgICBtYXhfbnVtX3NlcXM9OCwKICAgICAgICAgICAgbWF4X251bV9iYXRjaGVkX3Rva2Vucz0yNTYsCiAgICAgICAgICAgIG1heF9tb2RlbF9sZW49NTEyLAogICAgICAgICAgICBlbmFibGVfY2h1bmtlZF9wcmVmaWxsPVRydWUsCiAgICAgICAgICAgIGFzeW5jX3NjaGVkdWxpbmc9YXN5bmNfc2NoZWR1bGluZywKICAgICAgICAgICAgaXNfZW5jb2Rlcl9kZWNvZGVyPW1vZGVsLmlzX2VuY29kZXJfZGVjb2RlciwKICAgICAgICAgICAgd2F0ZXJtYXJrPTAuMCwKICAgICAgICApLAogICAgICAgIGNhY2hlX2NvbmZpZz1DYWNoZUNvbmZpZygKICAgICAgICAgICAgYmxvY2tfc2l6ZT1CTE9DS19TSVpFLAogICAgICAgICAgICBncHVfbWVtb3J5X3V0aWxpemF0aW9uPTAuOSwKICAgICAgICAgICAgY2FjaGVfZHR5cGU9ImF1dG8iLAogICAgICAgICAgICBlbmFibGVfcHJlZml4X2NhY2hpbmc9RmFsc2UsCiAgICAgICAgKSwKICAgICkKICAgIGNvbmZpZy5zY2hlZHVsZXJfY29uZmlnLmFzeW5jX3NjaGVkdWxpbmcgPSBhc3luY19zY2hlZHVsaW5nCiAgICByZXR1cm4gY29uZmlnCgoKZGVmIG1ha2Vfc2NoZWR1bGVyKHBhdGg6IFBhdGgsIGtpbmQ6IHN0ciwgKiwgYXN5bmNfc2NoZWR1bGluZzogYm9vbCk6CiAgICBjb25maWcgPSBtYWtlX3ZsbG1fY29uZmlnKHBhdGgsIGFzeW5jX3NjaGVkdWxpbmc9YXN5bmNfc2NoZWR1bGluZykKICAgIGNvbmZpZy5jYWNoZV9jb25maWcubnVtX2dwdV9ibG9ja3MgPSAxMjgKICAgIGt2X2NvbmZpZyA9IEtWQ2FjaGVDb25maWcoCiAgICAgICAgbnVtX2Jsb2Nrcz0xMjgsCiAgICAgICAga3ZfY2FjaGVfdGVuc29ycz1bXSwKICAgICAgICBrdl9jYWNoZV9ncm91cHM9W0tWQ2FjaGVHcm91cFNwZWMoWyJsYXllciJdLCBzcGVjKGtpbmQpKV0sCiAgICApCiAgICByZWdpc3Rlcl9hbGxfa3ZjYWNoZV9zcGVjcyhjb25maWcpCiAgICBjbHMgPSBBc3luY1NjaGVkdWxlciBpZiBhc3luY19zY2hlZHVsaW5nIGVsc2UgU2NoZWR1bGVyCiAgICByZXR1cm4gKAogICAgICAgIGNscygKICAgICAgICAgICAgdmxsbV9jb25maWc9Y29uZmlnLAogICAgICAgICAgICBrdl9jYWNoZV9jb25maWc9a3ZfY29uZmlnLAogICAgICAgICAgICBibG9ja19zaXplPUJMT0NLX1NJWkUsCiAgICAgICAgICAgIGxvZ19zdGF0cz1UcnVlLAogICAgICAgICAgICBzdHJ1Y3R1cmVkX291dHB1dF9tYW5hZ2VyPVN0cnVjdHVyZWRPdXRwdXRNYW5hZ2VyKGNvbmZpZyksCiAgICAgICAgKSwKICAgICAgICBjb25maWcsCiAgICApCgoKZGVmIG1ha2VfcmVxdWVzdChuYW1lOiBzdHIsICosIG1heF90b2tlbnM6IGludCA9IDgpIC0+IFJlcXVlc3Q6CiAgICBnbG9iYWwgX2hhc2hfcmVhZHkKICAgIGlmIG5vdCBfaGFzaF9yZWFkeToKICAgICAgICBpbml0X25vbmVfaGFzaChzaGEyNTYpCiAgICAgICAgX2hhc2hfcmVhZHkgPSBUcnVlCiAgICBwYXJhbXMgPSBTYW1wbGluZ1BhcmFtcyhtYXhfdG9rZW5zPW1heF90b2tlbnMpCiAgICBwYXJhbXMudXBkYXRlX2Zyb21fZ2VuZXJhdGlvbl9jb25maWcoe30sIDEyNykKICAgIHJldHVybiBSZXF1ZXN0KAogICAgICAgIHJlcXVlc3RfaWQ9bmFtZSwKICAgICAgICBwcm9tcHRfdG9rZW5faWRzPVsxXSAqIFBST01QVF9UT0tFTlMsCiAgICAgICAgc2FtcGxpbmdfcGFyYW1zPXBhcmFtcywKICAgICAgICBwb29saW5nX3BhcmFtcz1Ob25lLAogICAgICAgIGJsb2NrX2hhc2hlcj1nZXRfcmVxdWVzdF9ibG9ja19oYXNoZXIoQkxPQ0tfU0laRSwgc2hhMjU2KSwKICAgICkKCgpkZWYgcnVubmVyX291dHB1dChzY2hlZHVsZXJfb3V0cHV0KSAtPiBNb2RlbFJ1bm5lck91dHB1dDoKICAgIGlkcyA9IGxpc3Qoc2NoZWR1bGVyX291dHB1dC5udW1fc2NoZWR1bGVkX3Rva2VucykKICAgIHJldHVybiBNb2RlbFJ1bm5lck91dHB1dCgKICAgICAgICByZXFfaWRzPWlkcywKICAgICAgICByZXFfaWRfdG9faW5kZXg9e25hbWU6IGluZGV4IGZvciBpbmRleCwgbmFtZSBpbiBlbnVtZXJhdGUoaWRzKX0sCiAgICAgICAgc2FtcGxlZF90b2tlbl9pZHM9W1sxXV0gKiBsZW4oaWRzKSwKICAgICAgICBsb2dwcm9icz1Ob25lLAogICAgICAgIHByb21wdF9sb2dwcm9ic19kaWN0PXt9LAogICAgICAgIHBvb2xlcl9vdXRwdXQ9W10sCiAgICApCgoKZGVmIGJsb2NrX2lkcyhzY2hlZHVsZXIsIHJlcXVlc3RfaWQ6IHN0cikgLT4gbGlzdFtpbnRdOgogICAgcmV0dXJuIGxpc3Qoc2NoZWR1bGVyLmt2X2NhY2hlX21hbmFnZXIuZ2V0X2Jsb2NrX2lkcyhyZXF1ZXN0X2lkKVswXSkKCgpkZWYgYXN5bmNfZnJlZV90aW1lbGluZShwYXRoOiBQYXRoLCBraW5kOiBzdHIpIC0+IGRpY3Rbc3RyLCBpbnRdOgogICAgc2NoZWR1bGVyLCBfID0gbWFrZV9zY2hlZHVsZXIocGF0aCwga2luZCwgYXN5bmNfc2NoZWR1bGluZz1UcnVlKQogICAgaXRlbSA9IG1ha2VfcmVxdWVzdChmIntraW5kfS1hc3luYyIpCiAgICBzY2hlZHVsZXIuYWRkX3JlcXVlc3QoaXRlbSkKICAgIHBvb2wgPSBzY2hlZHVsZXIua3ZfY2FjaGVfbWFuYWdlci5ibG9ja19wb29sCiAgICBwcmVmaWxsID0gc2NoZWR1bGVyLnNjaGVkdWxlKCkKICAgIGFmdGVyX3ByZWZpbGwgPSBwb29sLmdldF9udW1fZnJlZV9ibG9ja3MoKQogICAgZGVjb2RlID0gc2NoZWR1bGVyLnNjaGVkdWxlKCkKICAgIGJlZm9yZV9wcm9jZXNzID0gcG9vbC5nZXRfbnVtX2ZyZWVfYmxvY2tzKCkKICAgIHNjaGVkdWxlci51cGRhdGVfZnJvbV9vdXRwdXQocHJlZmlsbCwgcnVubmVyX291dHB1dChwcmVmaWxsKSkKICAgIHNjaGVkdWxlci5zY2hlZHVsZSgpCiAgICBhZnRlcl9wcm9jZXNzID0gcG9vbC5nZXRfbnVtX2ZyZWVfYmxvY2tzKCkKICAgIHNjaGVkdWxlci51cGRhdGVfZnJvbV9vdXRwdXQoZGVjb2RlLCBydW5uZXJfb3V0cHV0KGRlY29kZSkpCiAgICBzY2hlZHVsZXIuc2NoZWR1bGUoKQogICAgYWZ0ZXJfbmV4dCA9IHBvb2wuZ2V0X251bV9mcmVlX2Jsb2NrcygpCiAgICByZXR1cm4gewogICAgICAgICJhZnRlcl9wcmVmaWxsIjogYWZ0ZXJfcHJlZmlsbCwKICAgICAgICAiYmVmb3JlX3Byb2Nlc3MiOiBiZWZvcmVfcHJvY2VzcywKICAgICAgICAiYWZ0ZXJfcHJvY2VzcyI6IGFmdGVyX3Byb2Nlc3MsCiAgICAgICAgImFmdGVyX25leHQiOiBhZnRlcl9uZXh0LAogICAgfQoKCmRlZiBzeW5jX2ZyZWVfdGltZWxpbmUocGF0aDogUGF0aCwga2luZDogc3RyKSAtPiBkaWN0W3N0ciwgaW50XToKICAgIHNjaGVkdWxlciwgXyA9IG1ha2Vfc2NoZWR1bGVyKHBhdGgsIGtpbmQsIGFzeW5jX3NjaGVkdWxpbmc9RmFsc2UpCiAgICBpdGVtID0gbWFrZV9yZXF1ZXN0KGYie2tpbmR9LXN5bmMiKQogICAgc2NoZWR1bGVyLmFkZF9yZXF1ZXN0KGl0ZW0pCiAgICBwb29sID0gc2NoZWR1bGVyLmt2X2NhY2hlX21hbmFnZXIuYmxvY2tfcG9vbAogICAgcHJlZmlsbCA9IHNjaGVkdWxlci5zY2hlZHVsZSgpCiAgICBzY2hlZHVsZXIudXBkYXRlX2Zyb21fb3V0cHV0KHByZWZpbGwsIHJ1bm5lcl9vdXRwdXQocHJlZmlsbCkpCiAgICBiZWZvcmVfZGVjb2RlID0gcG9vbC5nZXRfbnVtX2ZyZWVfYmxvY2tzKCkKICAgIHNjaGVkdWxlci5zY2hlZHVsZSgpCiAgICBhZnRlcl9kZWNvZGUgPSBwb29sLmdldF9udW1fZnJlZV9ibG9ja3MoKQogICAgcmV0dXJuIHsiYmVmb3JlX2RlY29kZSI6IGJlZm9yZV9kZWNvZGUsICJhZnRlcl9kZWNvZGUiOiBhZnRlcl9kZWNvZGV9CgoKZGVmIGNvbm5lY3Rvcl9oYW5kb2ZmX2Jsb2NrX2NvdW50KHBhdGg6IFBhdGgpIC0+IGludDoKICAgIHNjaGVkdWxlciwgXyA9IG1ha2Vfc2NoZWR1bGVyKHBhdGgsICJzd2EiLCBhc3luY19zY2hlZHVsaW5nPVRydWUpCiAgICBpdGVtID0gbWFrZV9yZXF1ZXN0KCJjb25uZWN0b3ItaGFuZG9mZiIpCiAgICBzY2hlZHVsZXIuYWRkX3JlcXVlc3QoaXRlbSkKICAgIHNjaGVkdWxlci5zY2hlZHVsZSgpCiAgICBzY2hlZHVsZXIuc2NoZWR1bGUoKQogICAgY2xhc3MgUmVjb3JkaW5nQ29ubmVjdG9yOgogICAgICAgIGRlZiBfX2luaXRfXyhzZWxmKSAtPiBOb25lOgogICAgICAgICAgICBzZWxmLmJsb2NrX2lkcyA9IE5vbmUKCiAgICAgICAgZGVmIHJlcXVlc3RfZmluaXNoZWQoc2VsZiwgX3JlcXVlc3QsIGJsb2NrX2lkcyk6CiAgICAgICAgICAgIHNlbGYuYmxvY2tfaWRzID0gYmxvY2tfaWRzCiAgICAgICAgICAgIHJldHVybiBGYWxzZSwgTm9uZQoKICAgIGNvbm5lY3RvciA9IFJlY29yZGluZ0Nvbm5lY3RvcigpCiAgICBzY2hlZHVsZXIuY29ubmVjdG9yID0gY29ubmVjdG9yCiAgICBzY2hlZHVsZXIuZmluaXNoX3JlcXVlc3RzKGl0ZW0ucmVxdWVzdF9pZCwgUmVxdWVzdFN0YXR1cy5GSU5JU0hFRF9BQk9SVEVEKQogICAgYXNzZXJ0IGNvbm5lY3Rvci5ibG9ja19pZHMgaXMgbm90IE5vbmUKICAgIHJldHVybiBsZW4oY29ubmVjdG9yLmJsb2NrX2lkcykKCgpkZWYgY29tcGV0aW5nX2xvYWRfcmV1c2UocGF0aDogUGF0aCwga2luZDogc3RyKSAtPiBkaWN0W3N0ciwgb2JqZWN0XToKICAgICIiIk1vZGVsIGFuIGV4dGVybmFsIGxvYWQgZGVzdGluYXRpb24gd2l0aCBhIGNvbXBldGluZyByZXF1ZXN0LgoKICAgIFRoZSB0YXJnZXQgc2NoZWR1bGVyIGFuZCByZWFsIGJsb2NrIHBvb2wgcnVuIHVuY2hhbmdlZC4gTW9kZWwgZXhlY3V0aW9uIGFuZAogICAgdGhlIGV4dGVybmFsIERNQSBhcmUgc3Vic3RpdHV0ZWQ6IGFsbG9jYXRpb24gdG8gYGBsb2FkLXRhcmdldGBgIHJlcHJlc2VudHMKICAgIHRoZSBjb25uZWN0b3IgY2hvb3NpbmcgZGVzdGluYXRpb24gYmxvY2tzIGZvciBhbiBpbmNvbWluZyBLViBsb2FkLgogICAgIiIiCiAgICBzY2hlZHVsZXIsIF8gPSBtYWtlX3NjaGVkdWxlcihwYXRoLCBraW5kLCBhc3luY19zY2hlZHVsaW5nPVRydWUpCiAgICByZWFkZXIgPSBtYWtlX3JlcXVlc3QoImluZmxpZ2h0LXJlYWRlciIsIG1heF90b2tlbnM9NjQpCiAgICBzY2hlZHVsZXIuYWRkX3JlcXVlc3QocmVhZGVyKQogICAgc2NoZWR1bGVyLnNjaGVkdWxlKCkKICAgIHJlYWRlcl9ibG9ja3MgPSBzZXQoYmxvY2tfaWRzKHNjaGVkdWxlciwgcmVhZGVyLnJlcXVlc3RfaWQpKQoKICAgICMgU2NoZWR1bGluZyBhZ2FpbiBiZWZvcmUgcHJvY2Vzc2luZyB0aGUgZmlyc3Qgb3V0cHV0IGlzIHRoZSB2dWxuZXJhYmxlCiAgICAjIG92ZXJsYXAuIEEgY29tcGV0aW5nIHJlcXVlc3QgdGhlbiBhc2tzIHRoZSBzYW1lIHJlYWwgYmxvY2sgcG9vbCBmb3IgbG9hZAogICAgIyBkZXN0aW5hdGlvbnMuCiAgICBzY2hlZHVsZXIuc2NoZWR1bGUoKQogICAgbG9hZF90YXJnZXQgPSBtYWtlX3JlcXVlc3QoImxvYWQtdGFyZ2V0IikKICAgIHNjaGVkdWxlci5hZGRfcmVxdWVzdChsb2FkX3RhcmdldCkKICAgIHNjaGVkdWxlci5zY2hlZHVsZSgpCiAgICBsb2FkX2Jsb2NrcyA9IHNldChibG9ja19pZHMoc2NoZWR1bGVyLCBsb2FkX3RhcmdldC5yZXF1ZXN0X2lkKSkKICAgIG92ZXJsYXAgPSBzb3J0ZWQocmVhZGVyX2Jsb2NrcyAmIGxvYWRfYmxvY2tzKQogICAgcmV0dXJuIHsKICAgICAgICAicmVhZGVyX2Jsb2NrcyI6IHNvcnRlZChyZWFkZXJfYmxvY2tzKSwKICAgICAgICAibG9hZF9ibG9ja3MiOiBzb3J0ZWQobG9hZF9ibG9ja3MpLAogICAgICAgICJwcmVtYXR1cmVfb3ZlcmxhcCI6IG92ZXJsYXAsCiAgICB9CgoKZGVmIHNwZWN1bGF0aXZlX3JvbGxiYWNrX3dpbmRvdygKICAgIHBhdGg6IFBhdGgsCiAgICBraW5kOiBzdHIsCiAgICAqLAogICAgcm9sbGJhY2tfdG9rZW5zOiBpbnQsCikgLT4gZGljdFtzdHIsIG9iamVjdF06CiAgICAiIiJJbmplY3QgYSBkZXRlcm1pbmlzdGljIHNwZWN1bGF0aXZlIHJlamVjdGlvbiBhdCB0aGUgc2NoZWR1bGVyIGJvdW5kYXJ5LiIiIgogICAgc2NoZWR1bGVyLCBfID0gbWFrZV9zY2hlZHVsZXIocGF0aCwga2luZCwgYXN5bmNfc2NoZWR1bGluZz1UcnVlKQogICAgaXRlbSA9IG1ha2VfcmVxdWVzdCgicm9sbGJhY2siLCBtYXhfdG9rZW5zPTY0KQogICAgc2NoZWR1bGVyLmFkZF9yZXF1ZXN0KGl0ZW0pCiAgICBzY2hlZHVsZXIuc2NoZWR1bGUoKQogICAgb3JpZ2luYWwgPSBibG9ja19pZHMoc2NoZWR1bGVyLCBpdGVtLnJlcXVlc3RfaWQpCgogICAgIyBUaGUgbmV4dCBzY2hlZHVsZSBhZHZhbmNlcyB0aGUgb3B0aW1pc3RpYyBjb3VudCB3aGlsZSB0aGUgcHJlY2VkaW5nIHN0ZXAKICAgICMgaXMgc3RpbGwgaW4gZmxpZ2h0LiBSZWplY3Rpb24gdGhlbiBtb3ZlcyBwcm9ncmVzcyBiYWNrIGludG8gdGhhdCByYW5nZS4KICAgIHNjaGVkdWxlci5zY2hlZHVsZSgpCiAgICBvcHRpbWlzdGljID0gaXRlbS5udW1fY29tcHV0ZWRfdG9rZW5zCiAgICBhc3NlcnQgMCA8IHJvbGxiYWNrX3Rva2VucyA8IG9wdGltaXN0aWMKICAgIGl0ZW0ubnVtX2NvbXB1dGVkX3Rva2VucyAtPSByb2xsYmFja190b2tlbnMKICAgIHJvbGxlZF9iYWNrID0gaXRlbS5udW1fY29tcHV0ZWRfdG9rZW5zCgogICAgaWYga2luZCA9PSAic3dhIjoKICAgICAgICBmaXJzdF9yZXF1aXJlZF90b2tlbiA9IG1heCgwLCByb2xsZWRfYmFjayAtIDE2ICsgMSkKICAgIGVsaWYga2luZCA9PSAiY2h1bmtlZCI6CiAgICAgICAgZmlyc3RfcmVxdWlyZWRfdG9rZW4gPSAocm9sbGVkX2JhY2sgLy8gMzIpICogMzIKICAgIGVsc2U6CiAgICAgICAgcmFpc2UgQXNzZXJ0aW9uRXJyb3Ioa2luZCkKICAgIGZpcnN0X2Jsb2NrID0gZmlyc3RfcmVxdWlyZWRfdG9rZW4gLy8gQkxPQ0tfU0laRQogICAgbGFzdF9ibG9jayA9IG1heChmaXJzdF9ibG9jaywgKHJvbGxlZF9iYWNrIC0gMSkgLy8gQkxPQ0tfU0laRSkKICAgIGN1cnJlbnQgPSBibG9ja19pZHMoc2NoZWR1bGVyLCBpdGVtLnJlcXVlc3RfaWQpCiAgICByZXF1aXJlZF9vcmlnaW5hbCA9IG9yaWdpbmFsW2ZpcnN0X2Jsb2NrIDogbGFzdF9ibG9jayArIDFdCiAgICByZXF1aXJlZF9jdXJyZW50ID0gY3VycmVudFtmaXJzdF9ibG9jayA6IGxhc3RfYmxvY2sgKyAxXQogICAgcmV0dXJuIHsKICAgICAgICAib3B0aW1pc3RpY190b2tlbnMiOiBvcHRpbWlzdGljLAogICAgICAgICJyb2xsZWRfYmFja190b2tlbnMiOiByb2xsZWRfYmFjaywKICAgICAgICAicmVxdWlyZWRfYmxvY2tfaW5kZXhlcyI6IGxpc3QocmFuZ2UoZmlyc3RfYmxvY2ssIGxhc3RfYmxvY2sgKyAxKSksCiAgICAgICAgInJlcXVpcmVkX29yaWdpbmFsX2lkcyI6IHJlcXVpcmVkX29yaWdpbmFsLAogICAgICAgICJyZXF1aXJlZF9jdXJyZW50X2lkcyI6IHJlcXVpcmVkX2N1cnJlbnQsCiAgICAgICAgInJlcXVpcmVkX2Jsb2Nrc19yZXRhaW5lZCI6IHJlcXVpcmVkX2N1cnJlbnQgPT0gcmVxdWlyZWRfb3JpZ2luYWwsCiAgICB9CgoKZGVmIGFkbWlzc2lvbl9ibG9ja3MocGF0aDogUGF0aCwga2luZDogc3RyLCAqLCBhc3luY19zY2hlZHVsaW5nOiBib29sKSAtPiBpbnQ6CiAgICBjb25maWcgPSBtYWtlX3ZsbG1fY29uZmlnKHBhdGgsIGFzeW5jX3NjaGVkdWxpbmc9YXN5bmNfc2NoZWR1bGluZykKICAgIGl0ZW1fc3BlYyA9IHNwZWMoa2luZCkKICAgIHJldHVybiBpdGVtX3NwZWMubWF4X21lbW9yeV91c2FnZV9ieXRlcyhjb25maWcpIC8vIGl0ZW1fc3BlYy5wYWdlX3NpemVfYnl0ZXMK | base64 -d > /opt/repro/scheduler_fixture.py
LABEL ai.infra.bench.environment-template=vllm-harbor-all-in-one \
      ai.infra.bench.base-commit=$VLLM_BASE_SHA \
      ai.infra.bench.dependency-cutoff=$VLLM_DEPENDENCY_CUTOFF \
      ai.infra.bench.cache-namespace=$VLLM_CACHE_NAMESPACE
ENTRYPOINT []
CMD ["sleep", "infinity"]
