# syntax=docker/dockerfile:1.7

ARG VLLM_SOURCE_COMMIT=b07555d26f4c7ad9a2d1ec45428a9d4287db612c
ARG VLLM_SOURCE_TREE=5e9db07c8aa717797c947d3bf19d055dede6f384
ARG VLLM_ORACLE_COMMIT=0b0aa874e85431a0f08a0d1fad95ae673e034392
ARG VLLM_REPOSITORY=https://github.com/vllm-project/vllm.git

FROM alpine/git:2.49.1@sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26 AS git_runtime
ARG VLLM_SOURCE_COMMIT
ARG VLLM_SOURCE_TREE
ARG VLLM_ORACLE_COMMIT
ARG VLLM_REPOSITORY
RUN tar -czf /git-runtime.tar \
    /usr/bin/git \
    /usr/libexec/git-core \
    /usr/share/git-core \
    /lib/ld-musl-x86_64.so.1 \
    /usr/lib/libpcre2-8.so.0.14.0 \
    /usr/lib/libz.so.1.3.1
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

# The PR base is 283 commits after v0.11.1 and includes native-source changes.
# An exact offline rebuild was attempted but CMake requires five uncached
# external source projects. The constrained fallback overlays the *entire*
# exact-base source tree and reuses only wheel-only/native files from the
# closest official runtime. The native-origin label makes this ABI risk
# machine-visible; this is not the rejected single-Python-file construction.
FROM vllm/vllm-openai:v0.11.1@sha256:d5b12dfb74d605615f8b29ebafaa52294c118bcac7bc9e941785c4108fdb913a

ARG VLLM_SOURCE_COMMIT
ARG VLLM_SOURCE_TREE
ARG VLLM_ORACLE_COMMIT
ARG VLLM_SOURCE_SHA256=5f5d48bb58d898d89d65bb4310b916f3472f84db0cb17f994203084e3aafce1f
ARG VLLM_SOURCE_URL=https://codeload.github.com/vllm-project/vllm/tar.gz/b07555d26f4c7ad9a2d1ec45428a9d4287db612c

LABEL ai-infra-bench.vllm-source-commit="${VLLM_SOURCE_COMMIT}" \
      ai-infra-bench.vllm-native-origin="v0.11.1:439368496db48d8f992ba8c606a0c0b1eebbfa69"

USER root

COPY --from=git_runtime /git-runtime.tar /tmp/git-runtime.tar
RUN tar -xzf /tmp/git-runtime.tar -C / \
    && rm /tmp/git-runtime.tar \
    && ln -s libpcre2-8.so.0.14.0 /usr/lib/libpcre2-8.so.0 \
    && ln -s libz.so.1.3.1 /usr/lib/libz.so.1 \
    && git --version

RUN set -eu; \
    curl --fail --location --retry 8 --retry-all-errors \
      "${VLLM_SOURCE_URL}" -o /tmp/vllm-source.tar.gz; \
    printf '%s  %s\n' "${VLLM_SOURCE_SHA256}" /tmp/vllm-source.tar.gz | sha256sum -c -; \
    mkdir -p /workspace/repo; \
    tar -xzf /tmp/vllm-source.tar.gz --strip-components=1 -C /workspace/repo; \
    rm /tmp/vllm-source.tar.gz; \
    test ! -e /workspace/repo/.git; \
    installed_pkg="$(python3 -c 'import importlib.metadata; print(importlib.metadata.distribution("vllm").locate_file("vllm"))')"; \
    cd "${installed_pkg}"; \
    find . -type f \( -name '*.so' -o -name '_version.py' \) \
      -exec cp --no-clobber --parents '{}' /workspace/repo/vllm/ \;; \
    site_dir="$(python3 -c 'import site; print(site.getsitepackages()[0])')"; \
    printf "import sys; sys.path.insert(0, '/workspace/repo')\n" > "${site_dir}/000_ai_infra_bench_vllm_source.pth"

ENV PIP_NO_INDEX=1

COPY --from=git_runtime /vllm-history/.git /workspace/repo/.git

# Bind the byte-locked source tree to the exact upstream Base history. The
# wheel contributes only ignored native/generated runtime files.
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
    VLLM_NO_USAGE_STATS=1 \
    HOME=/home/agent

WORKDIR /workspace/repo
USER agent

RUN python3 -c "import importlib.util,pathlib,vllm; p=pathlib.Path(vllm.__file__).resolve(); s=importlib.util.find_spec('vllm._C'); print(vllm.__version__,p,s.origin if s else None); assert str(p).startswith('/workspace/repo/vllm/') and s is not None and str(s.origin).startswith('/workspace/repo/vllm/')" \
    && test "$(id -un)" = agent \
    && test -z "$(git remote)" \
    && test "$(git rev-parse HEAD)" = "${VLLM_SOURCE_COMMIT}" \
    && test -z "$(git status --porcelain)"

ENTRYPOINT []
CMD ["sleep", "infinity"]
