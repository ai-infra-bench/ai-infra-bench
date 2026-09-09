ARG BASE_IMAGE=vllm/vllm-openai:v0.12.0@sha256:6766ce0c459e24b76f3e9ba14ffc0442131ef4248c904efdcbf0d89e38be01fe
ARG NATIVE_IMAGE=vllm/vllm-openai:v0.13.0@sha256:d623253f2ba246378421c9642e20885e65257f38418ff26d48c81aea1702521b
ARG VLLM_BASE_SHA=e2ed238885be6af358be1851cd43105b7d036c49
ARG VLLM_BASE_TREE=75491c7db4e75808a6bfe937322d3839a619ecdf
ARG VLLM_ORACLE_SHA=3778673ea81bf5241f40e9c5e90f989bde377acf
ARG VLLM_REPOSITORY=https://github.com/vllm-project/vllm.git

FROM alpine/git:2.49.1@sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26 AS git-history
ARG VLLM_BASE_SHA
ARG VLLM_BASE_TREE
ARG VLLM_ORACLE_SHA
ARG VLLM_REPOSITORY
RUN set -eux; \
    git init -q /vllm-history; \
    git -C /vllm-history config core.logAllRefUpdates false; \
    git -C /vllm-history config user.name "AI Infra Bench"; \
    git -C /vllm-history config user.email "noreply@ai-infra-bench.local"; \
    git -C /vllm-history remote add origin "${VLLM_REPOSITORY}"; \
    git -C /vllm-history fetch --no-tags origin "${VLLM_BASE_SHA}"; \
    git -C /vllm-history checkout -q -b benchmark-base "${VLLM_BASE_SHA}"; \
    test "$(git -C /vllm-history rev-parse HEAD)" = "${VLLM_BASE_SHA}"; \
    test "$(git -C /vllm-history rev-parse 'HEAD^{tree}')" = "${VLLM_BASE_TREE}"; \
    git -C /vllm-history remote remove origin; \
    rm -rf /vllm-history/.git/logs; \
    rm -f /vllm-history/.git/FETCH_HEAD /vllm-history/.git/ORIG_HEAD; \
    test ! -e /vllm-history/.git/shallow; \
    test -z "$(git -C /vllm-history remote)"; \
    test -z "$(git -C /vllm-history for-each-ref --format='%(refname)' refs/remotes refs/tags)"; \
    test "$(git -C /vllm-history rev-list --count HEAD)" -gt 1; \
    test -z "$(git -C /vllm-history rev-list --all --not "${VLLM_BASE_SHA}")"; \
    test -z "$(git -C /vllm-history fsck --full --no-reflogs --unreachable --no-progress 2>/dev/null)"; \
    ! git -C /vllm-history cat-file -e "${VLLM_ORACLE_SHA}^{commit}" 2>/dev/null

FROM ${NATIVE_IMAGE} AS native-donor
USER root
COPY lock/native-v0.13.0.sha256 /tmp/native-manifest.sha256
RUN set -eux; \
    VLLM_SITE="$(python3 -c 'import pathlib, vllm; print(pathlib.Path(vllm.__file__).parent)')"; \
    mkdir -p /opt/native; \
    cd "${VLLM_SITE}"; \
    test "$(wc -l < /tmp/native-manifest.sha256)" = 7; \
    while read -r expected rel; do \
        case "${rel}" in \
            *.so) ;; \
            *) echo "Non-.so donor path: ${rel}" >&2; exit 1 ;; \
        esac; \
        case "${rel}" in \
            /*|../*|*/../*) echo "Unsafe donor path: ${rel}" >&2; exit 1 ;; \
        esac; \
        test -f "${rel}"; \
        test ! -L "${rel}"; \
        test "$(dd if="${rel}" bs=1 count=4 2>/dev/null | od -An -tx1 | tr -d ' \n')" = 7f454c46; \
        install -D -m 0755 "${rel}" "/opt/native/${rel}"; \
    done < /tmp/native-manifest.sha256; \
    cd /opt/native; \
    sha256sum -c /tmp/native-manifest.sha256; \
    test "$(find . -type f | wc -l)" = 7; \
    test -z "$(find . ! -type d ! -type f -print -quit)"

FROM ${BASE_IMAGE}

ARG VLLM_BASE_SHA
ARG VLLM_BASE_TREE
ARG VLLM_ORACLE_SHA
ARG VLLM_SOURCE_SHA256=b3abf42611917bf610cfe2c543961ba38a7b9e6e1a3a6774287d5e3f4aa932c2

USER root

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace

COPY --from=native-donor /opt/native /opt/vllm-native

# Fetch the exact survey base as a digest-checked archive. Exact upstream Base
# history is copied from the isolated Git stage below.
# Docker's predefined proxy args are intentionally not redeclared.
RUN set -eux; \
    apt-get \
        -o Acquire::http::Proxy=false \
        -o Acquire::https::Proxy=false \
        update; \
    DEBIAN_FRONTEND=noninteractive apt-get \
        -o Acquire::http::Proxy=false \
        -o Acquire::https::Proxy=false \
        install -y --no-install-recommends \
        ca-certificates \
        git; \
    rm -rf /var/lib/apt/lists/*; \
    curl -fL \
        --retry 8 \
        --retry-all-errors \
        --retry-delay 3 \
        --connect-timeout 30 \
        --max-time 600 \
        "https://codeload.github.com/vllm-project/vllm/tar.gz/${VLLM_BASE_SHA}" \
        -o /tmp/vllm-source.tar.gz; \
    echo "${VLLM_SOURCE_SHA256}  /tmp/vllm-source.tar.gz" | sha256sum -c -; \
    mkdir -p /workspace/repo; \
    tar -xzf /tmp/vllm-source.tar.gz --strip-components=1 -C /workspace/repo; \
    rm -f /tmp/vllm-source.tar.gz

COPY --from=git-history /vllm-history/.git /workspace/repo/.git

RUN set -eux; \
    test "$(git -C /workspace/repo rev-parse HEAD)" = "${VLLM_BASE_SHA}"; \
    test "$(git -C /workspace/repo rev-parse 'HEAD^{tree}')" = "${VLLM_BASE_TREE}"; \
    test -z "$(git -C /workspace/repo remote)"; \
    test -z "$(git -C /workspace/repo for-each-ref --format='%(refname)' refs/remotes refs/tags)"; \
    test ! -e /workspace/repo/.git/logs; \
    test ! -e /workspace/repo/.git/FETCH_HEAD; \
    test ! -e /workspace/repo/.git/ORIG_HEAD; \
    test ! -e /workspace/repo/.git/shallow; \
    test "$(git -C /workspace/repo rev-list --count HEAD)" -gt 1; \
    test -z "$(git -C /workspace/repo rev-list --all --not "${VLLM_BASE_SHA}")"; \
    test -z "$(git -C /workspace/repo fsck --full --no-reflogs --unreachable --no-progress 2>/dev/null)"; \
    ! git -C /workspace/repo cat-file -e "${VLLM_ORACLE_SHA}^{commit}" 2>/dev/null; \
    test -z "$(git -C /workspace/repo status --porcelain=v1 --untracked-files=all)"; \
    VLLM_SITE="$(python3 -c 'import pathlib, vllm; print(pathlib.Path(vllm.__file__).parent)')"; \
    test "$(find /opt/vllm-native -type f | wc -l)" = 7; \
    test -z "$(find /opt/vllm-native ! -type d ! -type f -print -quit)"; \
    cp -a "${VLLM_SITE}/_version.py" /workspace/repo/vllm/_version.py; \
    find /opt/vllm-native -type f -name '*.so' \
        -exec sh -c 'for src do rel="${src#"$0"/}"; dst="/workspace/repo/vllm/$rel"; mkdir -p "$(dirname "$dst")"; cp -a "$src" "$dst"; done' /opt/vllm-native {} +; \
    rm -rf /opt/vllm-native; \
    test ! -e /opt/vllm-native; \
    test -z "$(git -C /workspace/repo status --porcelain=v1 --untracked-files=all)"; \
    rm -f /root/.bash_history

RUN set -eux; \
    if ! id -u agent >/dev/null 2>&1; then \
        useradd --create-home --shell /bin/bash agent; \
    fi; \
    chown -R agent:agent /workspace; \
    rm -f /home/agent/.bash_history

ENV PYTHONPATH=/workspace/repo \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TRITON_CACHE_DIR=/home/agent/.cache/triton

USER agent
WORKDIR /workspace/repo
ENTRYPOINT []
CMD ["sleep", "infinity"]
