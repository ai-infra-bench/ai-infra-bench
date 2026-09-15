# syntax=docker/dockerfile:1.7

ARG VLLM_SOURCE_COMMIT=2902c348265639de300c95cbcae1c26486f57ac7
ARG VLLM_SOURCE_TREE=03efefcb3069dc383b7ea26693972933ab633e99
ARG VLLM_ORACLE_COMMIT=7b5575fa7dcf76ac86ab8d18501b9cc04f74f6bb
ARG VLLM_REPOSITORY=https://github.com/vllm-project/vllm.git

# Git is copied from a digest-pinned helper image. This keeps the final build
# offline without depending on mutable Ubuntu package mirrors.
FROM alpine/git:2.49.1@sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26 AS git_runtime
ARG VLLM_SOURCE_COMMIT
ARG VLLM_SOURCE_TREE
ARG VLLM_ORACLE_COMMIT
ARG VLLM_REPOSITORY
RUN set -eux; \
    git init -q /vllm-history; \
    git -C /vllm-history config core.logAllRefUpdates false; \
    git -C /vllm-history config user.name "AI Infra Bench"; \
    git -C /vllm-history config user.email "noreply@ai-infra-bench.local"; \
    git -C /vllm-history remote add origin "${VLLM_REPOSITORY}"; \
    git -C /vllm-history fetch --no-tags origin "${VLLM_SOURCE_COMMIT}"; \
    git -C /vllm-history checkout -q -b benchmark-base "${VLLM_SOURCE_COMMIT}"; \
    test "$(git -C /vllm-history rev-parse HEAD)" = "${VLLM_SOURCE_COMMIT}"; \
    test "$(git -C /vllm-history rev-parse 'HEAD^{tree}')" = "${VLLM_SOURCE_TREE}"; \
    git -C /vllm-history remote remove origin; \
    rm -rf /vllm-history/.git/logs; \
    rm -f /vllm-history/.git/FETCH_HEAD /vllm-history/.git/ORIG_HEAD; \
    test ! -e /vllm-history/.git/shallow; \
    test -z "$(git -C /vllm-history remote)"; \
    test -z "$(git -C /vllm-history for-each-ref --format='%(refname)' refs/remotes refs/tags)"; \
    test "$(git -C /vllm-history rev-list --count HEAD)" -gt 1; \
    test -z "$(git -C /vllm-history rev-list --all --not "${VLLM_SOURCE_COMMIT}")"; \
    test -z "$(git -C /vllm-history fsck --full --no-reflogs --unreachable --no-progress 2>/dev/null)"; \
    ! git -C /vllm-history cat-file -e "${VLLM_ORACLE_COMMIT}^{commit}" 2>/dev/null

# PR #29999 was opened against main on the v0.12 development line. The
# official image supplies the matching torch 2.9/CUDA 12.9 runtime and compiled
# vLLM extensions; the exact PR base source is overlaid below and is the Python
# tree used at runtime.
FROM vllm/vllm-openai:v0.12.0@sha256:6766ce0c459e24b76f3e9ba14ffc0442131ef4248c904efdcbf0d89e38be01fe

ARG VLLM_SOURCE_COMMIT
ARG VLLM_SOURCE_TREE
ARG VLLM_ORACLE_COMMIT
ARG VLLM_SOURCE_SHA256=12a2dd5777029f342c5379c4b22ead2255912f832f98726692b5dbf5132256de
ARG VLLM_SOURCE_URL=https://codeload.github.com/vllm-project/vllm/tar.gz/2902c348265639de300c95cbcae1c26486f57ac7

LABEL ai-infra-bench.vllm-source-commit="${VLLM_SOURCE_COMMIT}"

USER root

# The release runtime intentionally omits Git. Copy the small Alpine Git
# runtime and its musl dependencies from the pinned helper stage.
COPY --from=git_runtime /usr/bin/git /usr/local/bin/git
COPY --from=git_runtime /usr/libexec/git-core /usr/libexec/git-core
COPY --from=git_runtime /usr/share/git-core /usr/share/git-core
COPY --from=git_runtime /lib/ld-musl-x86_64.so.1 /lib/ld-musl-x86_64.so.1
COPY --from=git_runtime /usr/lib/libpcre2-8.so.0.14.0 /usr/lib/libpcre2-8.so.0.14.0
COPY --from=git_runtime /usr/lib/libz.so.1.3.1 /usr/lib/libz.so.1.3.1
RUN ln -s libpcre2-8.so.0.14.0 /usr/lib/libpcre2-8.so.0 \
    && ln -s libz.so.1.3.1 /usr/lib/libz.so.1 \
    && git --version

RUN set -eu; \
    curl --fail --location --retry 8 --retry-all-errors \
      "${VLLM_SOURCE_URL}" -o /tmp/vllm-source.tar.gz; \
    printf '%s  %s\n' "${VLLM_SOURCE_SHA256}" /tmp/vllm-source.tar.gz | sha256sum -c -; \
    mkdir -p /workspace/repo; \
    tar -xzf /tmp/vllm-source.tar.gz --strip-components=1 -C /workspace/repo; \
    rm /tmp/vllm-source.tar.gz; \
    installed_pkg="$(python3 -c 'import importlib.metadata; print(importlib.metadata.distribution("vllm").locate_file("vllm"))')"; \
    cd "${installed_pkg}"; \
    find . -type f \( -name '*.so' -o -name '_version.py' \) \
      -exec cp --no-clobber --parents '{}' /workspace/repo/vllm/ \;; \
    site_dir="$(python3 -c 'import site; print(site.getsitepackages()[0])')"; \
    printf "import sys; sys.path.insert(0, '/workspace/repo')\n" > "${site_dir}/000_ai_infra_bench_vllm_source.pth"; \
    test ! -e /workspace/repo/.git

COPY --from=git_runtime /vllm-history/.git /workspace/repo/.git

RUN set -eu; \
    test "$(git -C /workspace/repo rev-parse HEAD)" = "${VLLM_SOURCE_COMMIT}"; \
    test "$(git -C /workspace/repo rev-parse 'HEAD^{tree}')" = "${VLLM_SOURCE_TREE}"; \
    test -z "$(git -C /workspace/repo remote)"; \
    test -z "$(git -C /workspace/repo for-each-ref --format='%(refname)' refs/remotes refs/tags)"; \
    test ! -e /workspace/repo/.git/logs; \
    test ! -e /workspace/repo/.git/FETCH_HEAD; \
    test ! -e /workspace/repo/.git/ORIG_HEAD; \
    test ! -e /workspace/repo/.git/shallow; \
    test "$(git -C /workspace/repo rev-list --count HEAD)" -gt 1; \
    test -z "$(git -C /workspace/repo rev-list --all --not "${VLLM_SOURCE_COMMIT}")"; \
    test -z "$(git -C /workspace/repo fsck --full --no-reflogs --unreachable --no-progress 2>/dev/null)"; \
    ! git -C /workspace/repo cat-file -e "${VLLM_ORACLE_COMMIT}^{commit}" 2>/dev/null; \
    test -z "$(git -C /workspace/repo status --porcelain=v1 --untracked-files=all)"; \
    useradd --create-home --uid 1000 --shell /bin/bash agent; \
    chown -R agent:agent /workspace/repo /home/agent

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_DATASETS_OFFLINE=1 \
    PIP_NO_INDEX=1 \
    VLLM_NO_USAGE_STATS=1 \
    HOME=/home/agent

WORKDIR /workspace/repo
USER agent

# Build-time checks prove that candidate edits under /workspace/repo are on
# the import path and that a native CUDA extension is present there.  Loading
# the extension itself is verified with a GPU at runtime.
RUN python3 -c "import importlib.util,pathlib,vllm; p=pathlib.Path(vllm.__file__).resolve(); s=importlib.util.find_spec('vllm._C'); print(vllm.__version__,p,s.origin if s else None); assert str(p).startswith('/workspace/repo/vllm/') and s is not None and str(s.origin).startswith('/workspace/repo/vllm/')" \
    && test "$(id -un)" = agent \
    && test -z "$(git remote)" \
    && test "$(git rev-parse HEAD)" = "${VLLM_SOURCE_COMMIT}" \
    && test -z "$(git status --porcelain)"

ENTRYPOINT []
CMD ["sleep", "infinity"]
