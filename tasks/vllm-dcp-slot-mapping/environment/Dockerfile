ARG BASE_IMAGE=vllm/vllm-openai:v0.17.0@sha256:14ea8b431aaaf75eb873c46c8ebfbad2b4b0790d30c66126d789d8cb9bd0aab9
FROM ${BASE_IMAGE} AS prepared

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

# Keep the no-network agent phase usable by terminal-based benchmark agents.
USER root
RUN apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 \
        -o Acquire::https::Timeout=30 -o Dir::Etc::sourceparts=- update \
 && DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=3 \
        -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 \
        install -y --no-install-recommends tmux \
 && rm -rf /var/lib/apt/lists/*
COPY lock/requirements.txt /tmp/upstream-test-requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/upstream-test-requirements.txt

# The donor's Python package and example tree are newer than the target Base.
# Import precedence is not isolation: remove these readable source copies.
RUN test -f /usr/local/lib/python3.12/dist-packages/vllm/v1/worker/gpu/model_runner.py \
 && test -f /workspace/repo/vllm/v1/worker/gpu/model_runner.py \
 && rm -rf /usr/local/lib/python3.12/dist-packages/vllm /vllm-workspace /root/.cache/pip /workspace/environment-lock \
 && ln -s /workspace/repo/vllm /usr/local/lib/python3.12/dist-packages/vllm \
 && python3 -c 'import pathlib,vllm; assert pathlib.Path(vllm.__file__).resolve().is_relative_to("/workspace/repo")'

# Export only the sanitized filesystem; donor source cannot survive in layers.
FROM scratch
COPY --from=prepared / /
ENV PATH="/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ENV NVARCH="x86_64"
ENV NVIDIA_REQUIRE_CUDA="cuda>=12.9 brand=unknown,driver>=535,driver<536 brand=grid,driver>=535,driver<536 brand=tesla,driver>=535,driver<536 brand=nvidia,driver>=535,driver<536 brand=quadro,driver>=535,driver<536 brand=quadrortx,driver>=535,driver<536 brand=nvidiartx,driver>=535,driver<536 brand=vapps,driver>=535,driver<536 brand=vpc,driver>=535,driver<536 brand=vcs,driver>=535,driver<536 brand=vws,driver>=535,driver<536 brand=cloudgaming,driver>=535,driver<536 brand=unknown,driver>=550,driver<551 brand=grid,driver>=550,driver<551 brand=tesla,driver>=550,driver<551 brand=nvidia,driver>=550,driver<551 brand=quadro,driver>=550,driver<551 brand=quadrortx,driver>=550,driver<551 brand=nvidiartx,driver>=550,driver<551 brand=vapps,driver>=550,driver<551 brand=vpc,driver>=550,driver<551 brand=vcs,driver>=550,driver<551 brand=vws,driver>=550,driver<551 brand=cloudgaming,driver>=550,driver<551 brand=unknown,driver>=560,driver<561 brand=grid,driver>=560,driver<561 brand=tesla,driver>=560,driver<561 brand=nvidia,driver>=560,driver<561 brand=quadro,driver>=560,driver<561 brand=quadrortx,driver>=560,driver<561 brand=nvidiartx,driver>=560,driver<561 brand=vapps,driver>=560,driver<561 brand=vpc,driver>=560,driver<561 brand=vcs,driver>=560,driver<561 brand=vws,driver>=560,driver<561 brand=cloudgaming,driver>=560,driver<561 brand=unknown,driver>=565,driver<566 brand=grid,driver>=565,driver<566 brand=tesla,driver>=565,driver<566 brand=nvidia,driver>=565,driver<566 brand=quadro,driver>=565,driver<566 brand=quadrortx,driver>=565,driver<566 brand=nvidiartx,driver>=565,driver<566 brand=vapps,driver>=565,driver<566 brand=vpc,driver>=565,driver<566 brand=vcs,driver>=565,driver<566 brand=vws,driver>=565,driver<566 brand=cloudgaming,driver>=565,driver<566 brand=unknown,driver>=570,driver<571 brand=grid,driver>=570,driver<571 brand=tesla,driver>=570,driver<571 brand=nvidia,driver>=570,driver<571 brand=quadro,driver>=570,driver<571 brand=quadrortx,driver>=570,driver<571 brand=nvidiartx,driver>=570,driver<571 brand=vapps,driver>=570,driver<571 brand=vpc,driver>=570,driver<571 brand=vcs,driver>=570,driver<571 brand=vws,driver>=570,driver<571 brand=cloudgaming,driver>=570,driver<571"
ENV NV_CUDA_CUDART_VERSION="12.9.79-1"
ENV CUDA_VERSION="12.9.1"
ENV LD_LIBRARY_PATH="/usr/local/nvidia/lib64:/usr/local/cuda/lib64:/usr/local/cuda/lib64"
ENV NVIDIA_VISIBLE_DEVICES="all"
ENV NVIDIA_DRIVER_CAPABILITIES="compute,utility"
ENV DEBIAN_FRONTEND="noninteractive"
ENV UV_HTTP_TIMEOUT="500"
ENV UV_INDEX_STRATEGY="unsafe-best-match"
ENV UV_LINK_MODE="copy"
ENV VLLM_ENABLE_CUDA_COMPATIBILITY="0"
ENV TORCH_CUDA_ARCH_LIST="7.0 7.5 8.0 8.9 9.0 10.0 12.0"
ENV VLLM_USAGE_SOURCE="production-docker-image"
ENV PYTHONUNBUFFERED="1"
ENV PIP_DISABLE_PIP_VERSION_CHECK="1"
ENV PYTHONPATH="/workspace/repo"
ENV HF_HUB_OFFLINE="1"
ENV TRANSFORMERS_OFFLINE="1"
ENV HOME="/home/agent"
ENV HF_HOME="/home/agent/.cache/huggingface"
ENV PYTHONDONTWRITEBYTECODE="1"
ENV PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
USER agent
WORKDIR /workspace/repo
ENTRYPOINT []
CMD ["sleep", "infinity"]
