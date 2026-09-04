# syntax=docker/dockerfile:1.7.0@sha256:dbbd5e059e8a07ff7ea6233b213b36aa516b4c53c645f1817a4dd18b83cbea56
# Self-contained, cutoff-pinned environment for this task.

ARG VLLM_BASE_SHA=4731884796d43bd8493769dbfb0e199a2a542092
ARG VLLM_DEPENDENCY_CUTOFF=2026-03-24T16:53:07Z
ARG VLLM_CACHE_NAMESPACE=4731884796d43bd8493769dbfb0e199a2a542092-dafe282dea8de514
ARG VLLM_REPO=https://github.com/vllm-project/vllm.git
ARG DEBIAN_SNAPSHOT=20260324T160000Z

######################### PINNED SOURCE #########################
FROM python:3.12.12-slim-trixie@sha256:42f1689d6d6b906c7e829f9d9ec38491550344ac9adc01e464ff9a08df1ffb48 AS source
ARG VLLM_BASE_SHA
ARG VLLM_REPO
ARG DEBIAN_SNAPSHOT
RUN test -n "$VLLM_BASE_SHA" \
 && rm -f /etc/apt/sources.list.d/debian.sources \
 && printf '%s\n' \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} trixie main" \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} trixie-updates main" \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT} trixie-security main" \
      > /etc/apt/sources.list \
 && apt-get -o Acquire::Check-Valid-Until=false update \
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
FROM python:3.12.12-slim-trixie@sha256:42f1689d6d6b906c7e829f9d9ec38491550344ac9adc01e464ff9a08df1ffb48
ARG DEBIAN_SNAPSHOT
ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=500 \
    CC=/usr/bin/gcc \
    CXX=/usr/bin/g++ \
    CCACHE_DIR=/root/.cache/ccache \
    CMAKE_CXX_COMPILER_LAUNCHER=ccache \
    MAX_JOBS=8

RUN rm -f /etc/apt/sources.list.d/debian.sources \
 && printf '%s\n' \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} trixie main" \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} trixie-updates main" \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT} trixie-security main" \
      > /etc/apt/sources.list \
 && apt-get -o Acquire::Check-Valid-Until=false update \
 && apt-get install -y --no-install-recommends \
      bash build-essential ca-certificates ccache curl ffmpeg \
      git jq libgl1 libnuma-dev libsm6 libssl-dev libtcmalloc-minimal4 \
      libxext6 lsof make pkg-config sudo unzip wget xz-utils \
 && rm -rf /var/lib/apt/lists/*

RUN curl --http1.1 -L --retry 10 --retry-all-errors --connect-timeout 30 --max-time 600 \
      --proto '=https' --tlsv1.2 -sSf \
      "https://files.pythonhosted.org/packages/36/fa/086616d98b0b8a2cc5e7b49c389118a8196027a79a5a501f5e738f718f59/uv-0.11.0-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl" \
      -o /tmp/uv-0.11.0-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl \
 && printf '%s  %s\n' \
      30a08ee4291580784a5e276a1cbec8830994dba2ed5c94d878cce8b2121367cf \
      /tmp/uv-0.11.0-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl | sha256sum -c - \
 && pip install --no-cache-dir --no-deps \
      /tmp/uv-0.11.0-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl \
 && rm -f /tmp/uv-0.11.0-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl \
 && uv --version | grep -Eq '^uv 0\.11\.0([[:space:]]|$)'

ARG VLLM_DEPENDENCY_CUTOFF
# The exact cutoff-bounded dependency lock is the only local build input.
COPY lock/requirements.txt /tmp/vllm-requirements.lock
RUN --mount=type=cache,id=vllm-uv-downloads-v3,target=/root/.cache/uv,sharing=locked \
    uv pip install --system --require-hashes --index-strategy first-index \
      --torch-backend cpu -r /tmp/vllm-requirements.lock \
 && rm -f /tmp/vllm-requirements.lock

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

RUN useradd --create-home --shell /bin/bash agent \
 && chown -R agent:agent /workspace/vllm

LABEL ai.infra.bench.environment-template=vllm-cutoff-pinned \
      ai.infra.bench.base-commit=$VLLM_BASE_SHA \
      ai.infra.bench.dependency-cutoff=$VLLM_DEPENDENCY_CUTOFF \
      ai.infra.bench.cache-namespace=$VLLM_CACHE_NAMESPACE
USER agent
ENV HOME=/home/agent
ENTRYPOINT []
CMD ["sleep", "infinity"]
