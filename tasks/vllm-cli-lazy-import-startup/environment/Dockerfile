# syntax=docker/dockerfile:1
# Template inputs below are replaced from task.toml by generate.py. Generated
# task Dockerfiles are self-contained and differ only in their frozen inputs.

ARG VLLM_BASE_SHA=4c47710bf707e93bdf83391948f844e461b7ba4f
ARG VLLM_DEPENDENCY_CUTOFF=2026-04-17T00:54:32Z
ARG VLLM_CACHE_NAMESPACE=4c47710bf707e93bdf83391948f844e461b7ba4f-2004971382e583fa-6e080ff0c9cb931b
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
# Exact task dependency lock (sha256:2004971382e583fa38d53c93c6201521458f8ab1f310c694a15ae8cc719e3ac1) is embedded so this
# Dockerfile remains independently buildable with an empty context.
RUN --mount=type=cache,id=vllm-uv-downloads-v3,target=/root/.cache/uv,sharing=locked <<'VLLM_INSTALL_EOF'
set -eu
cat > /tmp/vllm-requirements.lock <<'VLLM_REQUIREMENTS_EOF'
# Generated with uv 0.11.28 from the pinned base requirements and task
# extras for CPython 3.12 on x86_64 manylinux_2_28. Packages newer than
# 2026-04-17T00:54:32Z were excluded during resolution.
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
anthropic==0.96.0
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
av==17.0.0
    # via -r requirements/common.txt
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
    # via
    #   cryptography
    #   soundfile
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
compressed-tensors==0.15.0.1
    # via -r requirements/common.txt
contourpy==1.3.3
    # via matplotlib
cryptography==46.0.7
    # via pyjwt
cycler==0.12.1
    # via matplotlib
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
fastapi==0.136.0
    # via
    #   -r requirements/common.txt
    #   model-hosting-container-standards
fastapi-cli==0.0.24
    # via fastapi
fastapi-cloud-cli==0.17.0
    # via fastapi-cli
fastar==0.11.0
    # via
    #   fastapi
    #   fastapi-cloud-cli
filelock==3.28.0
    # via
    #   -r requirements/common.txt
    #   huggingface-hub
    #   torch
fonttools==4.62.1
    # via matplotlib
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
    #   huggingface-hub
    #   mcp
    #   model-hosting-container-standards
    #   openai
httpx-sse==0.4.3
    # via mcp
huggingface-hub==1.11.0
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
kiwisolver==1.5.0
    # via matplotlib
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
matplotlib==3.10.8
    # via
    #   -r extras.in
    #   seaborn
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
    #   contourpy
    #   gguf
    #   matplotlib
    #   mistral-common
    #   numba
    #   opencv-python-headless
    #   pandas
    #   seaborn
    #   soundfile
    #   torchvision
    #   transformers
    #   xgrammar
openai==2.32.0
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
    #   matplotlib
    #   pytest
    #   setuptools-scm
    #   transformers
    #   vcs-versioning
    #   wheel
pandas==3.0.2
    # via
    #   -r extras.in
    #   seaborn
partial-json-parser==0.2.1.1.post7
    # via -r requirements/common.txt
pillow==12.2.0
    # via
    #   -r requirements/common.txt
    #   matplotlib
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
pydantic==2.13.1
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
pydantic-core==2.46.1
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
pyparsing==3.3.2
    # via matplotlib
pytest==9.0.3
    # via
    #   -r extras.in
    #   pytest-timeout
pytest-timeout==2.4.0
    # via -r extras.in
python-dateutil==2.9.0.post0
    # via
    #   matplotlib
    #   pandas
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
    #   mistral-common
    #   opentelemetry-exporter-otlp-proto-http
    #   tiktoken
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
seaborn==0.13.2
    # via -r extras.in
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
    # via
    #   -r requirements/common.txt
    #   python-dateutil
sniffio==1.3.1
    # via
    #   anthropic
    #   openai
soundfile==0.13.1
    # via -r requirements/common.txt
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
transformers==5.5.4
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
    #   huggingface-hub
    #   transformers
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
 && printf '%s' ZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IGpzb24KaW1wb3J0IHN0YXRpc3RpY3MKaW1wb3J0IHN1YnByb2Nlc3MKaW1wb3J0IHN5cwoKClNBTVBMRVMgPSA1Ck1BWF9SQVRJTyA9IDEuNQpNQVhfT1ZFUkhFQURfU0VDT05EUyA9IDAuOApJTVBPUlRfU0NSSVBUID0gciIiIgppbXBvcnQgaW1wb3J0bGliCmltcG9ydCBqc29uCmltcG9ydCBvcwppbXBvcnQgc3lzCmltcG9ydCB0aW1lCgp0YXJnZXQgPSBzeXMuYXJndlsxXQpzdGFydGVkID0gdGltZS5wZXJmX2NvdW50ZXIoKQppbXBvcnRsaWIuaW1wb3J0X21vZHVsZSh0YXJnZXQpCmVsYXBzZWQgPSB0aW1lLnBlcmZfY291bnRlcigpIC0gc3RhcnRlZApwcmludChqc29uLmR1bXBzKHsKICAgICJ0YXJnZXQiOiB0YXJnZXQsCiAgICAiZWxhcHNlZCI6IGVsYXBzZWQsCiAgICAiYmVuY2htYXJrX21vZHVsZXMiOiBzb3J0ZWQoCiAgICAgICAgbmFtZSBmb3IgbmFtZSBpbiBzeXMubW9kdWxlcwogICAgICAgIGlmIG5hbWUuc3RhcnRzd2l0aCgidmxsbS5lbnRyeXBvaW50cy5jbGkuYmVuY2htYXJrLiIpCiAgICApLAogICAgInBsb3R0aW5nX21vZHVsZXMiOiBzb3J0ZWQoCiAgICAgICAgbmFtZSBmb3IgbmFtZSBpbiBzeXMubW9kdWxlcwogICAgICAgIGlmIG5hbWUuc3BsaXQoIi4iLCAxKVswXSBpbiB7Im1hdHBsb3RsaWIiLCAicGFuZGFzIiwgInNlYWJvcm4ifQogICAgKSwKICAgICJpbmR1Y3Rvcl9jb25maWdfbG9hZGVkIjogInRvcmNoLl9pbmR1Y3Rvci5jb25maWciIGluIHN5cy5tb2R1bGVzLAogICAgImNvbXBpbGVfdGhyZWFkcyI6IG9zLmVudmlyb24uZ2V0KCJUT1JDSElORFVDVE9SX0NPTVBJTEVfVEhSRUFEUyIpLAp9KSkKIiIiCgoKZGVmIG1lYXN1cmUodGFyZ2V0OiBzdHIpIC0+IGRpY3Rbc3RyLCBvYmplY3RdOgogICAgcmVzdWx0ID0gc3VicHJvY2Vzcy5ydW4oCiAgICAgICAgW3N5cy5leGVjdXRhYmxlLCAiLWMiLCBJTVBPUlRfU0NSSVBULCB0YXJnZXRdLAogICAgICAgIGN3ZD0iL3dvcmtzcGFjZS92bGxtIiwKICAgICAgICB0ZXh0PVRydWUsCiAgICAgICAgc3Rkb3V0PXN1YnByb2Nlc3MuUElQRSwKICAgICAgICBzdGRlcnI9c3VicHJvY2Vzcy5QSVBFLAogICAgICAgIHRpbWVvdXQ9MzAsCiAgICAgICAgY2hlY2s9VHJ1ZSwKICAgICkKICAgIHJldHVybiBqc29uLmxvYWRzKHJlc3VsdC5zdGRvdXQuc3BsaXRsaW5lcygpWy0xXSkKCgpkZWYgbWFpbigpIC0+IGludDoKICAgIHBsYWluX3JlcG9ydHM6IGxpc3RbZGljdFtzdHIsIG9iamVjdF1dID0gW10KICAgIGNsaV9yZXBvcnRzOiBsaXN0W2RpY3Rbc3RyLCBvYmplY3RdXSA9IFtdCiAgICBmb3Igc2FtcGxlIGluIHJhbmdlKFNBTVBMRVMpOgogICAgICAgICMgQWx0ZXJuYXRlIG9yZGVyIHNvIHRyYW5zaWVudCBob3N0IGxvYWQgaXMgbm90IGFsd2F5cyBjaGFyZ2VkIHRvIG9uZSBzaWRlLgogICAgICAgIHRhcmdldHMgPSAoCiAgICAgICAgICAgICgidmxsbSIsIHBsYWluX3JlcG9ydHMpLAogICAgICAgICAgICAoInZsbG0uZW50cnlwb2ludHMuY2xpLm1haW4iLCBjbGlfcmVwb3J0cyksCiAgICAgICAgKQogICAgICAgIGlmIHNhbXBsZSAlIDI6CiAgICAgICAgICAgIHRhcmdldHMgPSB0dXBsZShyZXZlcnNlZCh0YXJnZXRzKSkKICAgICAgICBmb3IgdGFyZ2V0LCByZXBvcnRzIGluIHRhcmdldHM6CiAgICAgICAgICAgIHJlcG9ydCA9IG1lYXN1cmUodGFyZ2V0KQogICAgICAgICAgICByZXBvcnRzLmFwcGVuZChyZXBvcnQpCiAgICAgICAgICAgIHByaW50KGpzb24uZHVtcHMocmVwb3J0LCBzZXBhcmF0b3JzPSgiLCIsICI6IikpKQoKICAgIHBsYWluX21lZGlhbiA9IHN0YXRpc3RpY3MubWVkaWFuKAogICAgICAgIGZsb2F0KHJlcG9ydFsiZWxhcHNlZCJdKSBmb3IgcmVwb3J0IGluIHBsYWluX3JlcG9ydHMKICAgICkKICAgIGNsaV9tZWRpYW4gPSBzdGF0aXN0aWNzLm1lZGlhbigKICAgICAgICBmbG9hdChyZXBvcnRbImVsYXBzZWQiXSkgZm9yIHJlcG9ydCBpbiBjbGlfcmVwb3J0cwogICAgKQogICAgcmF0aW8gPSBjbGlfbWVkaWFuIC8gcGxhaW5fbWVkaWFuCiAgICBvdmVyaGVhZCA9IGNsaV9tZWRpYW4gLSBwbGFpbl9tZWRpYW4KICAgIGltcG9ydF9jb250cmFjdCA9IGFsbCgKICAgICAgICBub3QgcmVwb3J0WyJiZW5jaG1hcmtfbW9kdWxlcyJdCiAgICAgICAgYW5kIG5vdCByZXBvcnRbInBsb3R0aW5nX21vZHVsZXMiXQogICAgICAgIGFuZCByZXBvcnRbImNvbXBpbGVfdGhyZWFkcyJdID09ICIxIgogICAgICAgIGZvciByZXBvcnQgaW4gY2xpX3JlcG9ydHMKICAgICkKICAgIGNvcnJlY3QgPSAoCiAgICAgICAgaW1wb3J0X2NvbnRyYWN0CiAgICAgICAgYW5kIHJhdGlvIDw9IE1BWF9SQVRJTwogICAgICAgIGFuZCBvdmVyaGVhZCA8PSBNQVhfT1ZFUkhFQURfU0VDT05EUwogICAgKQogICAgc3VtbWFyeSA9IHsKICAgICAgICAic2FtcGxlc19wZXJfdGFyZ2V0IjogU0FNUExFUywKICAgICAgICAicGxhaW5faW1wb3J0X21lZGlhbl9zZWNvbmRzIjogcGxhaW5fbWVkaWFuLAogICAgICAgICJjbGlfaW1wb3J0X21lZGlhbl9zZWNvbmRzIjogY2xpX21lZGlhbiwKICAgICAgICAiY2xpX3RvX3BsYWluX3JhdGlvIjogcmF0aW8sCiAgICAgICAgImNsaV9vdmVyaGVhZF9zZWNvbmRzIjogb3ZlcmhlYWQsCiAgICAgICAgIm1heF9yYXRpbyI6IE1BWF9SQVRJTywKICAgICAgICAibWF4X292ZXJoZWFkX3NlY29uZHMiOiBNQVhfT1ZFUkhFQURfU0VDT05EUywKICAgICAgICAiaW1wb3J0X2NvbnRyYWN0IjogaW1wb3J0X2NvbnRyYWN0LAogICAgICAgICJjb2xkX2NsaV9pbXBvcnRfY29udHJhY3QiOiBjb3JyZWN0LAogICAgfQogICAgcHJpbnQoanNvbi5kdW1wcyhzdW1tYXJ5LCBpbmRlbnQ9Miwgc29ydF9rZXlzPVRydWUpKQogICAgcmV0dXJuIDAgaWYgY29ycmVjdCBlbHNlIDMKCgppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOgogICAgcmFpc2UgU3lzdGVtRXhpdChtYWluKCkpCg== | base64 -d > /opt/repro/cli_import_report.py
LABEL ai.infra.bench.environment-template=vllm-harbor-all-in-one \
      ai.infra.bench.base-commit=$VLLM_BASE_SHA \
      ai.infra.bench.dependency-cutoff=$VLLM_DEPENDENCY_CUTOFF \
      ai.infra.bench.cache-namespace=$VLLM_CACHE_NAMESPACE
ENTRYPOINT []
CMD ["sleep", "infinity"]
