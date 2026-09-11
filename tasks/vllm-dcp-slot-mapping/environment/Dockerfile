ARG BASE_IMAGE=vllm/vllm-openai:v0.17.0@sha256:14ea8b431aaaf75eb873c46c8ebfbad2b4b0790d30c66126d789d8cb9bd0aab9
FROM ${BASE_IMAGE}

ARG VLLM_BASE_SHA=be3af2d29e2507f32b2190fe015cd6609b348caa
ARG VLLM_SOURCE_TREE=fa64310667f4c1849399eedea2e4e05c57936453
ARG VLLM_REPO=https://github.com/vllm-project/vllm.git

USER root
ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /workspace

# The nearest pre-cutoff release uses Torch 2.9.1 while this exact base requires
# Torch 2.10. v0.17.0 is the first compatible official donor. Exact base Python
# and Triton sources replace its Python package; copied native scope is checked
# against the machine-readable manifest below.
RUN set -eux; \
    if ! command -v git >/dev/null 2>&1; then \
        apt-get update; \
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
            git=1:2.34.1-1ubuntu1.17 \
            git-man=1:2.34.1-1ubuntu1.17 \
            liberror-perl=0.17029-1; \
        rm -rf /var/lib/apt/lists/*; \
    fi; \
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
    while test -e /workspace/repo/.git/shallow; do \
      fetch_step --deepen=2000 --no-tags origin "${VLLM_BASE_SHA}"; \
    done; \
    git -C /workspace/repo checkout -q -b main "${VLLM_BASE_SHA}"; \
    test "$(git -C /workspace/repo rev-parse HEAD)" = "${VLLM_BASE_SHA}"; \
    test "$(git -C /workspace/repo rev-parse 'HEAD^{tree}')" = "${VLLM_SOURCE_TREE}"; \
    git -C /workspace/repo remote remove origin; \
    rm -rf /workspace/repo/.git/logs; \
    rm -f /workspace/repo/.git/FETCH_HEAD /workspace/repo/.git/ORIG_HEAD; \
    test -z "$(git -C /workspace/repo remote)"; \
    test -z "$(git -C /workspace/repo for-each-ref --format='%(refname)' refs/remotes refs/tags)"; \
    test "$(git -C /workspace/repo rev-list --all --count)" -gt 1; \
    test ! -e /workspace/repo/.git/shallow; \
    test -z "$(git -C /workspace/repo fsck --full --no-reflogs --unreachable --no-progress 2>/dev/null)"; \
    VLLM_SITE="$(python3 -c 'import pathlib, vllm; print(pathlib.Path(vllm.__file__).parent)')"; \
    find "${VLLM_SITE}" -type f \( -name '*.so' -o -name '_version.py' \) \
        -exec sh -c 'for src do rel="${src#"$0"/}"; dst="/workspace/repo/vllm/$rel"; mkdir -p "$(dirname "$dst")"; cp -a "$src" "$dst"; done' "${VLLM_SITE}" {} +; \
    for rel in \
        vllm_flash_attn/__init__.py \
        vllm_flash_attn/flash_attn_interface.py; do \
        test -f "${VLLM_SITE}/${rel}"; \
        cp -a "${VLLM_SITE}/${rel}" "/workspace/repo/vllm/${rel}"; \
    done; \
    test -z "$(git -C /workspace/repo status --porcelain)"; \
    PYTHONPATH=/workspace/repo python3 -c 'import importlib.util, pathlib, vllm; root=pathlib.Path("/workspace/repo").resolve(); src=pathlib.Path(vllm.__file__).resolve(); native=pathlib.Path(importlib.util.find_spec("vllm._C").origin).resolve(); assert src.is_relative_to(root), src; assert native.is_relative_to(root), native; print("candidate_source", src); print("candidate_native", native)'; \
    rm -f /root/.bash_history

COPY lock/native-donor.json /workspace/environment-lock/native-donor.json

RUN python3 -c 'import json, pathlib; manifest=json.loads(pathlib.Path("/workspace/environment-lock/native-donor.json").read_text()); root=pathlib.Path("/workspace/repo/vllm"); actual=sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and (p.suffix == ".so" or p.name == "_version.py")); assert actual == manifest["copied_artifacts"], (actual, manifest["copied_artifacts"]); py_actual=sorted(p for p in manifest["copied_python_artifacts"] if (root / p).is_file()); assert py_actual == manifest["copied_python_artifacts"], py_actual; assert manifest["target_native_intersection"] == []; print("native_manifest_verified", len(actual), "python_shims_verified", len(py_actual))'

RUN set -eux; \
    if ! id -u agent >/dev/null 2>&1; then \
        useradd --create-home --shell /bin/bash agent; \
    fi; \
    if ! command -v python >/dev/null 2>&1; then \
        ln -s "$(command -v python3)" /usr/local/bin/python; \
    fi; \
    chown -R agent:agent /workspace; \
    rm -f /home/agent/.bash_history

ENV PYTHONPATH=/workspace/repo \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

USER agent
WORKDIR /workspace/repo
ENTRYPOINT []
CMD ["sleep", "infinity"]
