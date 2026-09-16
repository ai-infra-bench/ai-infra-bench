# syntax=docker/dockerfile:1

ARG BASE_IMAGE=vllm/vllm-openai-cpu@sha256:d19978a2d4bb2289c740a6c89d4cc15fbcf4d20d916f1e268168b8bbad3b776b
FROM ${BASE_IMAGE} AS prepared

ARG BASE_IMAGE
ARG VLLM_BASE_SHA=d88f28da05b12bc7d63ebe3dcedf445ecb274343
ARG VLLM_BASE_TREE=037cc4e534167733500093aa225de6ab64a1028e
ARG VLLM_REPO=https://github.com/vllm-project/vllm.git

USER 0:0
ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_DATASETS_OFFLINE=1 \
    PIP_NO_INDEX=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    TOKENIZERS_PARALLELISM=false \
    TORCH_DEVICE_BACKEND_AUTOLOAD=0 \
    HOME=/home/agent

RUN case "${BASE_IMAGE}" in \
      *@sha256:d19978a2d4bb2289c740a6c89d4cc15fbcf4d20d916f1e268168b8bbad3b776b) ;; \
      *) echo "BASE_IMAGE must be the frozen v0.17.1 x86_64 CPU manifest" >&2; exit 1 ;; \
    esac

# Keep only compiled extensions and generated version metadata from the
# digest-pinned official release. Candidate Python source is supplied below.
RUN set -eu; \
    installed_vllm="$(python3 -c 'import pathlib,vllm; print(pathlib.Path(vllm.__file__).resolve().parent)')"; \
    mkdir -p /opt/vllm-native-overlay; \
    cd "${installed_vllm}"; \
    find . -type f \( -name '*.so' -o -name '_version.py' \) -print0 \
      | tar --null --files-from=- -cf - \
      | tar -C /opt/vllm-native-overlay -xf -; \
    test -n "$(find /opt/vllm-native-overlay -type f -name '*.so' -print -quit)"

# Fetch the exact Base with its reachable history, then remove every remote,
# reflog and fetch artifact that could reveal post-cutoff source.
RUN set -eu; \
    mkdir -p /app; \
    cd /app; \
    git init -q; \
    git config core.logAllRefUpdates false; \
    git config http.version HTTP/1.1; \
    git remote add origin "${VLLM_REPO}"; \
    fetch_step() { \
      for attempt in 1 2 3; do \
        git fetch "$@" && return 0; \
      done; \
      return 1; \
    }; \
    fetch_step --depth=2000 --no-tags origin "${VLLM_BASE_SHA}"; \
    while test -e .git/shallow; do \
      fetch_step --deepen=2000 --no-tags origin "${VLLM_BASE_SHA}"; \
    done; \
    git checkout -q -b main "${VLLM_BASE_SHA}"; \
    test "$(git rev-parse HEAD)" = "${VLLM_BASE_SHA}"; \
    test "$(git rev-parse 'HEAD^{tree}')" = "${VLLM_BASE_TREE}"; \
    git remote remove origin; \
    rm -rf .git/logs; \
    rm -f .git/FETCH_HEAD .git/ORIG_HEAD; \
    test -z "$(git remote)"; \
    test -z "$(git for-each-ref --format='%(refname)' refs/remotes refs/tags)"; \
    test "$(git rev-list --all --count)" -gt 1; \
    test ! -e .git/shallow; \
    test -z "$(git fsck --full --no-reflogs --unreachable --no-progress 2>/dev/null)"

RUN set -eu; \
    cp -a /opt/vllm-native-overlay/. /app/vllm/; \
    cd /app; \
    find /opt/vllm-native-overlay -type f -printf '/vllm/%P\n' \
      | sort >> .git/info/exclude; \
    site_dir="$(python3 -c 'import site; print(site.getsitepackages()[0])')"; \
    printf 'import sys; sys.path.insert(0, "/app")\n' \
      > "${site_dir}/vllm-candidate-source.pth"; \
    cd /tmp; \
    python3 -I -c 'import importlib.util,pathlib,torch,vllm; root=pathlib.Path("/app"); assert pathlib.Path(vllm.__file__).resolve().is_relative_to(root); spec=importlib.util.find_spec("vllm._C"); assert spec and pathlib.Path(spec.origin).resolve().is_relative_to(root); assert torch.__version__ == "2.10.0+cpu"; assert torch.version.cuda is None; assert not torch.cuda.is_available()'; \
    cd /app; \
    test -z "$(git status --porcelain=v1 --untracked-files=all)"

RUN groupadd --gid 10001 agent \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/agent agent \
    && chown -R agent:agent /app /home/agent \
    && chmod -R a-w /opt/vllm-native-overlay

WORKDIR /app
# Keep the no-network agent phase usable by terminal-based benchmark agents.
USER 0:0
RUN apt-get -o Acquire::Retries=3 \
        -o Acquire::http::Timeout=30 \
        -o Acquire::https::Timeout=30 update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tmux \
 && rm -rf /var/lib/apt/lists/*
COPY lock/requirements.txt /tmp/upstream-test-requirements.txt
RUN PIP_NO_INDEX=0 /opt/venv/bin/python -m pip install --no-cache-dir -r /tmp/upstream-test-requirements.txt

# Normal upstream scheduler tests use this public, pre-cutoff model metadata.
# No weights, task-specific reproducers, or hidden test inputs are included.
COPY lock/hf-cache/ /home/agent/.cache/huggingface/hub/
RUN chown -R agent:agent /home/agent/.cache

# The source checkout, not a readable donor wheel, is the only vLLM source.
RUN test -f /opt/venv/lib/python3.12/site-packages/vllm/v1/core/sched/scheduler.py \
 && test -f /app/vllm/v1/core/sched/scheduler.py \
 && rm -rf /opt/venv/lib/python3.12/site-packages/vllm /root/.cache/uv /vllm-workspace \
 && ln -s /app/vllm /opt/venv/lib/python3.12/site-packages/vllm \
 && python -c 'import pathlib,vllm; assert pathlib.Path(vllm.__file__).resolve().is_relative_to("/app")'

# Export only the sanitized filesystem; donor source cannot survive in layers.
FROM scratch
COPY --from=prepared / /
ENV PATH="/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ENV CC="/usr/bin/gcc-12"
ENV CXX="/usr/bin/g++-12"
ENV CCACHE_DIR="/root/.cache/ccache"
ENV CMAKE_CXX_COMPILER_LAUNCHER="ccache"
ENV VIRTUAL_ENV="/opt/venv"
ENV UV_PYTHON_INSTALL_DIR="/opt/uv/python"
ENV UV_HTTP_TIMEOUT="500"
ENV PIP_EXTRA_INDEX_URL="https://download.pytorch.org/whl/cpu"
ENV UV_EXTRA_INDEX_URL="https://download.pytorch.org/whl/cpu"
ENV UV_INDEX_STRATEGY="unsafe-best-match"
ENV UV_LINK_MODE="copy"
ENV TARGETARCH="amd64"
ENV LD_PRELOAD="/usr/lib/x86_64-linux-gnu/libtcmalloc_minimal.so.4:/opt/venv/lib/libiomp5.so"
ENV HF_HUB_OFFLINE="1"
ENV TRANSFORMERS_OFFLINE="1"
ENV HF_DATASETS_OFFLINE="1"
ENV PIP_NO_INDEX="1"
ENV PIP_DISABLE_PIP_VERSION_CHECK="1"
ENV PYTHONDONTWRITEBYTECODE="1"
ENV PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
ENV TOKENIZERS_PARALLELISM="false"
ENV TORCH_DEVICE_BACKEND_AUTOLOAD="0"
ENV HOME="/home/agent"
ENV HF_HOME="/home/agent/.cache/huggingface"
USER 10001:10001
WORKDIR /app
ENTRYPOINT []
CMD ["sleep", "infinity"]
