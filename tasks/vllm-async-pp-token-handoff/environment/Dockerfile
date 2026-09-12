ARG BASE_IMAGE=vllm/vllm-openai:v0.14.1@sha256:8e67731819426f7df194e5a0dfd6649d3aa3474f80c44f75b1e8711e76f8030a
ARG VLLM_BASE_SHA=8ebf372e9d612a325f54aadf5c0c3c6588b6afa3
ARG VLLM_SOURCE_TREE=27422138dd790ac7992e774d438e0bf84d546c01
ARG VLLM_ORACLE_SHA=3e440786afe763e892e12125ee7529f95f141c54
ARG VLLM_REPOSITORY=https://github.com/vllm-project/vllm.git

FROM alpine/git:2.49.1@sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26 AS git-history
ARG VLLM_BASE_SHA
ARG VLLM_SOURCE_TREE
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
    test "$(git -C /vllm-history rev-parse 'HEAD^{tree}')" = "${VLLM_SOURCE_TREE}"; \
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

FROM ${BASE_IMAGE}

ARG VLLM_BASE_SHA
ARG VLLM_SOURCE_SHA256=22c309000b09e9824a0ba5f5837e2b76a32f001b964f4153343cb030e44ba2b7
ARG VLLM_SOURCE_TREE
ARG VLLM_ORACLE_SHA
ARG VLLM_SOURCE_URL=https://codeload.github.com/vllm-project/vllm/tar.gz/8ebf372e9d612a325f54aadf5c0c3c6588b6afa3

USER root
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /workspace

# v0.14.1 is the nearest official pre-cutoff release and matches exact base
# Torch 2.9.1 / CUDA 12.9. Exact base Python replaces the donor package; the
# copied native and generated-wrapper scope is asserted below.
RUN set -eux; \
    apt-get \
        -o Acquire::http::Proxy=false \
        -o Acquire::https::Proxy=false \
        update; \
    DEBIAN_FRONTEND=noninteractive apt-get \
        -o Acquire::http::Proxy=false \
        -o Acquire::https::Proxy=false \
        install -y --no-install-recommends \
        git=1:2.34.1-1ubuntu1.17 \
        git-man=1:2.34.1-1ubuntu1.17 \
        liberror-perl=0.17029-1; \
    rm -rf /var/lib/apt/lists/*; \
    command -v curl; \
    command -v git; \
    command -v torchrun; \
    curl -fL \
        --retry 8 \
        --retry-all-errors \
        --retry-delay 3 \
        --connect-timeout 30 \
        --max-time 600 \
        "${VLLM_SOURCE_URL}" \
        -o /tmp/vllm-source.tar.gz; \
    echo "${VLLM_SOURCE_SHA256}  /tmp/vllm-source.tar.gz" | sha256sum -c -; \
    mkdir -p /workspace/repo; \
    tar -xzf /tmp/vllm-source.tar.gz --strip-components=1 -C /workspace/repo; \
    rm -f /tmp/vllm-source.tar.gz

COPY --from=git-history /vllm-history/.git /workspace/repo/.git

RUN set -eux; \
    test "$(git -C /workspace/repo rev-parse HEAD)" = "${VLLM_BASE_SHA}"; \
    test "$(git -C /workspace/repo rev-parse 'HEAD^{tree}')" = "${VLLM_SOURCE_TREE}"; \
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
    find "${VLLM_SITE}" -type f \( -name '*.so' -o -name '_version.py' \) \
        -exec sh -c 'for src do rel="${src#"$0"/}"; dst="/workspace/repo/vllm/$rel"; mkdir -p "$(dirname "$dst")"; cp -a "$src" "$dst"; done' "${VLLM_SITE}" {} +; \
    for rel in \
        vllm_flash_attn/__init__.py \
        vllm_flash_attn/flash_attn_interface.py; do \
        test -f "${VLLM_SITE}/${rel}"; \
        cp -a "${VLLM_SITE}/${rel}" "/workspace/repo/vllm/${rel}"; \
    done; \
    test -z "$(git -C /workspace/repo status --porcelain=v1 --untracked-files=all)"; \
    PYTHONPATH=/workspace/repo python3 -c 'import importlib.util, pathlib, vllm, vllm.vllm_flash_attn; root=pathlib.Path("/workspace/repo").resolve(); src=pathlib.Path(vllm.__file__).resolve(); native=pathlib.Path(importlib.util.find_spec("vllm._C").origin).resolve(); flash=pathlib.Path(vllm.vllm_flash_attn.__file__).resolve(); assert src.is_relative_to(root), src; assert native.is_relative_to(root), native; assert flash.is_relative_to(root), flash; print("candidate_source", src); print("candidate_native", native); print("candidate_flash_wrapper", flash)'; \
    rm -f /root/.bash_history

COPY lock/runtime-native.json /workspace/environment-lock/runtime-native.json

RUN python3 -c 'import json, pathlib; manifest=json.loads(pathlib.Path("/workspace/environment-lock/runtime-native.json").read_text()); root=pathlib.Path("/workspace/repo/vllm"); actual=sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and (p.suffix == ".so" or p.name == "_version.py")); assert actual == manifest["copied_artifacts"], (actual, manifest["copied_artifacts"]); py_actual=sorted(p for p in manifest["copied_python_artifacts"] if (root / p).is_file()); assert py_actual == manifest["copied_python_artifacts"], py_actual; print("native_manifest_verified", len(actual), "python_shims_verified", len(py_actual))'

RUN set -eux; \
    if ! id -u agent >/dev/null 2>&1; then \
        useradd --create-home --shell /bin/bash agent; \
    fi; \
    chown -R agent:agent /workspace; \
    rm -f /home/agent/.bash_history

ENV PYTHONPATH=/workspace/repo \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    NCCL_DEBUG=WARN

USER agent
WORKDIR /workspace/repo
ENTRYPOINT []
CMD ["sleep", "infinity"]
