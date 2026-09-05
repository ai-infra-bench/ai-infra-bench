# Use the digest-pinned CPU image only as a build donor. The final image is a
# flattened, filtered rootfs and therefore does not inherit donor layers that
# contain the already-fixed vLLM Python source.
ARG BASE_IMAGE=vllm/vllm-openai-cpu:v0.17.1-x86_64@sha256:d19978a2d4bb2289c740a6c89d4cc15fbcf4d20d916f1e268168b8bbad3b776b
FROM ${BASE_IMAGE} AS donor

USER root

RUN set -eux; \
    VLLM_SITE="$(python3 -c 'import pathlib, vllm; print(pathlib.Path(vllm.__file__).parent)')"; \
    mkdir -p /opt/ai-infra-native/vllm; \
    find "${VLLM_SITE}" -type f \( -name '*.so' -o -name '_version.py' \) \
      -exec sh -c 'for src do rel="${src#"$0"/}"; dst="/opt/ai-infra-native/vllm/$rel"; mkdir -p "$(dirname "$dst")"; cp -a "$src" "$dst"; done' "${VLLM_SITE}" {} +; \
    mkdir -p /clean-root; \
    tar -C / --one-file-system \
      --exclude='./clean-root' \
      --exclude='./workspace' \
      --exclude='./proc' --exclude='./sys' --exclude='./dev' --exclude='./run' \
      --exclude='./tmp/*' --exclude='./root/.cache' \
      --exclude='./opt/venv/lib/python3.12/site-packages/vllm' \
      --exclude='./opt/venv/lib/python3.12/site-packages/vllm-*.dist-info' \
      -cf - . | tar -C /clean-root -xf -; \
    test ! -e /clean-root/opt/venv/lib/python3.12/site-packages/vllm; \
    test -z "$(find /clean-root -path '*/vllm/v1/request.py' -type f -print)"

FROM scratch
COPY --from=donor /clean-root/ /

ARG VLLM_BASE_SHA=e94ec597334d9a3e9b0d04bc17152e2747c83d51
ARG VLLM_SOURCE_TREE=bfdf97989c2997f550a44ebc42ad8aa5582d67a7
ARG VLLM_REPO=https://github.com/vllm-project/vllm.git

USER root

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace

# Fetch only history reachable from the exact pre-fix base, then remove all
# network metadata and reject hidden future objects.
RUN set -eux; \
    command -v git; \
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
    git -C /workspace/repo checkout -q -b main "${VLLM_BASE_SHA}"; \
    test "$(git -C /workspace/repo rev-parse HEAD)" = "${VLLM_BASE_SHA}"; \
    test "$(git -C /workspace/repo rev-parse 'HEAD^{tree}')" = "${VLLM_SOURCE_TREE}"; \
    git -C /workspace/repo remote remove origin; \
    rm -rf /workspace/repo/.git/logs; \
    rm -f /workspace/repo/.git/FETCH_HEAD /workspace/repo/.git/ORIG_HEAD; \
    test -z "$(git -C /workspace/repo remote)"; \
    test -z "$(git -C /workspace/repo for-each-ref --format='%(refname)' refs/remotes refs/tags)"; \
    test "$(git -C /workspace/repo rev-list --all --count)" -gt 1; \
    test -z "$(git -C /workspace/repo fsck --full --no-reflogs --unreachable --no-progress 2>/dev/null)"; \
    find /opt/ai-infra-native/vllm -type f \
      -exec sh -c 'for src do rel="${src#"$0"/}"; dst="/workspace/repo/vllm/$rel"; mkdir -p "$(dirname "$dst")"; cp -a "$src" "$dst"; done' /opt/ai-infra-native/vllm {} +; \
    rm -rf /opt/ai-infra-native; \
    test -z "$(find /opt/venv/lib/python3.12/site-packages -path '*/vllm/v1/request.py' -type f -print)"; \
    test -z "$(git -C /workspace/repo status --porcelain)"; \
    rm -f /root/.bash_history

RUN set -eux; \
    if ! id -u agent >/dev/null 2>&1; then \
        useradd --create-home --shell /bin/bash agent; \
    fi; \
    chown -R agent:agent /workspace; \
    rm -f /home/agent/.bash_history

ENV PYTHONPATH=/workspace/repo \
    LD_LIBRARY_PATH=/lib/x86_64-linux-gnu

USER agent
WORKDIR /workspace/repo
ENTRYPOINT []
CMD ["sleep", "infinity"]
