# syntax=docker/dockerfile:1
# Template inputs below are replaced from task.toml by generate.py. Generated
# task Dockerfiles are self-contained and differ only in their frozen inputs.

ARG VLLM_BASE_SHA=43f0e024bcc304e88b5be47555daabf795582354
ARG VLLM_DEPENDENCY_CUTOFF=2026-06-13T05:55:33Z
ARG VLLM_CACHE_NAMESPACE=43f0e024bcc304e88b5be47555daabf795582354-984de83c1435760a-58c4f34b2c181742
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
# Exact task dependency lock (sha256:984de83c1435760a7a74cd94ceea359a99c2626a780698822dd5fdea4ab6c2d8) is embedded so this
# Dockerfile remains independently buildable with an empty context.
RUN --mount=type=cache,id=vllm-uv-downloads-v3,target=/root/.cache/uv,sharing=locked <<'VLLM_INSTALL_EOF'
set -eu
cat > /tmp/vllm-requirements.lock <<'VLLM_REQUIREMENTS_EOF'
# Generated with uv 0.11.28 from the pinned base requirements and task
# extras for CPython 3.12 on x86_64 manylinux_2_28. Packages newer than
# 2026-06-13T05:55:33Z were excluded during resolution.
aiohappyeyeballs==2.6.2
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
anthropic==0.109.1
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
apache-tvm-ffi==0.1.12
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
cbor2==6.1.2
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
    #   ray
    #   rich-toolkit
    #   typer
    #   uvicorn
cloudpickle==3.1.2
    # via
    #   -r extras.in
    #   -r requirements/common.txt
cmake==4.3.2
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
fastapi-cli==0.0.24
    # via fastapi
fastapi-cloud-cli==0.20.0
    # via fastapi-cli
fastar==0.11.0
    # via
    #   fastapi
    #   fastapi-cloud-cli
filelock==3.29.3
    # via
    #   -r requirements/common.txt
    #   huggingface-hub
    #   ray
    #   torch
frozenlist==1.8.0
    # via
    #   aiohttp
    #   aiosignal
fsspec==2026.4.0
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
huggingface-hub==1.19.0
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
    #   ray
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
mcp==1.27.2
    # via -r requirements/common.txt
mdurl==0.1.2
    # via markdown-it-py
mistral-common==1.11.3
    # via -r requirements/common.txt
model-hosting-container-standards==0.1.15
    # via -r requirements/common.txt
mpmath==1.3.0
    # via sympy
msgpack==1.2.0
    # via ray
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
openai==2.41.1
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
    #   ray
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
prometheus-fastapi-instrumentator==8.0.0
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
    #   ray
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
python-multipart==0.0.32
    # via
    #   fastapi
    #   mcp
pyyaml==6.0.3
    # via
    #   -r requirements/common.txt
    #   huggingface-hub
    #   lm-format-enforcer
    #   ray
    #   transformers
    #   uvicorn
pyzmq==27.1.0
    # via -r requirements/common.txt
ray==2.55.1
    # via -r extras.in
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
    #   mistral-common
    #   opentelemetry-exporter-otlp-proto-http
    #   ray
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
rpds-py==2026.5.1
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
sentry-sdk==2.62.0
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
starlette==1.3.1
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
tqdm==4.68.2
    # via
    #   -r requirements/common.txt
    #   huggingface-hub
    #   openai
    #   transformers
transformers==5.12.0
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
uvicorn==0.49.0
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
xgrammar==0.2.2
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

RUN install -d /workspace/prompt-gateway/model \
 && curl --http1.1 -L --retry 10 --retry-all-errors --connect-timeout 30 --max-time 600 --proto '=https' --tlsv1.2 -sSf https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/resolve/7ae557604adf67be50417f59c2c2f167def9a775/LICENSE -o /workspace/prompt-gateway/model/LICENSE \
 && printf '%s  %s\n' 832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e /workspace/prompt-gateway/model/LICENSE | sha256sum -c - \
 && curl --http1.1 -L --retry 10 --retry-all-errors --connect-timeout 30 --max-time 600 --proto '=https' --tlsv1.2 -sSf https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/resolve/7ae557604adf67be50417f59c2c2f167def9a775/config.json -o /workspace/prompt-gateway/model/config.json \
 && printf '%s  %s\n' 18e18afcaccafade98daf13a54092927904649e1dd4eba8299ab717d5d94ff45 /workspace/prompt-gateway/model/config.json | sha256sum -c - \
 && curl --http1.1 -L --retry 10 --retry-all-errors --connect-timeout 30 --max-time 600 --proto '=https' --tlsv1.2 -sSf https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/resolve/7ae557604adf67be50417f59c2c2f167def9a775/generation_config.json -o /workspace/prompt-gateway/model/generation_config.json \
 && printf '%s  %s\n' e558847a8b4402616f1273797b015104dc266fe4b520056fca88823ba8f8ebe6 /workspace/prompt-gateway/model/generation_config.json | sha256sum -c - \
 && curl --http1.1 -L --retry 10 --retry-all-errors --connect-timeout 30 --max-time 600 --proto '=https' --tlsv1.2 -sSf https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/resolve/7ae557604adf67be50417f59c2c2f167def9a775/merges.txt -o /workspace/prompt-gateway/model/merges.txt \
 && printf '%s  %s\n' 599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3 /workspace/prompt-gateway/model/merges.txt | sha256sum -c - \
 && curl --http1.1 -L --retry 10 --retry-all-errors --connect-timeout 30 --max-time 600 --proto '=https' --tlsv1.2 -sSf https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/resolve/7ae557604adf67be50417f59c2c2f167def9a775/tokenizer.json -o /workspace/prompt-gateway/model/tokenizer.json \
 && printf '%s  %s\n' c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539 /workspace/prompt-gateway/model/tokenizer.json | sha256sum -c - \
 && curl --http1.1 -L --retry 10 --retry-all-errors --connect-timeout 30 --max-time 600 --proto '=https' --tlsv1.2 -sSf https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/resolve/7ae557604adf67be50417f59c2c2f167def9a775/tokenizer_config.json -o /workspace/prompt-gateway/model/tokenizer_config.json \
 && printf '%s  %s\n' 5b5d4f65d0acd3b2d56a35b56d374a36cbc1c8fa5cf3b3febbbfabf22f359583 /workspace/prompt-gateway/model/tokenizer_config.json | sha256sum -c - \
 && curl --http1.1 -L --retry 10 --retry-all-errors --connect-timeout 30 --max-time 600 --proto '=https' --tlsv1.2 -sSf https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/resolve/7ae557604adf67be50417f59c2c2f167def9a775/vocab.json -o /workspace/prompt-gateway/model/vocab.json \
 && printf '%s  %s\n' ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910 /workspace/prompt-gateway/model/vocab.json | sha256sum -c -
LABEL ai.infra.bench.workspace-application=prompt-gateway \
      ai.infra.bench.prompt-gateway-model="Qwen/Qwen2.5-0.5B-Instruct" \
      ai.infra.bench.prompt-gateway-model-revision=7ae557604adf67be50417f59c2c2f167def9a775 \
      ai.infra.bench.prompt-gateway-model-license="Apache-2.0"

# Task-owned user application installed next to the vLLM worktree.
RUN install -d /workspace/prompt-gateway \
 && install -d /workspace/prompt-gateway \
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGpzb24KZnJvbSBkYXRhY2xhc3NlcyBpbXBvcnQgYXNkaWN0LCBkYXRhY2xhc3MsIGZpZWxkCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aApmcm9tIHR5cGluZyBpbXBvcnQgQW55LCBJdGVyYWJsZQoKCkBkYXRhY2xhc3MoZnJvemVuPVRydWUpCmNsYXNzIFJlcXVlc3RFbnZlbG9wZToKICAgIHJlcXVlc3RfaWQ6IHN0cgogICAgdGVuYW50OiBzdHIKICAgIHByb21wdDogc3RyCiAgICByZXF1ZXN0ZWRfb3V0cHV0X3Rva2VuczogaW50CiAgICBwcmlvcml0eTogaW50ID0gMAogICAgbWV0YWRhdGE6IGRpY3Rbc3RyLCBzdHJdID0gZmllbGQoZGVmYXVsdF9mYWN0b3J5PWRpY3QpCgogICAgQGNsYXNzbWV0aG9kCiAgICBkZWYgZnJvbV9tYXBwaW5nKGNscywgZGF0YTogZGljdFtzdHIsIEFueV0sIGxpbmVfbnVtYmVyOiBpbnQpIC0+ICJSZXF1ZXN0RW52ZWxvcGUiOgogICAgICAgIHJlcXVlc3RfaWQgPSBzdHIoZGF0YS5nZXQoInJlcXVlc3RfaWQiLCAiIikpLnN0cmlwKCkKICAgICAgICB0ZW5hbnQgPSBzdHIoZGF0YS5nZXQoInRlbmFudCIsICIiKSkuc3RyaXAoKQogICAgICAgIHByb21wdCA9IHN0cihkYXRhLmdldCgicHJvbXB0IiwgIiIpKQogICAgICAgIHJlcXVlc3RlZF9vdXRwdXRfdG9rZW5zID0gaW50KGRhdGEuZ2V0KCJyZXF1ZXN0ZWRfb3V0cHV0X3Rva2VucyIsIDApKQogICAgICAgIHByaW9yaXR5ID0gaW50KGRhdGEuZ2V0KCJwcmlvcml0eSIsIDApKQogICAgICAgIG1ldGFkYXRhID0ge3N0cihrZXkpOiBzdHIodmFsdWUpIGZvciBrZXksIHZhbHVlIGluIGRpY3QoZGF0YS5nZXQoIm1ldGFkYXRhIiwge30pKS5pdGVtcygpfQogICAgICAgIGlmIG5vdCByZXF1ZXN0X2lkOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKGYibGluZSB7bGluZV9udW1iZXJ9OiByZXF1ZXN0X2lkIGlzIHJlcXVpcmVkIikKICAgICAgICBpZiBub3QgdGVuYW50OgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKGYibGluZSB7bGluZV9udW1iZXJ9OiB0ZW5hbnQgaXMgcmVxdWlyZWQiKQogICAgICAgIGlmIG5vdCBwcm9tcHQuc3RyaXAoKToKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcihmImxpbmUge2xpbmVfbnVtYmVyfTogcHJvbXB0IGlzIHJlcXVpcmVkIikKICAgICAgICBpZiByZXF1ZXN0ZWRfb3V0cHV0X3Rva2VucyA8IDE6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoZiJsaW5lIHtsaW5lX251bWJlcn06IHJlcXVlc3RlZF9vdXRwdXRfdG9rZW5zIG11c3QgYmUgcG9zaXRpdmUiKQogICAgICAgIHJldHVybiBjbHMoCiAgICAgICAgICAgIHJlcXVlc3RfaWQ9cmVxdWVzdF9pZCwKICAgICAgICAgICAgdGVuYW50PXRlbmFudCwKICAgICAgICAgICAgcHJvbXB0PXByb21wdCwKICAgICAgICAgICAgcmVxdWVzdGVkX291dHB1dF90b2tlbnM9cmVxdWVzdGVkX291dHB1dF90b2tlbnMsCiAgICAgICAgICAgIHByaW9yaXR5PXByaW9yaXR5LAogICAgICAgICAgICBtZXRhZGF0YT1tZXRhZGF0YSwKICAgICAgICApCgoKQGRhdGFjbGFzcyhmcm96ZW49VHJ1ZSkKY2xhc3MgSW5zcGVjdGVkUmVxdWVzdDoKICAgIHJlcXVlc3Q6IFJlcXVlc3RFbnZlbG9wZQogICAgaW5wdXRfdG9rZW5faWRzOiB0dXBsZVtpbnQsIC4uLl0KICAgIGlucHV0X3Rva2VuczogaW50CiAgICB0b3RhbF9yZXNlcnZlZF90b2tlbnM6IGludAoKICAgIGRlZiB0b19tYXBwaW5nKHNlbGYpIC0+IGRpY3Rbc3RyLCBBbnldOgogICAgICAgIHJldHVybiB7CiAgICAgICAgICAgICJyZXF1ZXN0IjogYXNkaWN0KHNlbGYucmVxdWVzdCksCiAgICAgICAgICAgICJpbnB1dF90b2tlbl9pZHMiOiBsaXN0KHNlbGYuaW5wdXRfdG9rZW5faWRzKSwKICAgICAgICAgICAgImlucHV0X3Rva2VucyI6IHNlbGYuaW5wdXRfdG9rZW5zLAogICAgICAgICAgICAidG90YWxfcmVzZXJ2ZWRfdG9rZW5zIjogc2VsZi50b3RhbF9yZXNlcnZlZF90b2tlbnMsCiAgICAgICAgfQoKCkBkYXRhY2xhc3MoZnJvemVuPVRydWUpCmNsYXNzIFJlamVjdGVkUmVxdWVzdDoKICAgIHJlcXVlc3RfaWQ6IHN0cgogICAgcmVhc29uOiBzdHIKICAgIG9ic2VydmVkX3Rva2VuczogaW50IHwgTm9uZSA9IE5vbmUKCiAgICBkZWYgdG9fbWFwcGluZyhzZWxmKSAtPiBkaWN0W3N0ciwgQW55XToKICAgICAgICByZXR1cm4gYXNkaWN0KHNlbGYpCgoKQGRhdGFjbGFzcyhmcm96ZW49VHJ1ZSkKY2xhc3MgUGxhbm5lZEJhdGNoOgogICAgYmF0Y2hfaWQ6IHN0cgogICAgcmVxdWVzdF9pZHM6IHR1cGxlW3N0ciwgLi4uXQogICAgcmVzZXJ2ZWRfdG9rZW5zOiBpbnQKICAgIHRlbmFudHM6IHR1cGxlW3N0ciwgLi4uXQoKICAgIGRlZiB0b19tYXBwaW5nKHNlbGYpIC0+IGRpY3Rbc3RyLCBBbnldOgogICAgICAgIHJldHVybiB7CiAgICAgICAgICAgICJiYXRjaF9pZCI6IHNlbGYuYmF0Y2hfaWQsCiAgICAgICAgICAgICJyZXF1ZXN0X2lkcyI6IGxpc3Qoc2VsZi5yZXF1ZXN0X2lkcyksCiAgICAgICAgICAgICJyZXNlcnZlZF90b2tlbnMiOiBzZWxmLnJlc2VydmVkX3Rva2VucywKICAgICAgICAgICAgInRlbmFudHMiOiBsaXN0KHNlbGYudGVuYW50cyksCiAgICAgICAgfQoKCkBkYXRhY2xhc3MoZnJvemVuPVRydWUpCmNsYXNzIEdhdGV3YXlSZXBvcnQ6CiAgICBhY2NlcHRlZDogdHVwbGVbSW5zcGVjdGVkUmVxdWVzdCwgLi4uXQogICAgcmVqZWN0ZWQ6IHR1cGxlW1JlamVjdGVkUmVxdWVzdCwgLi4uXQogICAgYmF0Y2hlczogdHVwbGVbUGxhbm5lZEJhdGNoLCAuLi5dCiAgICBjb3VudGVyczogZGljdFtzdHIsIGludF0KCiAgICBkZWYgdG9fbWFwcGluZyhzZWxmKSAtPiBkaWN0W3N0ciwgQW55XToKICAgICAgICByZXR1cm4gewogICAgICAgICAgICAiYWNjZXB0ZWQiOiBbaXRlbS50b19tYXBwaW5nKCkgZm9yIGl0ZW0gaW4gc2VsZi5hY2NlcHRlZF0sCiAgICAgICAgICAgICJyZWplY3RlZCI6IFtpdGVtLnRvX21hcHBpbmcoKSBmb3IgaXRlbSBpbiBzZWxmLnJlamVjdGVkXSwKICAgICAgICAgICAgImJhdGNoZXMiOiBbaXRlbS50b19tYXBwaW5nKCkgZm9yIGl0ZW0gaW4gc2VsZi5iYXRjaGVzXSwKICAgICAgICAgICAgImNvdW50ZXJzIjogZGljdChzZWxmLmNvdW50ZXJzKSwKICAgICAgICB9CgogICAgZGVmIHRvX2pzb24oc2VsZikgLT4gc3RyOgogICAgICAgIHJldHVybiBqc29uLmR1bXBzKHNlbGYudG9fbWFwcGluZygpLCBpbmRlbnQ9Miwgc29ydF9rZXlzPVRydWUpCgoKZGVmIGxvYWRfcmVxdWVzdHMocGF0aDogUGF0aCkgLT4gdHVwbGVbUmVxdWVzdEVudmVsb3BlLCAuLi5dOgogICAgcmVxdWVzdHM6IGxpc3RbUmVxdWVzdEVudmVsb3BlXSA9IFtdCiAgICBzZWVuOiBzZXRbc3RyXSA9IHNldCgpCiAgICBmb3IgbGluZV9udW1iZXIsIHJhd19saW5lIGluIGVudW1lcmF0ZShwYXRoLnJlYWRfdGV4dChlbmNvZGluZz0idXRmLTgiKS5zcGxpdGxpbmVzKCksIDEpOgogICAgICAgIGxpbmUgPSByYXdfbGluZS5zdHJpcCgpCiAgICAgICAgaWYgbm90IGxpbmUgb3IgbGluZS5zdGFydHN3aXRoKCIjIik6CiAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgcmVxdWVzdCA9IFJlcXVlc3RFbnZlbG9wZS5mcm9tX21hcHBpbmcoanNvbi5sb2FkcyhsaW5lKSwgbGluZV9udW1iZXIpCiAgICAgICAgaWYgcmVxdWVzdC5yZXF1ZXN0X2lkIGluIHNlZW46CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoZiJsaW5lIHtsaW5lX251bWJlcn06IGR1cGxpY2F0ZSByZXF1ZXN0X2lkIHtyZXF1ZXN0LnJlcXVlc3RfaWQhcn0iKQogICAgICAgIHNlZW4uYWRkKHJlcXVlc3QucmVxdWVzdF9pZCkKICAgICAgICByZXF1ZXN0cy5hcHBlbmQocmVxdWVzdCkKICAgIGlmIG5vdCByZXF1ZXN0czoKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKGYibm8gcmVxdWVzdHMgZm91bmQgaW4ge3BhdGh9IikKICAgIHJldHVybiB0dXBsZShyZXF1ZXN0cykKCgpkZWYgc3RhYmxlX3ByaW9yaXR5X29yZGVyKHJlcXVlc3RzOiBJdGVyYWJsZVtSZXF1ZXN0RW52ZWxvcGVdKSAtPiB0dXBsZVtSZXF1ZXN0RW52ZWxvcGUsIC4uLl06CiAgICBpbmRleGVkID0gbGlzdChlbnVtZXJhdGUocmVxdWVzdHMpKQogICAgaW5kZXhlZC5zb3J0KGtleT1sYW1iZGEgaXRlbTogKC1pdGVtWzFdLnByaW9yaXR5LCBpdGVtWzBdKSkKICAgIHJldHVybiB0dXBsZShyZXF1ZXN0IGZvciBfLCByZXF1ZXN0IGluIGluZGV4ZWQpCg== | base64 -d > /workspace/prompt-gateway/domain.py \
 && install -d /workspace/prompt-gateway \
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGFyZ3BhcnNlCmltcG9ydCBqc29uCmZyb20gZGF0YWNsYXNzZXMgaW1wb3J0IGRhdGFjbGFzcwpmcm9tIHBhdGhsaWIgaW1wb3J0IFBhdGgKZnJvbSB0eXBpbmcgaW1wb3J0IEFueQoKCkBkYXRhY2xhc3MoZnJvemVuPVRydWUpCmNsYXNzIEVuZ2luZVNldHRpbmdzOgogICAgbW9kZWxfcGF0aDogUGF0aAogICAgbWF4X21vZGVsX2xlbjogaW50CiAgICBtYXhfbnVtX3NlcXM6IGludAogICAgbWF4X251bV9iYXRjaGVkX3Rva2VuczogaW50CgogICAgQGNsYXNzbWV0aG9kCiAgICBkZWYgZnJvbV9tYXBwaW5nKGNscywgZGF0YTogZGljdFtzdHIsIEFueV0sIHJvb3Q6IFBhdGgpIC0+ICJFbmdpbmVTZXR0aW5ncyI6CiAgICAgICAgbW9kZWxfcGF0aCA9IFBhdGgoc3RyKGRhdGEuZ2V0KCJtb2RlbF9wYXRoIiwgIm1vZGVsIikpKQogICAgICAgIGlmIG5vdCBtb2RlbF9wYXRoLmlzX2Fic29sdXRlKCk6CiAgICAgICAgICAgIG1vZGVsX3BhdGggPSByb290IC8gbW9kZWxfcGF0aAogICAgICAgIHNldHRpbmdzID0gY2xzKAogICAgICAgICAgICBtb2RlbF9wYXRoPW1vZGVsX3BhdGgucmVzb2x2ZSgpLAogICAgICAgICAgICBtYXhfbW9kZWxfbGVuPWludChkYXRhLmdldCgibWF4X21vZGVsX2xlbiIsIDEyOCkpLAogICAgICAgICAgICBtYXhfbnVtX3NlcXM9aW50KGRhdGEuZ2V0KCJtYXhfbnVtX3NlcXMiLCA4KSksCiAgICAgICAgICAgIG1heF9udW1fYmF0Y2hlZF90b2tlbnM9aW50KGRhdGEuZ2V0KCJtYXhfbnVtX2JhdGNoZWRfdG9rZW5zIiwgMjU2KSksCiAgICAgICAgKQogICAgICAgIGlmIHNldHRpbmdzLm1heF9tb2RlbF9sZW4gPCAxNjoKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigibWF4X21vZGVsX2xlbiBtdXN0IGJlIGF0IGxlYXN0IDE2IikKICAgICAgICBpZiBzZXR0aW5ncy5tYXhfbnVtX3NlcXMgPCAxOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJtYXhfbnVtX3NlcXMgbXVzdCBiZSBwb3NpdGl2ZSIpCiAgICAgICAgaWYgc2V0dGluZ3MubWF4X251bV9iYXRjaGVkX3Rva2VucyA8IHNldHRpbmdzLm1heF9tb2RlbF9sZW46CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIm1heF9udW1fYmF0Y2hlZF90b2tlbnMgbXVzdCBjb3ZlciBvbmUgbWF4aW11bS1sZW5ndGggcmVxdWVzdCIpCiAgICAgICAgcmV0dXJuIHNldHRpbmdzCgoKQGRhdGFjbGFzcyhmcm96ZW49VHJ1ZSkKY2xhc3MgQWRtaXNzaW9uU2V0dGluZ3M6CiAgICByZXF1ZXN0X3Rva2VuX2xpbWl0OiBpbnQKICAgIGJhdGNoX3Rva2VuX2xpbWl0OiBpbnQKICAgIG1heF9iYXRjaF9zaXplOiBpbnQKICAgIHJlc2VydmVfb3V0cHV0X3Rva2VuczogaW50CgogICAgQGNsYXNzbWV0aG9kCiAgICBkZWYgZnJvbV9tYXBwaW5nKGNscywgZGF0YTogZGljdFtzdHIsIEFueV0pIC0+ICJBZG1pc3Npb25TZXR0aW5ncyI6CiAgICAgICAgc2V0dGluZ3MgPSBjbHMoCiAgICAgICAgICAgIHJlcXVlc3RfdG9rZW5fbGltaXQ9aW50KGRhdGEuZ2V0KCJyZXF1ZXN0X3Rva2VuX2xpbWl0IiwgOTYpKSwKICAgICAgICAgICAgYmF0Y2hfdG9rZW5fbGltaXQ9aW50KGRhdGEuZ2V0KCJiYXRjaF90b2tlbl9saW1pdCIsIDE2MCkpLAogICAgICAgICAgICBtYXhfYmF0Y2hfc2l6ZT1pbnQoZGF0YS5nZXQoIm1heF9iYXRjaF9zaXplIiwgNCkpLAogICAgICAgICAgICByZXNlcnZlX291dHB1dF90b2tlbnM9aW50KGRhdGEuZ2V0KCJyZXNlcnZlX291dHB1dF90b2tlbnMiLCAxNikpLAogICAgICAgICkKICAgICAgICBpZiBzZXR0aW5ncy5yZXF1ZXN0X3Rva2VuX2xpbWl0IDwgMToKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigicmVxdWVzdF90b2tlbl9saW1pdCBtdXN0IGJlIHBvc2l0aXZlIikKICAgICAgICBpZiBzZXR0aW5ncy5iYXRjaF90b2tlbl9saW1pdCA8IHNldHRpbmdzLnJlcXVlc3RfdG9rZW5fbGltaXQ6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoImJhdGNoX3Rva2VuX2xpbWl0IG11c3QgY292ZXIgb25lIGFjY2VwdGVkIHJlcXVlc3QiKQogICAgICAgIGlmIHNldHRpbmdzLm1heF9iYXRjaF9zaXplIDwgMToKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigibWF4X2JhdGNoX3NpemUgbXVzdCBiZSBwb3NpdGl2ZSIpCiAgICAgICAgaWYgc2V0dGluZ3MucmVzZXJ2ZV9vdXRwdXRfdG9rZW5zIDwgMDoKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigicmVzZXJ2ZV9vdXRwdXRfdG9rZW5zIGNhbm5vdCBiZSBuZWdhdGl2ZSIpCiAgICAgICAgcmV0dXJuIHNldHRpbmdzCgoKQGRhdGFjbGFzcyhmcm96ZW49VHJ1ZSkKY2xhc3MgUmF5U2V0dGluZ3M6CiAgICBudW1fY3B1czogaW50CiAgICBvYmplY3Rfc3RvcmVfbWVtb3J5OiBpbnQgfCBOb25lCiAgICBsb2dfdG9fZHJpdmVyOiBib29sCgogICAgQGNsYXNzbWV0aG9kCiAgICBkZWYgZnJvbV9tYXBwaW5nKGNscywgZGF0YTogZGljdFtzdHIsIEFueV0pIC0+ICJSYXlTZXR0aW5ncyI6CiAgICAgICAgcmF3X3N0b3JlID0gZGF0YS5nZXQoIm9iamVjdF9zdG9yZV9tZW1vcnkiKQogICAgICAgIHNldHRpbmdzID0gY2xzKAogICAgICAgICAgICBudW1fY3B1cz1pbnQoZGF0YS5nZXQoIm51bV9jcHVzIiwgNCkpLAogICAgICAgICAgICBvYmplY3Rfc3RvcmVfbWVtb3J5PU5vbmUgaWYgcmF3X3N0b3JlIGlzIE5vbmUgZWxzZSBpbnQocmF3X3N0b3JlKSwKICAgICAgICAgICAgbG9nX3RvX2RyaXZlcj1ib29sKGRhdGEuZ2V0KCJsb2dfdG9fZHJpdmVyIiwgRmFsc2UpKSwKICAgICAgICApCiAgICAgICAgaWYgc2V0dGluZ3MubnVtX2NwdXMgPCAyOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJSYXkgbmVlZHMgYXQgbGVhc3QgdHdvIENQVXMgZm9yIHRoaXMgZ2F0ZXdheSIpCiAgICAgICAgcmV0dXJuIHNldHRpbmdzCgoKQGRhdGFjbGFzcyhmcm96ZW49VHJ1ZSkKY2xhc3MgR2F0ZXdheVNldHRpbmdzOgogICAgZW5naW5lOiBFbmdpbmVTZXR0aW5ncwogICAgYWRtaXNzaW9uOiBBZG1pc3Npb25TZXR0aW5ncwogICAgcmF5OiBSYXlTZXR0aW5ncwogICAgcmVxdWVzdHNfcGF0aDogUGF0aAoKICAgIEBjbGFzc21ldGhvZAogICAgZGVmIGxvYWQoY2xzLCBwYXRoOiBQYXRoKSAtPiAiR2F0ZXdheVNldHRpbmdzIjoKICAgICAgICBwYXRoID0gcGF0aC5yZXNvbHZlKCkKICAgICAgICBkYXRhID0ganNvbi5sb2FkcyhwYXRoLnJlYWRfdGV4dChlbmNvZGluZz0idXRmLTgiKSkKICAgICAgICByb290ID0gcGF0aC5wYXJlbnQKICAgICAgICByZXF1ZXN0c19wYXRoID0gUGF0aChzdHIoZGF0YS5nZXQoInJlcXVlc3RzX3BhdGgiLCAicmVxdWVzdHMuanNvbmwiKSkpCiAgICAgICAgaWYgbm90IHJlcXVlc3RzX3BhdGguaXNfYWJzb2x1dGUoKToKICAgICAgICAgICAgcmVxdWVzdHNfcGF0aCA9IHJvb3QgLyByZXF1ZXN0c19wYXRoCiAgICAgICAgc2V0dGluZ3MgPSBjbHMoCiAgICAgICAgICAgIGVuZ2luZT1FbmdpbmVTZXR0aW5ncy5mcm9tX21hcHBpbmcoZGljdChkYXRhLmdldCgiZW5naW5lIiwge30pKSwgcm9vdCksCiAgICAgICAgICAgIGFkbWlzc2lvbj1BZG1pc3Npb25TZXR0aW5ncy5mcm9tX21hcHBpbmcoZGljdChkYXRhLmdldCgiYWRtaXNzaW9uIiwge30pKSksCiAgICAgICAgICAgIHJheT1SYXlTZXR0aW5ncy5mcm9tX21hcHBpbmcoZGljdChkYXRhLmdldCgicmF5Iiwge30pKSksCiAgICAgICAgICAgIHJlcXVlc3RzX3BhdGg9cmVxdWVzdHNfcGF0aC5yZXNvbHZlKCksCiAgICAgICAgKQogICAgICAgIGlmIG5vdCBzZXR0aW5ncy5lbmdpbmUubW9kZWxfcGF0aC5pc19kaXIoKToKICAgICAgICAgICAgcmFpc2UgRmlsZU5vdEZvdW5kRXJyb3IoZiJtb2RlbCBkaXJlY3Rvcnkgbm90IGZvdW5kOiB7c2V0dGluZ3MuZW5naW5lLm1vZGVsX3BhdGh9IikKICAgICAgICBpZiBub3Qgc2V0dGluZ3MucmVxdWVzdHNfcGF0aC5pc19maWxlKCk6CiAgICAgICAgICAgIHJhaXNlIEZpbGVOb3RGb3VuZEVycm9yKGYicmVxdWVzdCBpbnB1dCBub3QgZm91bmQ6IHtzZXR0aW5ncy5yZXF1ZXN0c19wYXRofSIpCiAgICAgICAgcmV0dXJuIHNldHRpbmdzCgoKZGVmIHBhcnNlX2FyZ3MoYXJndjogbGlzdFtzdHJdIHwgTm9uZSA9IE5vbmUpIC0+IGFyZ3BhcnNlLk5hbWVzcGFjZToKICAgIHBhcnNlciA9IGFyZ3BhcnNlLkFyZ3VtZW50UGFyc2VyKAogICAgICAgIHByb2c9InByb21wdC1nYXRld2F5IiwKICAgICAgICBkZXNjcmlwdGlvbj0iUGxhbiB0b2tlbi1idWRnZXRlZCByZXF1ZXN0IGJhdGNoZXMgdXNpbmcgYSByZW1vdGUgdkxMTSBydW50aW1lLiIsCiAgICApCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KAogICAgICAgICItLWNvbmZpZyIsCiAgICAgICAgdHlwZT1QYXRoLAogICAgICAgIGRlZmF1bHQ9UGF0aChfX2ZpbGVfXykud2l0aF9uYW1lKCJzZXR0aW5ncy5qc29uIiksCiAgICAgICAgaGVscD0icGF0aCB0byB0aGUgZ2F0ZXdheSBKU09OIGNvbmZpZ3VyYXRpb24iLAogICAgKQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgKICAgICAgICAiLS1vdXRwdXQiLAogICAgICAgIHR5cGU9UGF0aCwKICAgICAgICBkZWZhdWx0PU5vbmUsCiAgICAgICAgaGVscD0ib3B0aW9uYWwgcGF0aCBmb3IgdGhlIHJlc3VsdGluZyBiYXRjaCBwbGFuIiwKICAgICkKICAgIHBhcnNlci5hZGRfYXJndW1lbnQoCiAgICAgICAgIi0tbG9nLWxldmVsIiwKICAgICAgICBjaG9pY2VzPSgiREVCVUciLCAiSU5GTyIsICJXQVJOSU5HIiwgIkVSUk9SIiksCiAgICAgICAgZGVmYXVsdD0iSU5GTyIsCiAgICApCiAgICByZXR1cm4gcGFyc2VyLnBhcnNlX2FyZ3MoYXJndikK | base64 -d > /workspace/prompt-gateway/gateway_config.py \
 && install -d /workspace/prompt-gateway \
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGpzb24KaW1wb3J0IGxvZ2dpbmcKaW1wb3J0IHN5cwppbXBvcnQgdGltZQpmcm9tIHBhdGhsaWIgaW1wb3J0IFBhdGgKZnJvbSB0eXBpbmcgaW1wb3J0IEFueQoKaW1wb3J0IHJheQoKZnJvbSBkb21haW4gaW1wb3J0IGxvYWRfcmVxdWVzdHMKZnJvbSBnYXRld2F5X2NvbmZpZyBpbXBvcnQgR2F0ZXdheVNldHRpbmdzLCBwYXJzZV9hcmdzCmZyb20gcGlwZWxpbmUgaW1wb3J0IGFkbWlzc2lvbl9zZXR0aW5nc19wYXlsb2FkLCBwbGFuX3JlbW90ZV9iYXRjaCwgcmVxdWVzdF9wYXlsb2Fkcwpmcm9tIHJ1bnRpbWUgaW1wb3J0IFZsbG1SdW50aW1lLCBlbmdpbmVfc2V0dGluZ3NfcGF5bG9hZAoKCkxPR0dFUiA9IGxvZ2dpbmcuZ2V0TG9nZ2VyKCJwcm9tcHRfZ2F0ZXdheSIpCgoKZGVmIGNvbmZpZ3VyZV9sb2dnaW5nKGxldmVsOiBzdHIpIC0+IE5vbmU6CiAgICBsb2dnaW5nLmJhc2ljQ29uZmlnKAogICAgICAgIGxldmVsPWdldGF0dHIobG9nZ2luZywgbGV2ZWwpLAogICAgICAgIGZvcm1hdD0iJShhc2N0aW1lKXMgJShsZXZlbG5hbWUpcyAlKG5hbWUpcyAlKG1lc3NhZ2UpcyIsCiAgICAgICAgZGF0ZWZtdD0iJVktJW0tJWQgJUg6JU06JVMiLAogICAgKQoKCmNsYXNzIFByb21wdEdhdGV3YXlBcHBsaWNhdGlvbjoKICAgIGRlZiBfX2luaXRfXyhzZWxmLCBzZXR0aW5nczogR2F0ZXdheVNldHRpbmdzLCBvdXRwdXQ6IFBhdGggfCBOb25lKSAtPiBOb25lOgogICAgICAgIHNlbGYuX3NldHRpbmdzID0gc2V0dGluZ3MKICAgICAgICBzZWxmLl9vdXRwdXQgPSBvdXRwdXQKICAgICAgICBzZWxmLl9ydW50aW1lID0gTm9uZQoKICAgIGRlZiBfc3RhcnRfcmF5KHNlbGYpIC0+IE5vbmU6CiAgICAgICAgcmF5X2t3YXJnczogZGljdFtzdHIsIEFueV0gPSB7CiAgICAgICAgICAgICJudW1fY3B1cyI6IHNlbGYuX3NldHRpbmdzLnJheS5udW1fY3B1cywKICAgICAgICAgICAgImluY2x1ZGVfZGFzaGJvYXJkIjogRmFsc2UsCiAgICAgICAgICAgICJsb2dfdG9fZHJpdmVyIjogc2VsZi5fc2V0dGluZ3MucmF5LmxvZ190b19kcml2ZXIsCiAgICAgICAgICAgICJpZ25vcmVfcmVpbml0X2Vycm9yIjogVHJ1ZSwKICAgICAgICB9CiAgICAgICAgaWYgc2VsZi5fc2V0dGluZ3MucmF5Lm9iamVjdF9zdG9yZV9tZW1vcnkgaXMgbm90IE5vbmU6CiAgICAgICAgICAgIHJheV9rd2FyZ3NbIm9iamVjdF9zdG9yZV9tZW1vcnkiXSA9IHNlbGYuX3NldHRpbmdzLnJheS5vYmplY3Rfc3RvcmVfbWVtb3J5CiAgICAgICAgcmF5LmluaXQoKipyYXlfa3dhcmdzKQogICAgICAgIExPR0dFUi5kZWJ1ZygibG9jYWwgUmF5IHJ1bnRpbWUgc3RhcnRlZCIpCgogICAgZGVmIF9zdGFydF9ydW50aW1lKHNlbGYpIC0+IE5vbmU6CiAgICAgICAgc2VsZi5fcnVudGltZSA9IFZsbG1SdW50aW1lLnJlbW90ZShlbmdpbmVfc2V0dGluZ3NfcGF5bG9hZChzZWxmLl9zZXR0aW5ncy5lbmdpbmUpKQogICAgICAgIGhlYWx0aCA9IHJheS5nZXQoc2VsZi5fcnVudGltZS5oZWFsdGgucmVtb3RlKCkpCiAgICAgICAgaWYgbm90IGhlYWx0aFsicmVhZHkiXToKICAgICAgICAgICAgcmFpc2UgUnVudGltZUVycm9yKCJ2TExNIHJ1bnRpbWUgZGlkIG5vdCBiZWNvbWUgcmVhZHkiKQoKICAgIGRlZiBfbG9hZF9yZXF1ZXN0cyhzZWxmKToKICAgICAgICByZXF1ZXN0cyA9IGxvYWRfcmVxdWVzdHMoc2VsZi5fc2V0dGluZ3MucmVxdWVzdHNfcGF0aCkKICAgICAgICBMT0dHRVIuaW5mbygibG9hZGVkICVkIHJlcXVlc3RzIGZyb20gJXMiLCBsZW4ocmVxdWVzdHMpLCBzZWxmLl9zZXR0aW5ncy5yZXF1ZXN0c19wYXRoKQogICAgICAgIHJldHVybiByZXF1ZXN0cwoKICAgIGRlZiBfZmV0Y2hfcnVudGltZV90b2tlbml6ZXIoc2VsZik6CiAgICAgICAgaWYgc2VsZi5fcnVudGltZSBpcyBOb25lOgogICAgICAgICAgICByYWlzZSBSdW50aW1lRXJyb3IoInJ1bnRpbWUgYWN0b3IgaGFzIG5vdCBiZWVuIHN0YXJ0ZWQiKQogICAgICAgIHJldHVybiByYXkuZ2V0KHNlbGYuX3J1bnRpbWUuZ2V0X3J1bnRpbWVfdG9rZW5pemVyLnJlbW90ZSgpKQoKICAgIGRlZiBfcGxhbihzZWxmLCB0b2tlbml6ZXIsIHJlcXVlc3RzKSAtPiBkaWN0W3N0ciwgQW55XToKICAgICAgICBmdXR1cmUgPSBwbGFuX3JlbW90ZV9iYXRjaC5yZW1vdGUoCiAgICAgICAgICAgIHRva2VuaXplciwKICAgICAgICAgICAgcmVxdWVzdF9wYXlsb2FkcyhyZXF1ZXN0cyksCiAgICAgICAgICAgIGFkbWlzc2lvbl9zZXR0aW5nc19wYXlsb2FkKHNlbGYuX3NldHRpbmdzLmFkbWlzc2lvbiksCiAgICAgICAgKQogICAgICAgIHJldHVybiByYXkuZ2V0KGZ1dHVyZSkKCiAgICBkZWYgX3dyaXRlX3JlcG9ydChzZWxmLCByZXBvcnQ6IGRpY3Rbc3RyLCBBbnldKSAtPiBOb25lOgogICAgICAgIHJlbmRlcmVkID0ganNvbi5kdW1wcyhyZXBvcnQsIGluZGVudD0yLCBzb3J0X2tleXM9VHJ1ZSkKICAgICAgICBpZiBzZWxmLl9vdXRwdXQgaXMgTm9uZToKICAgICAgICAgICAgcHJpbnQocmVuZGVyZWQpCiAgICAgICAgICAgIHJldHVybgogICAgICAgIHNlbGYuX291dHB1dC5wYXJlbnQubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQogICAgICAgIHNlbGYuX291dHB1dC53cml0ZV90ZXh0KHJlbmRlcmVkICsgIlxuIiwgZW5jb2Rpbmc9InV0Zi04IikKICAgICAgICBMT0dHRVIuaW5mbygid3JvdGUgYmF0Y2ggcGxhbiB0byAlcyIsIHNlbGYuX291dHB1dCkKCiAgICBkZWYgcnVuKHNlbGYpIC0+IGludDoKICAgICAgICBzdGFydGVkID0gdGltZS5tb25vdG9uaWMoKQogICAgICAgIHNlbGYuX3N0YXJ0X3JheSgpCiAgICAgICAgdHJ5OgogICAgICAgICAgICBzZWxmLl9zdGFydF9ydW50aW1lKCkKICAgICAgICAgICAgcmVxdWVzdHMgPSBzZWxmLl9sb2FkX3JlcXVlc3RzKCkKICAgICAgICAgICAgdG9rZW5pemVyID0gc2VsZi5fZmV0Y2hfcnVudGltZV90b2tlbml6ZXIoKQogICAgICAgICAgICByZXBvcnQgPSBzZWxmLl9wbGFuKHRva2VuaXplciwgcmVxdWVzdHMpCiAgICAgICAgICAgIHNlbGYuX3dyaXRlX3JlcG9ydChyZXBvcnQpCiAgICAgICAgICAgIExPR0dFUi5pbmZvKCJnYXRld2F5IGNvbXBsZXRlZCBpbiAlLjNmIHNlY29uZHMiLCB0aW1lLm1vbm90b25pYygpIC0gc3RhcnRlZCkKICAgICAgICAgICAgcmV0dXJuIDAKICAgICAgICBleGNlcHQgRXhjZXB0aW9uOgogICAgICAgICAgICBMT0dHRVIuZXhjZXB0aW9uKCJwcm9tcHQgZ2F0ZXdheSBmYWlsZWQgd2hpbGUgcHJlcGFyaW5nIHRoZSBuZXh0IHJlcXVlc3QgYmF0Y2giKQogICAgICAgICAgICByZXR1cm4gMQogICAgICAgIGZpbmFsbHk6CiAgICAgICAgICAgIHJheS5zaHV0ZG93bigpCgoKZGVmIG1haW4oYXJndjogbGlzdFtzdHJdIHwgTm9uZSA9IE5vbmUpIC0+IGludDoKICAgIGFyZ3MgPSBwYXJzZV9hcmdzKGFyZ3YpCiAgICBjb25maWd1cmVfbG9nZ2luZyhhcmdzLmxvZ19sZXZlbCkKICAgIHNldHRpbmdzID0gR2F0ZXdheVNldHRpbmdzLmxvYWQoYXJncy5jb25maWcpCiAgICBMT0dHRVIuaW5mbygic3RhcnRpbmcgcHJvbXB0IGdhdGV3YXkgd2l0aCBjb25maWcgJXMiLCBhcmdzLmNvbmZpZy5yZXNvbHZlKCkpCiAgICByZXR1cm4gUHJvbXB0R2F0ZXdheUFwcGxpY2F0aW9uKHNldHRpbmdzLCBhcmdzLm91dHB1dCkucnVuKCkKCgppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOgogICAgcmFpc2UgU3lzdGVtRXhpdChtYWluKHN5cy5hcmd2WzE6XSkpCg== | base64 -d > /workspace/prompt-gateway/main.py \
 && install -d /workspace/prompt-gateway \
 && printf '%s' ewogICJyZXBvc2l0b3J5IjogIlF3ZW4vUXdlbjIuNS0wLjVCLUluc3RydWN0IiwKICAicmV2aXNpb24iOiAiN2FlNTU3NjA0YWRmNjdiZTUwNDE3ZjU5YzJjMmYxNjdkZWY5YTc3NSIsCiAgImxhc3RfbW9kaWZpZWQiOiAiMjAyNC0wOS0yNVQxMjozMjo1NloiLAogICJsaWNlbnNlIjogIkFwYWNoZS0yLjAiLAogICJmaWxlcyI6IHsKICAgICJMSUNFTlNFIjogIjgzMmRkOWUwMGE2OGRkODNiM2MzZmI5ZjU1ODhkYWQ3ZGNmMzM3YTBkYjUwZjdkOTQ4M2YzMTBjZDI5MmU5MmUiLAogICAgImNvbmZpZy5qc29uIjogIjE4ZTE4YWZjYWNjYWZhZGU5OGRhZjEzYTU0MDkyOTI3OTA0NjQ5ZTFkZDRlYmE4Mjk5YWI3MTdkNWQ5NGZmNDUiLAogICAgImdlbmVyYXRpb25fY29uZmlnLmpzb24iOiAiZTU1ODg0N2E4YjQ0MDI2MTZmMTI3Mzc5N2IwMTUxMDRkYzI2NmZlNGI1MjAwNTZmY2E4ODgyM2JhOGY4ZWJlNiIsCiAgICAibWVyZ2VzLnR4dCI6ICI1OTliYWI1NDA3NTA4ODc3NGIxNzMzZmRlODY1ZDViZDc0N2NiY2M3YTU0N2M1YmMxMjYxMGU4NzRlMjZmNWUzIiwKICAgICJ0b2tlbml6ZXIuanNvbiI6ICJjMDM4MjExN2VhMzI5Y2RmMDk3MDQxMTMyZjZkNzM1OTI0YjY5NzkyNGQ2ZjZmYzM5NDU3MTNlOTZjZTg3NTM5IiwKICAgICJ0b2tlbml6ZXJfY29uZmlnLmpzb24iOiAiNWI1ZDRmNjVkMGFjZDNiMmQ1NmEzNWI1NmQzNzRhMzZjYmMxYzhmYTVjZjNiM2ZlYmJiZmFiZjIyZjM1OTU4MyIsCiAgICAidm9jYWIuanNvbiI6ICJjYTEwZDdlOWZiM2VkMTg1NzVkZDFlMjc3YTI1NzljMTZkMTA4ZTMyZjI3NDM5Njg0YWZhMGUxMGIxNDQwOTEwIgogIH0KfQo= | base64 -d > /workspace/prompt-gateway/model-assets.json \
 && install -d /workspace/prompt-gateway \
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGhhc2hsaWIKZnJvbSBkYXRhY2xhc3NlcyBpbXBvcnQgYXNkaWN0CmZyb20gdHlwaW5nIGltcG9ydCBBbnksIEl0ZXJhYmxlCgppbXBvcnQgcmF5Cgpmcm9tIGRvbWFpbiBpbXBvcnQgKAogICAgR2F0ZXdheVJlcG9ydCwKICAgIEluc3BlY3RlZFJlcXVlc3QsCiAgICBQbGFubmVkQmF0Y2gsCiAgICBSZWplY3RlZFJlcXVlc3QsCiAgICBSZXF1ZXN0RW52ZWxvcGUsCiAgICBzdGFibGVfcHJpb3JpdHlfb3JkZXIsCikKZnJvbSBnYXRld2F5X2NvbmZpZyBpbXBvcnQgQWRtaXNzaW9uU2V0dGluZ3MKCgpjbGFzcyBSdW50aW1lVG9rZW5pemVyQ2xpZW50OgogICAgZGVmIF9faW5pdF9fKHNlbGYsIHRva2VuaXplcjogQW55KSAtPiBOb25lOgogICAgICAgIHNlbGYuX3Rva2VuaXplciA9IHRva2VuaXplcgoKICAgIGRlZiBlbmNvZGUoc2VsZiwgcHJvbXB0OiBzdHIpIC0+IHR1cGxlW2ludCwgLi4uXToKICAgICAgICB0b2tlbl9pZHMgPSBzZWxmLl90b2tlbml6ZXIuZW5jb2RlKHByb21wdCwgYWRkX3NwZWNpYWxfdG9rZW5zPUZhbHNlKQogICAgICAgIHJldHVybiB0dXBsZShpbnQodG9rZW5faWQpIGZvciB0b2tlbl9pZCBpbiB0b2tlbl9pZHMpCgoKY2xhc3MgUHJvbXB0SW5zcGVjdG9yOgogICAgZGVmIF9faW5pdF9fKHNlbGYsIHRva2VuaXplcjogUnVudGltZVRva2VuaXplckNsaWVudCwgc2V0dGluZ3M6IEFkbWlzc2lvblNldHRpbmdzKSAtPiBOb25lOgogICAgICAgIHNlbGYuX3Rva2VuaXplciA9IHRva2VuaXplcgogICAgICAgIHNlbGYuX3NldHRpbmdzID0gc2V0dGluZ3MKCiAgICBkZWYgaW5zcGVjdChzZWxmLCByZXF1ZXN0OiBSZXF1ZXN0RW52ZWxvcGUpIC0+IEluc3BlY3RlZFJlcXVlc3QgfCBSZWplY3RlZFJlcXVlc3Q6CiAgICAgICAgdG9rZW5faWRzID0gc2VsZi5fdG9rZW5pemVyLmVuY29kZShyZXF1ZXN0LnByb21wdCkKICAgICAgICBpbnB1dF90b2tlbnMgPSBsZW4odG9rZW5faWRzKQogICAgICAgIGlmIGlucHV0X3Rva2VucyA+IHNlbGYuX3NldHRpbmdzLnJlcXVlc3RfdG9rZW5fbGltaXQ6CiAgICAgICAgICAgIHJldHVybiBSZWplY3RlZFJlcXVlc3QoCiAgICAgICAgICAgICAgICByZXF1ZXN0X2lkPXJlcXVlc3QucmVxdWVzdF9pZCwKICAgICAgICAgICAgICAgIHJlYXNvbj0iaW5wdXQgdG9rZW4gbGltaXQgZXhjZWVkZWQiLAogICAgICAgICAgICAgICAgb2JzZXJ2ZWRfdG9rZW5zPWlucHV0X3Rva2VucywKICAgICAgICAgICAgKQogICAgICAgIHJlc2VydmVkX291dHB1dCA9IG1heCgKICAgICAgICAgICAgcmVxdWVzdC5yZXF1ZXN0ZWRfb3V0cHV0X3Rva2VucywKICAgICAgICAgICAgc2VsZi5fc2V0dGluZ3MucmVzZXJ2ZV9vdXRwdXRfdG9rZW5zLAogICAgICAgICkKICAgICAgICByZXR1cm4gSW5zcGVjdGVkUmVxdWVzdCgKICAgICAgICAgICAgcmVxdWVzdD1yZXF1ZXN0LAogICAgICAgICAgICBpbnB1dF90b2tlbl9pZHM9dG9rZW5faWRzLAogICAgICAgICAgICBpbnB1dF90b2tlbnM9aW5wdXRfdG9rZW5zLAogICAgICAgICAgICB0b3RhbF9yZXNlcnZlZF90b2tlbnM9aW5wdXRfdG9rZW5zICsgcmVzZXJ2ZWRfb3V0cHV0LAogICAgICAgICkKCgpjbGFzcyBCYXRjaEJ1aWxkZXI6CiAgICBkZWYgX19pbml0X18oc2VsZiwgc2V0dGluZ3M6IEFkbWlzc2lvblNldHRpbmdzKSAtPiBOb25lOgogICAgICAgIHNlbGYuX3NldHRpbmdzID0gc2V0dGluZ3MKCiAgICBAc3RhdGljbWV0aG9kCiAgICBkZWYgX2JhdGNoX2lkKGl0ZW1zOiBJdGVyYWJsZVtJbnNwZWN0ZWRSZXF1ZXN0XSkgLT4gc3RyOgogICAgICAgIHJlcXVlc3RfaWRzID0gIiwiLmpvaW4oaXRlbS5yZXF1ZXN0LnJlcXVlc3RfaWQgZm9yIGl0ZW0gaW4gaXRlbXMpCiAgICAgICAgcmV0dXJuIGhhc2hsaWIuc2hhMjU2KHJlcXVlc3RfaWRzLmVuY29kZSgidXRmLTgiKSkuaGV4ZGlnZXN0KClbOjEyXQoKICAgIGRlZiBidWlsZChzZWxmLCByZXF1ZXN0czogdHVwbGVbSW5zcGVjdGVkUmVxdWVzdCwgLi4uXSkgLT4gdHVwbGVbUGxhbm5lZEJhdGNoLCAuLi5dOgogICAgICAgIGJhdGNoZXM6IGxpc3RbUGxhbm5lZEJhdGNoXSA9IFtdCiAgICAgICAgY3VycmVudDogbGlzdFtJbnNwZWN0ZWRSZXF1ZXN0XSA9IFtdCiAgICAgICAgY3VycmVudF90b2tlbnMgPSAwCgogICAgICAgIGRlZiBmbHVzaCgpIC0+IE5vbmU6CiAgICAgICAgICAgIG5vbmxvY2FsIGN1cnJlbnQsIGN1cnJlbnRfdG9rZW5zCiAgICAgICAgICAgIGlmIG5vdCBjdXJyZW50OgogICAgICAgICAgICAgICAgcmV0dXJuCiAgICAgICAgICAgIGJhdGNoZXMuYXBwZW5kKAogICAgICAgICAgICAgICAgUGxhbm5lZEJhdGNoKAogICAgICAgICAgICAgICAgICAgIGJhdGNoX2lkPXNlbGYuX2JhdGNoX2lkKGN1cnJlbnQpLAogICAgICAgICAgICAgICAgICAgIHJlcXVlc3RfaWRzPXR1cGxlKGl0ZW0ucmVxdWVzdC5yZXF1ZXN0X2lkIGZvciBpdGVtIGluIGN1cnJlbnQpLAogICAgICAgICAgICAgICAgICAgIHJlc2VydmVkX3Rva2Vucz1jdXJyZW50X3Rva2VucywKICAgICAgICAgICAgICAgICAgICB0ZW5hbnRzPXR1cGxlKHNvcnRlZCh7aXRlbS5yZXF1ZXN0LnRlbmFudCBmb3IgaXRlbSBpbiBjdXJyZW50fSkpLAogICAgICAgICAgICAgICAgKQogICAgICAgICAgICApCiAgICAgICAgICAgIGN1cnJlbnQgPSBbXQogICAgICAgICAgICBjdXJyZW50X3Rva2VucyA9IDAKCiAgICAgICAgZm9yIHJlcXVlc3QgaW4gcmVxdWVzdHM6CiAgICAgICAgICAgIHdvdWxkX2V4Y2VlZF90b2tlbnMgPSAoCiAgICAgICAgICAgICAgICBjdXJyZW50X3Rva2VucyArIHJlcXVlc3QudG90YWxfcmVzZXJ2ZWRfdG9rZW5zCiAgICAgICAgICAgICAgICA+IHNlbGYuX3NldHRpbmdzLmJhdGNoX3Rva2VuX2xpbWl0CiAgICAgICAgICAgICkKICAgICAgICAgICAgd291bGRfZXhjZWVkX3NpemUgPSBsZW4oY3VycmVudCkgPj0gc2VsZi5fc2V0dGluZ3MubWF4X2JhdGNoX3NpemUKICAgICAgICAgICAgaWYgY3VycmVudCBhbmQgKHdvdWxkX2V4Y2VlZF90b2tlbnMgb3Igd291bGRfZXhjZWVkX3NpemUpOgogICAgICAgICAgICAgICAgZmx1c2goKQogICAgICAgICAgICBjdXJyZW50LmFwcGVuZChyZXF1ZXN0KQogICAgICAgICAgICBjdXJyZW50X3Rva2VucyArPSByZXF1ZXN0LnRvdGFsX3Jlc2VydmVkX3Rva2VucwogICAgICAgIGZsdXNoKCkKICAgICAgICByZXR1cm4gdHVwbGUoYmF0Y2hlcykKCgpjbGFzcyBBZG1pc3Npb25QaXBlbGluZToKICAgIGRlZiBfX2luaXRfXyhzZWxmLCB0b2tlbml6ZXI6IEFueSwgc2V0dGluZ3M6IEFkbWlzc2lvblNldHRpbmdzKSAtPiBOb25lOgogICAgICAgIGNsaWVudCA9IFJ1bnRpbWVUb2tlbml6ZXJDbGllbnQodG9rZW5pemVyKQogICAgICAgIHNlbGYuX2luc3BlY3RvciA9IFByb21wdEluc3BlY3RvcihjbGllbnQsIHNldHRpbmdzKQogICAgICAgIHNlbGYuX2JhdGNoX2J1aWxkZXIgPSBCYXRjaEJ1aWxkZXIoc2V0dGluZ3MpCgogICAgZGVmIHJ1bihzZWxmLCByZXF1ZXN0czogdHVwbGVbUmVxdWVzdEVudmVsb3BlLCAuLi5dKSAtPiBHYXRld2F5UmVwb3J0OgogICAgICAgIGFjY2VwdGVkOiBsaXN0W0luc3BlY3RlZFJlcXVlc3RdID0gW10KICAgICAgICByZWplY3RlZDogbGlzdFtSZWplY3RlZFJlcXVlc3RdID0gW10KICAgICAgICBvcmRlcmVkID0gc3RhYmxlX3ByaW9yaXR5X29yZGVyKHJlcXVlc3RzKQogICAgICAgIGZvciByZXF1ZXN0IGluIG9yZGVyZWQ6CiAgICAgICAgICAgIGluc3BlY3RlZCA9IHNlbGYuX2luc3BlY3Rvci5pbnNwZWN0KHJlcXVlc3QpCiAgICAgICAgICAgIGlmIGlzaW5zdGFuY2UoaW5zcGVjdGVkLCBSZWplY3RlZFJlcXVlc3QpOgogICAgICAgICAgICAgICAgcmVqZWN0ZWQuYXBwZW5kKGluc3BlY3RlZCkKICAgICAgICAgICAgZWxzZToKICAgICAgICAgICAgICAgIGFjY2VwdGVkLmFwcGVuZChpbnNwZWN0ZWQpCiAgICAgICAgYWNjZXB0ZWRfdHVwbGUgPSB0dXBsZShhY2NlcHRlZCkKICAgICAgICBiYXRjaGVzID0gc2VsZi5fYmF0Y2hfYnVpbGRlci5idWlsZChhY2NlcHRlZF90dXBsZSkKICAgICAgICBjb3VudGVycyA9IHsKICAgICAgICAgICAgInJlY2VpdmVkIjogbGVuKHJlcXVlc3RzKSwKICAgICAgICAgICAgImFjY2VwdGVkIjogbGVuKGFjY2VwdGVkX3R1cGxlKSwKICAgICAgICAgICAgInJlamVjdGVkIjogbGVuKHJlamVjdGVkKSwKICAgICAgICAgICAgImJhdGNoZXMiOiBsZW4oYmF0Y2hlcyksCiAgICAgICAgICAgICJhY2NlcHRlZF9pbnB1dF90b2tlbnMiOiBzdW0oaXRlbS5pbnB1dF90b2tlbnMgZm9yIGl0ZW0gaW4gYWNjZXB0ZWRfdHVwbGUpLAogICAgICAgICAgICAicmVzZXJ2ZWRfdG9rZW5zIjogc3VtKGl0ZW0udG90YWxfcmVzZXJ2ZWRfdG9rZW5zIGZvciBpdGVtIGluIGFjY2VwdGVkX3R1cGxlKSwKICAgICAgICB9CiAgICAgICAgcmV0dXJuIEdhdGV3YXlSZXBvcnQoCiAgICAgICAgICAgIGFjY2VwdGVkPWFjY2VwdGVkX3R1cGxlLAogICAgICAgICAgICByZWplY3RlZD10dXBsZShyZWplY3RlZCksCiAgICAgICAgICAgIGJhdGNoZXM9YmF0Y2hlcywKICAgICAgICAgICAgY291bnRlcnM9Y291bnRlcnMsCiAgICAgICAgKQoKCmRlZiBfcmVxdWVzdF9mcm9tX3BheWxvYWQocGF5bG9hZDogZGljdFtzdHIsIEFueV0pIC0+IFJlcXVlc3RFbnZlbG9wZToKICAgIG1ldGFkYXRhID0ge3N0cihrZXkpOiBzdHIodmFsdWUpIGZvciBrZXksIHZhbHVlIGluIGRpY3QocGF5bG9hZC5nZXQoIm1ldGFkYXRhIiwge30pKS5pdGVtcygpfQogICAgcmV0dXJuIFJlcXVlc3RFbnZlbG9wZSgKICAgICAgICByZXF1ZXN0X2lkPXN0cihwYXlsb2FkWyJyZXF1ZXN0X2lkIl0pLAogICAgICAgIHRlbmFudD1zdHIocGF5bG9hZFsidGVuYW50Il0pLAogICAgICAgIHByb21wdD1zdHIocGF5bG9hZFsicHJvbXB0Il0pLAogICAgICAgIHJlcXVlc3RlZF9vdXRwdXRfdG9rZW5zPWludChwYXlsb2FkWyJyZXF1ZXN0ZWRfb3V0cHV0X3Rva2VucyJdKSwKICAgICAgICBwcmlvcml0eT1pbnQocGF5bG9hZC5nZXQoInByaW9yaXR5IiwgMCkpLAogICAgICAgIG1ldGFkYXRhPW1ldGFkYXRhLAogICAgKQoKCkByYXkucmVtb3RlKG51bV9jcHVzPTEpCmRlZiBwbGFuX3JlbW90ZV9iYXRjaCgKICAgIHRva2VuaXplcjogQW55LAogICAgcmF3X3JlcXVlc3RzOiBsaXN0W2RpY3Rbc3RyLCBBbnldXSwKICAgIHJhd19zZXR0aW5nczogZGljdFtzdHIsIEFueV0sCikgLT4gZGljdFtzdHIsIEFueV06CiAgICBzZXR0aW5ncyA9IEFkbWlzc2lvblNldHRpbmdzKCoqcmF3X3NldHRpbmdzKQogICAgcmVxdWVzdHMgPSB0dXBsZShfcmVxdWVzdF9mcm9tX3BheWxvYWQocGF5bG9hZCkgZm9yIHBheWxvYWQgaW4gcmF3X3JlcXVlc3RzKQogICAgcmVwb3J0ID0gQWRtaXNzaW9uUGlwZWxpbmUodG9rZW5pemVyLCBzZXR0aW5ncykucnVuKHJlcXVlc3RzKQogICAgcmV0dXJuIHJlcG9ydC50b19tYXBwaW5nKCkKCgpkZWYgcmVxdWVzdF9wYXlsb2FkcyhyZXF1ZXN0czogdHVwbGVbUmVxdWVzdEVudmVsb3BlLCAuLi5dKSAtPiBsaXN0W2RpY3Rbc3RyLCBBbnldXToKICAgIHJldHVybiBbYXNkaWN0KHJlcXVlc3QpIGZvciByZXF1ZXN0IGluIHJlcXVlc3RzXQoKCmRlZiBhZG1pc3Npb25fc2V0dGluZ3NfcGF5bG9hZChzZXR0aW5nczogQWRtaXNzaW9uU2V0dGluZ3MpIC0+IGRpY3Rbc3RyLCBBbnldOgogICAgcmV0dXJuIGFzZGljdChzZXR0aW5ncykK | base64 -d > /workspace/prompt-gateway/pipeline.py \
 && install -d /workspace/prompt-gateway \
 && printf '%s' eyJyZXF1ZXN0X2lkIjoic3VwcG9ydC0yMDI2LTA5MTgiLCJ0ZW5hbnQiOiJjdXN0b21lci1zdXBwb3J0IiwicHJvbXB0IjoiU3VtbWFyaXplIHRoaXMgc3VwcG9ydCBjb252ZXJzYXRpb24gZm9yIHRoZSBuZXh0IGFnZW50LiBUaGUgY3VzdG9tZXIgdXBncmFkZWQgdGhlIGRlc2t0b3AgY2xpZW50IHllc3RlcmRheS4gU2lnbi1pbiBzdWNjZWVkcywgYnV0IGV2ZXJ5IG5ld2x5IG9wZW5lZCBwcm9qZWN0IHJlbWFpbnMgb24gdGhlIGxvYWRpbmcgc2NyZWVuLiBFeGlzdGluZyBwcm9qZWN0cyBzdGlsbCBvcGVuIGZyb20gdGhlIHJlY2VudC1pdGVtcyBsaXN0LiBJbmNsdWRlIHRoZSBvYnNlcnZlZCBiZWhhdmlvciwgdGhlIGF0dGVtcHRlZCByZWluc3RhbGwsIGFuZCB0aGUgbmV4dCBkaWFnbm9zdGljIHN0ZXAgd2l0aG91dCBndWVzc2luZyBhIHJvb3QgY2F1c2UuIiwicmVxdWVzdGVkX291dHB1dF90b2tlbnMiOjk2LCJwcmlvcml0eSI6MTAsIm1ldGFkYXRhIjp7ImNoYW5uZWwiOiJzdXBwb3J0LWNvbnNvbGUiLCJsYW5ndWFnZSI6ImVuIn19CnsicmVxdWVzdF9pZCI6Im9wcy1pbmNpZGVudC0xODQyIiwidGVuYW50Ijoib3BlcmF0aW9ucyIsInByb21wdCI6IlR1cm4gdGhpcyBpbmNpZGVudCB1cGRhdGUgaW50byBhIGNvbmNpc2UgaW50ZXJuYWwgc3RhdHVzIG5vdGUuIEF0IDA5OjEwIHRoZSBpbmdlc3Rpb24gcXVldWUgYmVnYW4gZ3Jvd2luZyBpbiB0aGUgd2VzdCByZWdpb24uIFRoZSBBUEkgZXJyb3IgcmF0ZSBzdGF5ZWQgYmVsb3cgb25lIHBlcmNlbnQsIGJ1dCBwcm9jZXNzaW5nIGxhdGVuY3kgcmVhY2hlZCBlaWdodGVlbiBtaW51dGVzLiBUaGUgdGVhbSBzaGlmdGVkIG5ldyB1cGxvYWRzIHRvIHRoZSBjZW50cmFsIHJlZ2lvbiBhdCAwOTozNCBhbmQgdGhlIGJhY2tsb2cgaGFzIGJlZW4gZmFsbGluZyBzaW5jZSAwOTo0Ny4gU3RhdGUgdGhlIGN1cnJlbnQgaW1wYWN0IGFuZCB0aGUgbmV4dCBjaGVja3BvaW50LiIsInJlcXVlc3RlZF9vdXRwdXRfdG9rZW5zIjo4MCwicHJpb3JpdHkiOjIwLCJtZXRhZGF0YSI6eyJjaGFubmVsIjoiaW5jaWRlbnQtYm90IiwibGFuZ3VhZ2UiOiJlbiJ9fQp7InJlcXVlc3RfaWQiOiJtZWV0aW5nLWFjdGlvbnMtNTU3IiwidGVuYW50IjoiY29sbGFib3JhdGlvbiIsInByb21wdCI6IkV4dHJhY3Qgb3duZXJzIGFuZCBhY3Rpb24gaXRlbXMgZnJvbSB0aGVzZSBtZWV0aW5nIG5vdGVzLiBQcml5YSB3aWxsIHZlcmlmeSB0aGUgbWlncmF0aW9uIGNoZWNrbGlzdCBieSBUaHVyc2RheS4gTWF0ZW8gd2lsbCBjb21wYXJlIHRoZSB0d28gc3RvcmFnZSBlc3RpbWF0ZXMgYW5kIHBvc3QgdGhlIHJlc3VsdCBpbiB0aGUgcHJvamVjdCByb29tLiBMaW4gd2lsbCBzY2hlZHVsZSBhIHR3ZW50eS1taW51dGUgcmV2aWV3IGFmdGVyIGJvdGggaXRlbXMgYXJlIGNvbXBsZXRlLiBLZWVwIHVucmVzb2x2ZWQgZGF0ZXMgbWFya2VkIGFzIHBlbmRpbmcuIiwicmVxdWVzdGVkX291dHB1dF90b2tlbnMiOjcyLCJwcmlvcml0eSI6NSwibWV0YWRhdGEiOnsiY2hhbm5lbCI6IndvcmtzcGFjZS1hc3Npc3RhbnQiLCJsYW5ndWFnZSI6ImVuIn19Cg== | base64 -d > /workspace/prompt-gateway/requests.jsonl \
 && install -d /workspace/prompt-gateway \
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IG9zCmZyb20gZGF0YWNsYXNzZXMgaW1wb3J0IGFzZGljdApmcm9tIHR5cGluZyBpbXBvcnQgQW55CgppbXBvcnQgcmF5Cgpmcm9tIGdhdGV3YXlfY29uZmlnIGltcG9ydCBFbmdpbmVTZXR0aW5ncwoKCkByYXkucmVtb3RlKG51bV9jcHVzPTIpCmNsYXNzIFZsbG1SdW50aW1lOgogICAgZGVmIF9faW5pdF9fKHNlbGYsIHJhd19zZXR0aW5nczogZGljdFtzdHIsIEFueV0pIC0+IE5vbmU6CiAgICAgICAgb3MuZW52aXJvbi5zZXRkZWZhdWx0KCJWTExNX0xPR0dJTkdfTEVWRUwiLCAiV0FSTklORyIpCiAgICAgICAgb3MuZW52aXJvbi5zZXRkZWZhdWx0KCJWTExNX0VOQUJMRV9WMV9NVUxUSVBST0NFU1NJTkciLCAiMCIpCiAgICAgICAgb3MuZW52aXJvbi5zZXRkZWZhdWx0KCJWTExNX0NQVV9LVkNBQ0hFX1NQQUNFIiwgIjEiKQogICAgICAgIGZyb20gdmxsbSBpbXBvcnQgTExNCgogICAgICAgIHNldHRpbmdzID0gRW5naW5lU2V0dGluZ3MoCiAgICAgICAgICAgIG1vZGVsX3BhdGg9cmF3X3NldHRpbmdzWyJtb2RlbF9wYXRoIl0sCiAgICAgICAgICAgIG1heF9tb2RlbF9sZW49aW50KHJhd19zZXR0aW5nc1sibWF4X21vZGVsX2xlbiJdKSwKICAgICAgICAgICAgbWF4X251bV9zZXFzPWludChyYXdfc2V0dGluZ3NbIm1heF9udW1fc2VxcyJdKSwKICAgICAgICAgICAgbWF4X251bV9iYXRjaGVkX3Rva2Vucz1pbnQocmF3X3NldHRpbmdzWyJtYXhfbnVtX2JhdGNoZWRfdG9rZW5zIl0pLAogICAgICAgICkKICAgICAgICBzZWxmLl9zZXR0aW5ncyA9IHNldHRpbmdzCiAgICAgICAgc2VsZi5fZW5naW5lID0gTExNKAogICAgICAgICAgICBtb2RlbD1zdHIoc2V0dGluZ3MubW9kZWxfcGF0aCksCiAgICAgICAgICAgIHRva2VuaXplcj1zdHIoc2V0dGluZ3MubW9kZWxfcGF0aCksCiAgICAgICAgICAgIGxvYWRfZm9ybWF0PSJkdW1teSIsCiAgICAgICAgICAgIGR0eXBlPSJmbG9hdDMyIiwKICAgICAgICAgICAgZW5mb3JjZV9lYWdlcj1UcnVlLAogICAgICAgICAgICB0cnVzdF9yZW1vdGVfY29kZT1GYWxzZSwKICAgICAgICAgICAgbWF4X21vZGVsX2xlbj1zZXR0aW5ncy5tYXhfbW9kZWxfbGVuLAogICAgICAgICAgICBtYXhfbnVtX3NlcXM9c2V0dGluZ3MubWF4X251bV9zZXFzLAogICAgICAgICAgICBtYXhfbnVtX2JhdGNoZWRfdG9rZW5zPXNldHRpbmdzLm1heF9udW1fYmF0Y2hlZF90b2tlbnMsCiAgICAgICAgICAgIGRpc2FibGVfbG9nX3N0YXRzPVRydWUsCiAgICAgICAgKQoKICAgIGRlZiBoZWFsdGgoc2VsZikgLT4gZGljdFtzdHIsIEFueV06CiAgICAgICAgdG9rZW5pemVyID0gc2VsZi5fZW5naW5lLmdldF90b2tlbml6ZXIoKQogICAgICAgIHRva2VuaXplci5lbmNvZGUoImhlYWx0aCBjaGVjayIsIGFkZF9zcGVjaWFsX3Rva2Vucz1GYWxzZSkKICAgICAgICByZXR1cm4gewogICAgICAgICAgICAicmVhZHkiOiBUcnVlLAogICAgICAgICAgICAibWF4X21vZGVsX2xlbiI6IHNlbGYuX3NldHRpbmdzLm1heF9tb2RlbF9sZW4sCiAgICAgICAgfQoKICAgIGRlZiBnZXRfcnVudGltZV90b2tlbml6ZXIoc2VsZik6CiAgICAgICAgcmV0dXJuIHNlbGYuX2VuZ2luZS5nZXRfdG9rZW5pemVyKCkKCiAgICBkZWYgc2V0dGluZ3Moc2VsZikgLT4gZGljdFtzdHIsIEFueV06CiAgICAgICAgcmVzdWx0ID0gYXNkaWN0KHNlbGYuX3NldHRpbmdzKQogICAgICAgIHJlc3VsdFsibW9kZWxfcGF0aCJdID0gc3RyKHNlbGYuX3NldHRpbmdzLm1vZGVsX3BhdGgpCiAgICAgICAgcmV0dXJuIHJlc3VsdAoKCmRlZiBlbmdpbmVfc2V0dGluZ3NfcGF5bG9hZChzZXR0aW5nczogRW5naW5lU2V0dGluZ3MpIC0+IGRpY3Rbc3RyLCBBbnldOgogICAgcmV0dXJuIHsKICAgICAgICAibW9kZWxfcGF0aCI6IHN0cihzZXR0aW5ncy5tb2RlbF9wYXRoKSwKICAgICAgICAibWF4X21vZGVsX2xlbiI6IHNldHRpbmdzLm1heF9tb2RlbF9sZW4sCiAgICAgICAgIm1heF9udW1fc2VxcyI6IHNldHRpbmdzLm1heF9udW1fc2VxcywKICAgICAgICAibWF4X251bV9iYXRjaGVkX3Rva2VucyI6IHNldHRpbmdzLm1heF9udW1fYmF0Y2hlZF90b2tlbnMsCiAgICB9Cg== | base64 -d > /workspace/prompt-gateway/runtime.py \
 && install -d /workspace/prompt-gateway \
 && printf '%s' ewogICJlbmdpbmUiOiB7CiAgICAibW9kZWxfcGF0aCI6ICJtb2RlbCIsCiAgICAibWF4X21vZGVsX2xlbiI6IDEyOCwKICAgICJtYXhfbnVtX3NlcXMiOiA4LAogICAgIm1heF9udW1fYmF0Y2hlZF90b2tlbnMiOiAyNTYKICB9LAogICJhZG1pc3Npb24iOiB7CiAgICAicmVxdWVzdF90b2tlbl9saW1pdCI6IDk2LAogICAgImJhdGNoX3Rva2VuX2xpbWl0IjogMTYwLAogICAgIm1heF9iYXRjaF9zaXplIjogNCwKICAgICJyZXNlcnZlX291dHB1dF90b2tlbnMiOiAxNgogIH0sCiAgInJheSI6IHsKICAgICJudW1fY3B1cyI6IDQsCiAgICAibG9nX3RvX2RyaXZlciI6IGZhbHNlCiAgfSwKICAicmVxdWVzdHNfcGF0aCI6ICJyZXF1ZXN0cy5qc29ubCIKfQo= | base64 -d > /workspace/prompt-gateway/settings.json
LABEL ai.infra.bench.environment-template=vllm-harbor-all-in-one \
      ai.infra.bench.base-commit=$VLLM_BASE_SHA \
      ai.infra.bench.dependency-cutoff=$VLLM_DEPENDENCY_CUTOFF \
      ai.infra.bench.cache-namespace=$VLLM_CACHE_NAMESPACE
ENTRYPOINT []
CMD ["sleep", "infinity"]
