ARG BASE_IMAGE=vllm/vllm-openai:v0.20.1@sha256:9eff9734a30b6713a8566217d36f8277630fd2d31cec7f0a0292835901a23aa4
FROM ${BASE_IMAGE}

ARG VLLM_BASE_SHA=f80aa53c9dc2273a19a6855092069db7e1306fff
ARG VLLM_BASE_TREE=2af517bd7880077a9fed9a39dc0e8b1e244a48b1
ARG VLLM_REPO=https://github.com/vllm-project/vllm.git

USER root

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace

COPY lock/native-paths.txt /tmp/native-paths.txt

# Acquire the exact survey Base and retain its reachable history.
# Docker's predefined proxy args are not redeclared, keeping values out of image
# configuration and history.
RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        git; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /workspace/repo; \
    git -C /workspace/repo init -q; \
    git -C /workspace/repo config core.logAllRefUpdates false; \
    git -C /workspace/repo config http.version HTTP/1.1; \
    git -C /workspace/repo remote add origin "${VLLM_REPO}"; \
    fetch_step() { \
      for attempt in 1 2 3; do \
        git -C /workspace/repo fetch "$@" && return 0; \
      done; \
      return 1; \
    }; \
    fetch_step --depth=2000 --no-tags origin "${VLLM_BASE_SHA}"; \
    while test -e /workspace/repo/.git/shallow; do \
      fetch_step --deepen=2000 --no-tags origin "${VLLM_BASE_SHA}"; \
    done; \
    git -C /workspace/repo checkout -q -b main "${VLLM_BASE_SHA}"; \
    test "$(git -C /workspace/repo rev-parse HEAD)" = "${VLLM_BASE_SHA}"; \
    test "$(git -C /workspace/repo rev-parse 'HEAD^{tree}')" = "${VLLM_BASE_TREE}"; \
    git -C /workspace/repo remote remove origin; \
    rm -rf /workspace/repo/.git/logs; \
    rm -f /workspace/repo/.git/FETCH_HEAD /workspace/repo/.git/ORIG_HEAD; \
    test -z "$(git -C /workspace/repo remote)"; \
    test -z "$(git -C /workspace/repo for-each-ref --format='%(refname)' refs/remotes refs/tags)"; \
    test "$(git -C /workspace/repo rev-list --all --count)" -gt 1; \
    test ! -e /workspace/repo/.git/shallow; \
    test -z "$(git -C /workspace/repo fsck --full --no-reflogs --unreachable --no-progress 2>/dev/null)"; \
    VLLM_SITE="$(python3 -c 'import pathlib, vllm; print(pathlib.Path(vllm.__file__).parent)')"; \
    while IFS= read -r rel; do \
        test -n "${rel}"; \
        test -f "${VLLM_SITE}/${rel}"; \
        test ! -L "${VLLM_SITE}/${rel}"; \
        mode=0644; \
        case "${rel}" in \
            *.so) readelf -h "${VLLM_SITE}/${rel}" >/dev/null; mode=0755 ;; \
        esac; \
        install -D -m "${mode}" "${VLLM_SITE}/${rel}" "/workspace/repo/vllm/${rel}"; \
    done < /tmp/native-paths.txt; \
    test "$(wc -l < /tmp/native-paths.txt)" = 10; \
    test "$(find /workspace/repo/vllm -type f -name '*.so' | wc -l)" = 9; \
    test -z "$(git -C /workspace/repo status --porcelain)"; \
    rm -f /tmp/native-paths.txt /root/.bash_history

RUN set -eux; \
    if ! id -u agent >/dev/null 2>&1; then \
        useradd --create-home --shell /bin/bash agent; \
    fi; \
    chown -R agent:agent /workspace; \
    rm -f /home/agent/.bash_history

ENV PYTHONPATH=/workspace/repo \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

USER agent
WORKDIR /workspace/repo
ENTRYPOINT []
CMD ["/bin/bash"]
