# syntax=docker/dockerfile:1
# Template inputs below are replaced from task.toml by generate.py. Generated
# task Dockerfiles are self-contained and differ only in their frozen inputs.

ARG VLLM_BASE_SHA=5e30e9b9a9b0dc91927f2ec4ffbd92c4af3825c0
ARG VLLM_DEPENDENCY_CUTOFF=2026-04-01T13:11:10Z
ARG VLLM_CACHE_NAMESPACE=5e30e9b9a9b0dc91927f2ec4ffbd92c4af3825c0-a6247e8bc078ef97-f6976e65056ca407
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

ARG CARGO_NEXTEST_VERSION=0.9.132
RUN case "$TARGETARCH" in \
      amd64) nextest_target=x86_64-unknown-linux-gnu; nextest_sha=e22f14ecaff5519dbfe521e8717d64e9989648bddc23eb1f71bb0053518a52e7 ;; \
      arm64) nextest_target=aarch64-unknown-linux-gnu; nextest_sha=592db3fa3d3ee62f109dc149554811eb8ecdc68e1514be5af79986b1560e2e0d ;; \
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
# Exact task dependency lock (sha256:a6247e8bc078ef97d01e65ec6c2c2957bc3174b6635cd28eb72e5478ea8b8d3d) is embedded so this
# Dockerfile remains independently buildable with an empty context.
RUN --mount=type=cache,id=vllm-uv-downloads-v3,target=/root/.cache/uv,sharing=locked <<'VLLM_INSTALL_EOF'
set -eu
cat > /tmp/vllm-requirements.lock <<'VLLM_REQUIREMENTS_EOF'
# Generated with uv 0.11.28 from the pinned base requirements and task
# extras for CPython 3.12 on x86_64 manylinux_2_28. Packages newer than
# 2026-04-01T13:11:10Z were excluded during resolution.
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
anthropic==0.87.0
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
charset-normalizer==3.4.6
    # via requests
click==8.3.1
    # via
    #   rich-toolkit
    #   typer
    #   uvicorn
cloudpickle==3.1.2
    # via -r requirements/common.txt
cmake==4.3.1
    # via -r requirements/cpu-build.txt
compressed-tensors==0.14.0.1
    # via -r requirements/common.txt
cryptography==46.0.6
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
docstring-parser==0.17.0
    # via anthropic
einops==0.8.2
    # via -r requirements/common.txt
email-validator==2.3.0
    # via
    #   fastapi
    #   pydantic
fastapi==0.135.2
    # via
    #   -r requirements/common.txt
    #   model-hosting-container-standards
fastapi-cli==0.0.24
    # via fastapi
fastapi-cloud-cli==0.15.1
    # via fastapi-cli
fastar==0.9.0
    # via fastapi-cloud-cli
filelock==3.25.2
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
googleapis-common-protos==1.73.1
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
    #   -r requirements/cpu-build.txt
    #   fastapi
    #   torch
jiter==0.13.0
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
mcp==1.26.0
    # via -r requirements/common.txt
mdurl==0.1.2
    # via markdown-it-py
mistral-common==1.10.0
    # via -r requirements/common.txt
model-hosting-container-standards==0.1.14
    # via -r requirements/common.txt
mpmath==1.3.0
    # via sympy
msgspec==0.20.0
    # via -r requirements/common.txt
multidict==6.7.1
    # via
    #   aiohttp
    #   yarl
networkx==3.6.1
    # via torch
ninja==1.13.0
    # via
    #   -r requirements/common.txt
    #   -r requirements/cpu-build.txt
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
openai==2.30.0
    # via -r requirements/common.txt
openai-harmony==0.0.8
    # via -r requirements/common.txt
opencv-python-headless==4.13.0.92
    # via
    #   -r requirements/common.txt
    #   mistral-common
opentelemetry-api==1.40.0
    # via
    #   -r requirements/common.txt
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
    #   opentelemetry-sdk
    #   opentelemetry-semantic-conventions
opentelemetry-exporter-otlp==1.40.0
    # via -r requirements/common.txt
opentelemetry-exporter-otlp-proto-common==1.40.0
    # via
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
opentelemetry-exporter-otlp-proto-grpc==1.40.0
    # via opentelemetry-exporter-otlp
opentelemetry-exporter-otlp-proto-http==1.40.0
    # via opentelemetry-exporter-otlp
opentelemetry-proto==1.40.0
    # via
    #   opentelemetry-exporter-otlp-proto-common
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
opentelemetry-sdk==1.40.0
    # via
    #   -r requirements/common.txt
    #   opentelemetry-exporter-otlp-proto-grpc
    #   opentelemetry-exporter-otlp-proto-http
    #   opentelemetry-semantic-conventions-ai
opentelemetry-semantic-conventions==0.61b0
    # via
    #   opentelemetry-sdk
    #   opentelemetry-semantic-conventions-ai
opentelemetry-semantic-conventions-ai==0.5.1
    # via -r requirements/common.txt
outlines-core==0.2.11
    # via -r requirements/common.txt
packaging==26.0
    # via
    #   -r requirements/cpu-build.txt
    #   huggingface-hub
    #   lm-format-enforcer
    #   pytest
    #   setuptools-scm
    #   transformers
    #   vcs-versioning
    #   wheel
partial-json-parser==0.2.1.1.post7
    # via -r requirements/common.txt
pillow==12.1.1
    # via
    #   -r requirements/common.txt
    #   mistral-common
    #   torchvision
pluggy==1.6.0
    # via pytest
prometheus-client==0.24.1
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
pydantic==2.12.5
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
pydantic-core==2.41.5
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
pytest==9.0.2
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
python-multipart==0.0.22
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
regex==2026.3.32
    # via
    #   -r requirements/common.txt
    #   -r requirements/cpu-build.txt
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
rich==14.3.3
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
sentry-sdk==2.57.0
    # via fastapi-cloud-cli
setproctitle==1.3.7
    # via -r requirements/common.txt
setuptools==77.0.3
    # via
    #   -r requirements/common.txt
    #   -r requirements/cpu-build.txt
    #   -r requirements/cpu.txt
    #   model-hosting-container-standards
    #   setuptools-scm
    #   torch
setuptools-scm==10.0.5
    # via -r requirements/cpu-build.txt
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
torch==2.10.0+cpu
    # via
    #   -r requirements/cpu-build.txt
    #   -r requirements/cpu.txt
    #   compressed-tensors
    #   torchvision
    #   xgrammar
torchaudio==2.11.0+cpu
    # via -r requirements/cpu.txt
torchvision==0.25.0+cpu
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
uvicorn==0.42.0
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
    # via -r requirements/cpu-build.txt
xgrammar==0.1.33
    # via -r requirements/common.txt
yarl==1.23.0
    # via aiohttp
zipp==3.23.0
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
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGpzb24KaW1wb3J0IHNvY2tldAppbXBvcnQgc3VicHJvY2VzcwppbXBvcnQgc3lzCmltcG9ydCB0aW1lCgppbXBvcnQgaHR0cHgKCgpkZWYgZnJlZV9wb3J0KCkgLT4gaW50OgogICAgd2l0aCBzb2NrZXQuc29ja2V0KCkgYXMgc29jazoKICAgICAgICBzb2NrLmJpbmQoKCIxMjcuMC4wLjEiLCAwKSkKICAgICAgICByZXR1cm4gc29jay5nZXRzb2NrbmFtZSgpWzFdCgoKZGVmIHdhaXRfcmVhZHkocG9ydDogaW50KSAtPiBOb25lOgogICAgZGVhZGxpbmUgPSB0aW1lLm1vbm90b25pYygpICsgMjAKICAgIHdoaWxlIHRpbWUubW9ub3RvbmljKCkgPCBkZWFkbGluZToKICAgICAgICB0cnk6CiAgICAgICAgICAgIGlmIGh0dHB4LmdldChmImh0dHA6Ly8xMjcuMC4wLjE6e3BvcnR9L2RvY3MiLCB0aW1lb3V0PTAuMikuc3RhdHVzX2NvZGUgPT0gMjAwOgogICAgICAgICAgICAgICAgcmV0dXJuCiAgICAgICAgZXhjZXB0IGh0dHB4LkhUVFBFcnJvcjoKICAgICAgICAgICAgdGltZS5zbGVlcCgwLjA1KQogICAgcmFpc2UgUnVudGltZUVycm9yKCJsb2NhbCB0b2tlbiBzZXJ2ZXIgZGlkIG5vdCBzdGFydCIpCgoKZGVmIG1haW4oKSAtPiBpbnQ6CiAgICBwb3J0ID0gZnJlZV9wb3J0KCkKICAgIHByb2Nlc3MgPSBzdWJwcm9jZXNzLlBvcGVuKAogICAgICAgIFtzeXMuZXhlY3V0YWJsZSwgIi9vcHQvcmVwcm8vc3RyZWFtX3NlcnZlci5weSIsICItLXBvcnQiLCBzdHIocG9ydCldCiAgICApCiAgICB0cnk6CiAgICAgICAgd2FpdF9yZWFkeShwb3J0KQogICAgICAgIHVybCA9IGYiaHR0cDovLzEyNy4wLjAuMTp7cG9ydH0vaW5mZXJlbmNlL3YxL2dlbmVyYXRlIgogICAgICAgIGJvZHkgPSB7CiAgICAgICAgICAgICJyZXF1ZXN0X2lkIjogInB1YmxpYy1zdHJlYW0tdHJhY2UiLAogICAgICAgICAgICAidG9rZW5faWRzIjogWzEyODAwMCwgOTkwNiwgMTEsIDEyNjgsIDUyNywgNDk5LCAzMF0sCiAgICAgICAgICAgICJzYW1wbGluZ19wYXJhbXMiOiB7Im1heF90b2tlbnMiOiA4fSwKICAgICAgICAgICAgInN0cmVhbSI6IFRydWUsCiAgICAgICAgfQogICAgICAgIHdpdGggaHR0cHguc3RyZWFtKCJQT1NUIiwgdXJsLCBqc29uPWJvZHksIHRpbWVvdXQ9MTApIGFzIHJlc3BvbnNlOgogICAgICAgICAgICBsaW5lcyA9IFtsaW5lIGZvciBsaW5lIGluIHJlc3BvbnNlLml0ZXJfbGluZXMoKSBpZiBsaW5lXQogICAgICAgICAgICBjb250ZW50X3R5cGUgPSByZXNwb25zZS5oZWFkZXJzLmdldCgiY29udGVudC10eXBlIikKICAgICAgICBub25zdHJlYW0gPSBodHRweC5wb3N0KHVybCwganNvbj17Kipib2R5LCAic3RyZWFtIjogRmFsc2V9LCB0aW1lb3V0PTEwKQogICAgICAgIHJlc3VsdCA9IHsKICAgICAgICAgICAgInN0cmVhbV9zdGF0dXMiOiByZXNwb25zZS5zdGF0dXNfY29kZSwKICAgICAgICAgICAgInN0cmVhbV9jb250ZW50X3R5cGUiOiBjb250ZW50X3R5cGUsCiAgICAgICAgICAgICJzdHJlYW1fbGluZXMiOiBsaW5lcywKICAgICAgICAgICAgIm5vbnN0cmVhbV9zdGF0dXMiOiBub25zdHJlYW0uc3RhdHVzX2NvZGUsCiAgICAgICAgICAgICJub25zdHJlYW1fY29udGVudF90eXBlIjogbm9uc3RyZWFtLmhlYWRlcnMuZ2V0KCJjb250ZW50LXR5cGUiKSwKICAgICAgICAgICAgIm5vbnN0cmVhbV9ib2R5Ijogbm9uc3RyZWFtLmpzb24oKSwKICAgICAgICB9CiAgICAgICAgcHJpbnQoanNvbi5kdW1wcyhyZXN1bHQsIGluZGVudD0yKSkKICAgICAgICBwYXNzZWQgPSAoCiAgICAgICAgICAgIHJlc3BvbnNlLnN0YXR1c19jb2RlID09IDIwMAogICAgICAgICAgICBhbmQgY29udGVudF90eXBlIGlzIG5vdCBOb25lCiAgICAgICAgICAgIGFuZCBjb250ZW50X3R5cGUuc3RhcnRzd2l0aCgidGV4dC9ldmVudC1zdHJlYW0iKQogICAgICAgICAgICBhbmQgbGluZXNbLTFdID09ICJkYXRhOiBbRE9ORV0iCiAgICAgICAgICAgIGFuZCBsZW4obGluZXMpID49IDQKICAgICAgICAgICAgYW5kIG5vbnN0cmVhbS5zdGF0dXNfY29kZSA9PSAyMDAKICAgICAgICAgICAgYW5kIG5vbnN0cmVhbS5oZWFkZXJzWyJjb250ZW50LXR5cGUiXS5zdGFydHN3aXRoKCJhcHBsaWNhdGlvbi9qc29uIikKICAgICAgICApCiAgICAgICAgcHJpbnQoZiJ0b2tlbl9zdHJlYW1faHR0cF9jb250cmFjdD17cGFzc2VkfSIpCiAgICAgICAgcmV0dXJuIDAgaWYgcGFzc2VkIGVsc2UgMwogICAgZmluYWxseToKICAgICAgICBwcm9jZXNzLnRlcm1pbmF0ZSgpCiAgICAgICAgcHJvY2Vzcy53YWl0KHRpbWVvdXQ9MTApCgoKaWYgX19uYW1lX18gPT0gIl9fbWFpbl9fIjoKICAgIHJhaXNlIFN5c3RlbUV4aXQobWFpbigpKQo= | base64 -d > /opt/repro/http_stream_trace.py && install -d /opt/repro \
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGFzeW5jaW8KZnJvbSB0eXBlcyBpbXBvcnQgU2ltcGxlTmFtZXNwYWNlCgpmcm9tIGZhc3RhcGkgaW1wb3J0IEZhc3RBUEkKCgpkZWYgX2NvbXBsZXRpb24oaW5kZXg6IGludCwgdG9rZW5faWRzOiBsaXN0W2ludF0sIGZpbmlzaF9yZWFzb249Tm9uZSwgbG9ncHJvYnM9Tm9uZSk6CiAgICBmcm9tIHZsbG0ub3V0cHV0cyBpbXBvcnQgQ29tcGxldGlvbk91dHB1dAoKICAgIHJldHVybiBDb21wbGV0aW9uT3V0cHV0KAogICAgICAgIGluZGV4PWluZGV4LAogICAgICAgIHRleHQ9IiIsCiAgICAgICAgdG9rZW5faWRzPXRva2VuX2lkcywKICAgICAgICBjdW11bGF0aXZlX2xvZ3Byb2I9Tm9uZSwKICAgICAgICBsb2dwcm9icz1sb2dwcm9icywKICAgICAgICBmaW5pc2hfcmVhc29uPWZpbmlzaF9yZWFzb24sCiAgICApCgoKZGVmIF9yZXF1ZXN0X291dHB1dCgKICAgIHJlcXVlc3RfaWQ6IHN0ciwKICAgIHByb21wdF90b2tlbl9pZHM6IGxpc3RbaW50XSwKICAgIG91dHB1dHMsCiAgICAqLAogICAgZmluaXNoZWQ6IGJvb2wsCiAgICBudW1fY2FjaGVkX3Rva2VuczogaW50IHwgTm9uZSA9IE5vbmUsCik6CiAgICBmcm9tIHZsbG0ub3V0cHV0cyBpbXBvcnQgUmVxdWVzdE91dHB1dAoKICAgIHJldHVybiBSZXF1ZXN0T3V0cHV0KAogICAgICAgIHJlcXVlc3RfaWQ9cmVxdWVzdF9pZCwKICAgICAgICBwcm9tcHQ9Tm9uZSwKICAgICAgICBwcm9tcHRfdG9rZW5faWRzPXByb21wdF90b2tlbl9pZHMsCiAgICAgICAgcHJvbXB0X2xvZ3Byb2JzPU5vbmUsCiAgICAgICAgb3V0cHV0cz1vdXRwdXRzLAogICAgICAgIGZpbmlzaGVkPWZpbmlzaGVkLAogICAgICAgIG1ldHJpY3M9Tm9uZSwKICAgICAgICBsb3JhX3JlcXVlc3Q9Tm9uZSwKICAgICAgICBlbmNvZGVyX3Byb21wdD1Ob25lLAogICAgICAgIGVuY29kZXJfcHJvbXB0X3Rva2VuX2lkcz1Ob25lLAogICAgICAgIG51bV9jYWNoZWRfdG9rZW5zPW51bV9jYWNoZWRfdG9rZW5zLAogICAgKQoKCmNsYXNzIEZha2VFbmdpbmU6CiAgICBlcnJvcmVkID0gRmFsc2UKICAgIGRlYWRfZXJyb3IgPSBSdW50aW1lRXJyb3IoImVuZ2luZSB1bmF2YWlsYWJsZSIpCgogICAgYXN5bmMgZGVmIGlzX3RyYWNpbmdfZW5hYmxlZChzZWxmKSAtPiBib29sOgogICAgICAgIHJldHVybiBGYWxzZQoKICAgIGRlZiBnZW5lcmF0ZShzZWxmLCBlbmdpbmVfaW5wdXQsIHNhbXBsaW5nX3BhcmFtcywgcmVxdWVzdF9pZCwgKipfa3dhcmdzKToKICAgICAgICBmcm9tIHZsbG0ubG9ncHJvYnMgaW1wb3J0IExvZ3Byb2IKICAgICAgICBmcm9tIHZsbG0uc2FtcGxpbmdfcGFyYW1zIGltcG9ydCBSZXF1ZXN0T3V0cHV0S2luZAoKICAgICAgICBwcm9tcHQgPSBsaXN0KGVuZ2luZV9pbnB1dFsicHJvbXB0X3Rva2VuX2lkcyJdKQogICAgICAgIHNjZW5hcmlvID0gcHJvbXB0WzBdIGlmIHByb21wdCBlbHNlIDAKICAgICAgICBjb3VudCA9IHNhbXBsaW5nX3BhcmFtcy5uCiAgICAgICAgc3RyZWFtaW5nID0gc2FtcGxpbmdfcGFyYW1zLm91dHB1dF9raW5kID09IFJlcXVlc3RPdXRwdXRLaW5kLkRFTFRBCgogICAgICAgIGFzeW5jIGRlZiByZXN1bHRzKCk6CiAgICAgICAgICAgIGlmIG5vdCBzdHJlYW1pbmc6CiAgICAgICAgICAgICAgICBpZiBzY2VuYXJpbyA9PSA5MDE6CiAgICAgICAgICAgICAgICAgICAgY3VtdWxhdGl2ZV9zdGVwcyA9IFtbNzFdLCBbNzFdXQogICAgICAgICAgICAgICAgZWxpZiBzY2VuYXJpbyA9PSA5MDI6CiAgICAgICAgICAgICAgICAgICAgY3VtdWxhdGl2ZV9zdGVwcyA9IFtbNzFdLCBbNzFdLCBbNzEsIDcyLCA3M10sIFs3MSwgNzIsIDczLCA3NF1dCiAgICAgICAgICAgICAgICBlbHNlOgogICAgICAgICAgICAgICAgICAgIGN1bXVsYXRpdmVfc3RlcHMgPSBbWzcxXSwgWzcxLCA3MiwgNzNdLCBbNzEsIDcyLCA3MywgNzRdXQogICAgICAgICAgICAgICAgZm9yIHN0ZXBfaW5kZXgsIHRva2VucyBpbiBlbnVtZXJhdGUoY3VtdWxhdGl2ZV9zdGVwcyk6CiAgICAgICAgICAgICAgICAgICAgZmluYWwgPSBzdGVwX2luZGV4ID09IGxlbihjdW11bGF0aXZlX3N0ZXBzKSAtIDEKICAgICAgICAgICAgICAgICAgICBvdXRwdXRzID0gW10KICAgICAgICAgICAgICAgICAgICBmb3IgaSBpbiByYW5nZShjb3VudCk6CiAgICAgICAgICAgICAgICAgICAgICAgIGN1cnJlbnQgPSBbdG9rZW4gKyBpICogMTAwIGZvciB0b2tlbiBpbiB0b2tlbnNdCiAgICAgICAgICAgICAgICAgICAgICAgIHRvcCA9IE5vbmUKICAgICAgICAgICAgICAgICAgICAgICAgaWYgc2FtcGxpbmdfcGFyYW1zLmxvZ3Byb2JzIGlzIG5vdCBOb25lOgogICAgICAgICAgICAgICAgICAgICAgICAgICAgdG9wID0gWwogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIHt0b2tlbjogTG9ncHJvYihsb2dwcm9iPS0wLjEsIHJhbms9MSl9CiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgZm9yIHRva2VuIGluIGN1cnJlbnQKICAgICAgICAgICAgICAgICAgICAgICAgICAgIF0KICAgICAgICAgICAgICAgICAgICAgICAgb3V0cHV0cy5hcHBlbmQoCiAgICAgICAgICAgICAgICAgICAgICAgICAgICBfY29tcGxldGlvbigKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBpLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGN1cnJlbnQsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgKCJlcnJvciIgaWYgc2NlbmFyaW8gPT0gOTAxIGVsc2UgImxlbmd0aCIpCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgaWYgZmluYWwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBlbHNlIE5vbmUsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgdG9wLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgKQogICAgICAgICAgICAgICAgICAgICAgICApCiAgICAgICAgICAgICAgICAgICAgeWllbGQgX3JlcXVlc3Rfb3V0cHV0KAogICAgICAgICAgICAgICAgICAgICAgICByZXF1ZXN0X2lkLAogICAgICAgICAgICAgICAgICAgICAgICBwcm9tcHQsCiAgICAgICAgICAgICAgICAgICAgICAgIG91dHB1dHMsCiAgICAgICAgICAgICAgICAgICAgICAgIGZpbmlzaGVkPWZpbmFsLAogICAgICAgICAgICAgICAgICAgICAgICBudW1fY2FjaGVkX3Rva2Vucz0yIGlmIHNjZW5hcmlvID09IDkwNCBlbHNlIE5vbmUsCiAgICAgICAgICAgICAgICAgICAgKQogICAgICAgICAgICAgICAgICAgIGF3YWl0IGFzeW5jaW8uc2xlZXAoMC4wNCkKICAgICAgICAgICAgICAgIHJldHVybgoKICAgICAgICAgICAgaWYgc2NlbmFyaW8gPT0gOTAxOgogICAgICAgICAgICAgICAgeWllbGQgX3JlcXVlc3Rfb3V0cHV0KAogICAgICAgICAgICAgICAgICAgIHJlcXVlc3RfaWQsCiAgICAgICAgICAgICAgICAgICAgcHJvbXB0LAogICAgICAgICAgICAgICAgICAgIFtfY29tcGxldGlvbigwLCBbNzFdKV0sCiAgICAgICAgICAgICAgICAgICAgZmluaXNoZWQ9RmFsc2UsCiAgICAgICAgICAgICAgICApCiAgICAgICAgICAgICAgICBhd2FpdCBhc3luY2lvLnNsZWVwKDAuMDQpCiAgICAgICAgICAgICAgICB5aWVsZCBfcmVxdWVzdF9vdXRwdXQoCiAgICAgICAgICAgICAgICAgICAgcmVxdWVzdF9pZCwKICAgICAgICAgICAgICAgICAgICBwcm9tcHQsCiAgICAgICAgICAgICAgICAgICAgW19jb21wbGV0aW9uKDAsIFtdLCAiZXJyb3IiKV0sCiAgICAgICAgICAgICAgICAgICAgZmluaXNoZWQ9VHJ1ZSwKICAgICAgICAgICAgICAgICkKICAgICAgICAgICAgICAgIHJldHVybgoKICAgICAgICAgICAgc3RlcHMgPSBbWzcxXSwgWzcyLCA3M10sIFs3NF1dCiAgICAgICAgICAgIGlmIHNjZW5hcmlvID09IDkwMjoKICAgICAgICAgICAgICAgIHN0ZXBzLmluc2VydCgxLCBbXSkKICAgICAgICAgICAgZm9yIHN0ZXBfaW5kZXgsIHRva2VucyBpbiBlbnVtZXJhdGUoc3RlcHMpOgogICAgICAgICAgICAgICAgZmluYWwgPSBzdGVwX2luZGV4ID09IGxlbihzdGVwcykgLSAxCiAgICAgICAgICAgICAgICBvdXRwdXRzID0gW10KICAgICAgICAgICAgICAgIGZvciBpbmRleCBpbiByYW5nZShjb3VudCk6CiAgICAgICAgICAgICAgICAgICAgY3VycmVudCA9IFt0b2tlbiArIGluZGV4ICogMTAwIGZvciB0b2tlbiBpbiB0b2tlbnNdCiAgICAgICAgICAgICAgICAgICAgdG9wID0gTm9uZQogICAgICAgICAgICAgICAgICAgIGlmIHNhbXBsaW5nX3BhcmFtcy5sb2dwcm9icyBpcyBub3QgTm9uZToKICAgICAgICAgICAgICAgICAgICAgICAgdG9wID0gWwogICAgICAgICAgICAgICAgICAgICAgICAgICAge3Rva2VuOiBMb2dwcm9iKGxvZ3Byb2I9LTAuMSwgcmFuaz0xKX0KICAgICAgICAgICAgICAgICAgICAgICAgICAgIGZvciB0b2tlbiBpbiBjdXJyZW50CiAgICAgICAgICAgICAgICAgICAgICAgIF0KICAgICAgICAgICAgICAgICAgICBvdXRwdXRzLmFwcGVuZCgKICAgICAgICAgICAgICAgICAgICAgICAgX2NvbXBsZXRpb24oCiAgICAgICAgICAgICAgICAgICAgICAgICAgICBpbmRleCwKICAgICAgICAgICAgICAgICAgICAgICAgICAgIGN1cnJlbnQsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAibGVuZ3RoIiBpZiBmaW5hbCBlbHNlIE5vbmUsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICB0b3AsCiAgICAgICAgICAgICAgICAgICAgICAgICkKICAgICAgICAgICAgICAgICAgICApCiAgICAgICAgICAgICAgICB5aWVsZCBfcmVxdWVzdF9vdXRwdXQoCiAgICAgICAgICAgICAgICAgICAgcmVxdWVzdF9pZCwKICAgICAgICAgICAgICAgICAgICBwcm9tcHQsCiAgICAgICAgICAgICAgICAgICAgb3V0cHV0cywKICAgICAgICAgICAgICAgICAgICBmaW5pc2hlZD1maW5hbCwKICAgICAgICAgICAgICAgICAgICBudW1fY2FjaGVkX3Rva2Vucz0yIGlmIHNjZW5hcmlvID09IDkwNCBlbHNlIE5vbmUsCiAgICAgICAgICAgICAgICApCiAgICAgICAgICAgICAgICBhd2FpdCBhc3luY2lvLnNsZWVwKDAuMDQpCgogICAgICAgIHJldHVybiByZXN1bHRzKCkKCgpjbGFzcyBGYWtlTW9kZWxzOgogICAgbG9yYV9yZXF1ZXN0czogZGljdCA9IHt9CgogICAgZGVmIG1vZGVsX25hbWUoc2VsZiwgX2xvcmFfcmVxdWVzdCkgLT4gc3RyOgogICAgICAgIHJldHVybiAibG9jYWwtdG9rZW4tZW5naW5lIgoKCmNsYXNzIEZha2VSZW5kZXI6CiAgICBhc3luYyBkZWYgcHJlcHJvY2Vzc19jb21wbGV0aW9uKHNlbGYsIHJlcXVlc3QsICoqX2t3YXJncyk6CiAgICAgICAgcmV0dXJuICh7InByb21wdF90b2tlbl9pZHMiOiBsaXN0KHJlcXVlc3QudG9rZW5faWRzKX0sKQoKCmRlZiBidWlsZF9oYW5kbGVyKCk6CiAgICBmcm9tIHZsbG0uZW50cnlwb2ludHMuc2VydmUuZGlzYWdnLnNlcnZpbmcgaW1wb3J0IFNlcnZpbmdUb2tlbnMKCiAgICBoYW5kbGVyID0gU2VydmluZ1Rva2Vucy5fX25ld19fKFNlcnZpbmdUb2tlbnMpCiAgICBoYW5kbGVyLmVuZ2luZV9jbGllbnQgPSBGYWtlRW5naW5lKCkKICAgIGhhbmRsZXIubW9kZWxzID0gRmFrZU1vZGVscygpCiAgICBoYW5kbGVyLm9wZW5haV9zZXJ2aW5nX3JlbmRlciA9IEZha2VSZW5kZXIoKQogICAgaGFuZGxlci5mb3JjZV9ub19kZXRva2VuaXplID0gRmFsc2UKICAgIGhhbmRsZXIucmVxdWVzdF9sb2dnZXIgPSBOb25lCiAgICBoYW5kbGVyLmVuYWJsZV9wcm9tcHRfdG9rZW5zX2RldGFpbHMgPSBUcnVlCiAgICBoYW5kbGVyLmVuYWJsZV9sb2dfb3V0cHV0cyA9IEZhbHNlCgogICAgYXN5bmMgZGVmIGNoZWNrX21vZGVsKF9yZXF1ZXN0KToKICAgICAgICByZXR1cm4gTm9uZQoKICAgIGFzeW5jIGRlZiB0cmFjZV9oZWFkZXJzKF9oZWFkZXJzKToKICAgICAgICByZXR1cm4gTm9uZQoKICAgIGhhbmRsZXIuX2NoZWNrX21vZGVsID0gY2hlY2tfbW9kZWwKICAgIGhhbmRsZXIuX21heWJlX2dldF9hZGFwdGVycyA9IGxhbWJkYSAqX2FyZ3MsICoqX2t3YXJnczogTm9uZQogICAgaGFuZGxlci5fbG9nX2lucHV0cyA9IGxhbWJkYSAqX2FyZ3MsICoqX2t3YXJnczogTm9uZQogICAgaGFuZGxlci5fZ2V0X3RyYWNlX2hlYWRlcnMgPSB0cmFjZV9oZWFkZXJzCiAgICByZXR1cm4gaGFuZGxlcgoKCmRlZiBjcmVhdGVfYXBwKCkgLT4gRmFzdEFQSToKICAgIGZyb20gdmxsbS5lbnRyeXBvaW50cy5zZXJ2ZS5kaXNhZ2cuYXBpX3JvdXRlciBpbXBvcnQgcm91dGVyCgogICAgYXBwID0gRmFzdEFQSSgpCiAgICBhcHAuc3RhdGUuYXJncyA9IFNpbXBsZU5hbWVzcGFjZSh0b2tlbnNfb25seT1GYWxzZSkKICAgIGFwcC5zdGF0ZS5lbmFibGVfc2VydmVyX2xvYWRfdHJhY2tpbmcgPSBGYWxzZQogICAgYXBwLnN0YXRlLnNlcnZpbmdfdG9rZW5zID0gYnVpbGRfaGFuZGxlcigpCiAgICBhcHAuc3RhdGUuZW5naW5lX2NsaWVudCA9IGFwcC5zdGF0ZS5zZXJ2aW5nX3Rva2Vucy5lbmdpbmVfY2xpZW50CiAgICBhcHAuaW5jbHVkZV9yb3V0ZXIocm91dGVyKQogICAgcmV0dXJuIGFwcAoKCmFwcCA9IGNyZWF0ZV9hcHAoKQo= | base64 -d > /opt/repro/stream_app.py && install -d /opt/repro \
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGFyZ3BhcnNlCgppbXBvcnQgdXZpY29ybgoKZnJvbSBzdHJlYW1fYXBwIGltcG9ydCBhcHAKCgpkZWYgbWFpbigpIC0+IE5vbmU6CiAgICBwYXJzZXIgPSBhcmdwYXJzZS5Bcmd1bWVudFBhcnNlcigpCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCItLXBvcnQiLCB0eXBlPWludCwgcmVxdWlyZWQ9VHJ1ZSkKICAgIGFyZ3MgPSBwYXJzZXIucGFyc2VfYXJncygpCiAgICB1dmljb3JuLnJ1bihhcHAsIGhvc3Q9IjEyNy4wLjAuMSIsIHBvcnQ9YXJncy5wb3J0LCBsb2dfbGV2ZWw9Indhcm5pbmciKQoKCmlmIF9fbmFtZV9fID09ICJfX21haW5fXyI6CiAgICBtYWluKCkK | base64 -d > /opt/repro/stream_server.py
LABEL ai.infra.bench.environment-template=vllm-harbor-all-in-one \
      ai.infra.bench.base-commit=$VLLM_BASE_SHA \
      ai.infra.bench.dependency-cutoff=$VLLM_DEPENDENCY_CUTOFF \
      ai.infra.bench.cache-namespace=$VLLM_CACHE_NAMESPACE
ENTRYPOINT []
CMD ["sleep", "infinity"]
