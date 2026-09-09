# syntax=docker/dockerfile:1

ARG VLLM_BASE_SHA=dc917cceb877dfd13f98c538c4c96158047d98bd
ARG VLLM_BASE_TREE=89beecb205e031cbb82e2eea9d2cd0f350135b8c
ARG VLLM_ORACLE_SHA=c4e744dbd41f23ee7fd554a86cc1bf516082552d
ARG VLLM_REPOSITORY=https://github.com/vllm-project/vllm.git

FROM alpine/git:2.49.1@sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26 AS git_runtime
ARG VLLM_BASE_SHA
ARG VLLM_BASE_TREE
ARG VLLM_ORACLE_SHA
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

ARG BASE_IMAGE=vllm/vllm-openai@sha256:1d6866b87630d94f5e0cdae55ab5abb4ce0b03fcb84d9d10612f9d518d19d4fd
FROM vllm/vllm-openai@sha256:1d6866b87630d94f5e0cdae55ab5abb4ce0b03fcb84d9d10612f9d518d19d4fd

ARG BASE_IMAGE
ARG VLLM_BASE_SHA
ARG VLLM_BASE_TREE
ARG VLLM_ORACLE_SHA
ARG VLLM_SOURCE_SHA256=de9e3f1e4782c9ff5c01bbc4f2daaeaa16f52bfe0ddfca2843b0ed4ecf849421
ARG VLLM_SOURCE_URL=https://codeload.github.com/vllm-project/vllm/tar.gz/dc917cceb877dfd13f98c538c4c96158047d98bd
ARG CUTLASS_SOURCE_SHA256=a4513ba33ae82fd754843c6d8437bee1ac71a6ef1c74df886de2338e3917d4df
ARG CUTLASS_SOURCE_URL=https://codeload.github.com/NVIDIA/cutlass/tar.gz/refs/tags/v4.2.1
ARG CMAKE_WHEEL_SHA256=2f766bb46367e5e0559fa33184653754bce044583a06014dcaebf8e6dff8a1f1
ARG CMAKE_WHEEL_URL=https://files.pythonhosted.org/packages/f4/2e/cefc60143950ca1a8dda26d4c8484e6fc406db16e7ca098ebae549de35f9/cmake-3.31.10-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
ARG CMAKE_WHEEL_FILE=cmake-3.31.10-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl

USER 0:0
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_DATASETS_OFFLINE=1 \
    PIP_NO_INDEX=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    TOKENIZERS_PARALLELISM=false \
    VLLM_TARGET_DEVICE=cuda \
    TORCH_CUDA_ARCH_LIST=8.0 \
    VLLM_CUTLASS_SRC_DIR=/opt/cutlass \
    MAX_JOBS=8 \
    NVCC_THREADS=2 \
    HOME=/home/agent

RUN case "${BASE_IMAGE}" in \
      *@sha256:1d6866b87630d94f5e0cdae55ab5abb4ce0b03fcb84d9d10612f9d518d19d4fd) ;; \
      *) echo "BASE_IMAGE must be the frozen v0.14.0 linux/amd64 manifest" >&2; exit 1 ;; \
    esac

COPY --from=git_runtime /git-runtime.tar /tmp/git-runtime.tar
RUN tar -xzf /tmp/git-runtime.tar -C / \
    && rm /tmp/git-runtime.tar \
    && ln -s libpcre2-8.so.0.14.0 /usr/lib/libpcre2-8.so.0 \
    && ln -s libz.so.1.3.1 /usr/lib/libz.so.1 \
    && git --version

# All network inputs are byte-locked. Validation serves them from A100
# loopback, so proxy credentials never enter build arguments or image layers.
RUN set -eu; \
    curl --fail --location --retry 5 --connect-timeout 30 \
      "${VLLM_SOURCE_URL}" -o /tmp/vllm-source.tar.gz; \
    curl --fail --location --retry 5 --connect-timeout 30 \
      "${CUTLASS_SOURCE_URL}" -o /tmp/cutlass-source.tar.gz; \
    curl --fail --location --retry 5 --connect-timeout 30 \
      "${CMAKE_WHEEL_URL}" -o "/tmp/${CMAKE_WHEEL_FILE}"; \
    printf '%s  %s\n' "${VLLM_SOURCE_SHA256}" /tmp/vllm-source.tar.gz \
      | sha256sum --check --strict; \
    printf '%s  %s\n' "${CUTLASS_SOURCE_SHA256}" /tmp/cutlass-source.tar.gz \
      | sha256sum --check --strict; \
    printf '%s  %s\n' "${CMAKE_WHEEL_SHA256}" "/tmp/${CMAKE_WHEEL_FILE}" \
      | sha256sum --check --strict; \
    mkdir -p /app /opt/cutlass; \
    python3 -m pip install --no-index --no-deps "/tmp/${CMAKE_WHEEL_FILE}"; \
    tar -xzf /tmp/vllm-source.tar.gz -C /app --strip-components=1; \
    tar -xzf /tmp/cutlass-source.tar.gz -C /opt/cutlass --strip-components=1; \
    rm -rf /tmp/vllm-source.tar.gz \
      /tmp/cutlass-source.tar.gz "/tmp/${CMAKE_WHEEL_FILE}"; \
    test "$(cmake --version | sed -n '1s/.* //p')" = 3.31.10; \
    git --version

COPY --from=git_runtime /vllm-history/.git /app/.git

# Bind the byte-locked source to the exact upstream Base and its parent
# history. No upstream remotes, tags, reflogs, or future objects survive.
RUN set -eu; \
    cd /app; \
    test "$(git rev-parse HEAD)" = "${VLLM_BASE_SHA}"; \
    test "$(git rev-parse 'HEAD^{tree}')" = "${VLLM_BASE_TREE}"; \
    test -z "$(git remote)"; \
    test -z "$(git for-each-ref --format='%(refname)' refs/remotes refs/tags)"; \
    test ! -e .git/logs; \
    test ! -e .git/FETCH_HEAD; \
    test ! -e .git/ORIG_HEAD; \
    test ! -e .git/shallow; \
    test "$(git rev-list --count HEAD)" -gt 1; \
    test -z "$(git rev-list --all --not "${VLLM_BASE_SHA}")"; \
    test -z "$(git fsck --full --no-reflogs --unreachable --no-progress 2>/dev/null)"; \
    ! git cat-file -e "${VLLM_ORACLE_SHA}^{commit}" 2>/dev/null; \
    test -z "$(git status --porcelain=v1 --untracked-files=all)"

# Bake the Base `_moe_C` extension from the byte-locked candidate source. The
# compile orchestration is inlined here (build context only) so no agent-visible
# scoring script is shipped; the verifier rebuilds identically from its own
# read-only mount at grading time. Source-provenance locking is enforced by the
# out-of-image curator audit, not by an in-image gate script.
RUN set -eu; \
    site_dir="$(python3 -c 'import site; print(site.getsitepackages()[0])')"; \
    printf 'import sys; sys.path.insert(0, "/app")\n' \
      > "${site_dir}/vllm-candidate-source.pth"; \
    nvidia_site=/usr/local/lib/python3.12/dist-packages/nvidia; \
    nvidia_includes="$(find "${nvidia_site}" -mindepth 2 -maxdepth 2 -type d -name include -print | sort | paste -sd: -)"; \
    test -n "${nvidia_includes}"; \
    export CPATH="${nvidia_includes}${CPATH:+:${CPATH}}"; \
    cmake_backup="$(mktemp /tmp/vllm-cmake.XXXXXX)"; \
    cp -p /app/CMakeLists.txt "${cmake_backup}"; \
    python3 -c 'import pathlib; p=pathlib.Path("/app/CMakeLists.txt"); t=p.read_text(); m="\n# For CUDA and HIP builds also build the triton_kernels external package.\n"; assert t.count(m)==1; p.write_text(t.replace(m,"\nreturn()\n"+m))'; \
    cmake -S /app -B /app/build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_CUDA_ARCHITECTURES=80 \
      -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc \
      -DCMAKE_INSTALL_PREFIX=/app \
      -DCUDA_nvrtc_LIBRARY=/usr/local/lib/python3.12/dist-packages/nvidia/cuda_nvrtc/lib/libnvrtc.so.12 \
      -DFETCHCONTENT_BASE_DIR=/app/.deps \
      -DNVCC_THREADS=2 \
      -DVLLM_CUTLASS_SRC_DIR=/opt/cutlass \
      -DVLLM_PYTHON_EXECUTABLE=/usr/bin/python3 \
      -DVLLM_TARGET_DEVICE=cuda; \
    cmake --build /app/build -j 8 --target _moe_C; \
    cmake --install /app/build --prefix /app --component _moe_C; \
    mv "${cmake_backup}" /app/CMakeLists.txt; \
    native="$(find /app/vllm -maxdepth 1 -type f -name '_moe_C*.so' -print -quit)"; \
    test -n "${native}"; \
    /usr/local/cuda/bin/cuobjdump --list-elf "${native}" | grep -q 'sm_80'; \
    printf '/build/\n/.deps/\n/vllm/_moe_C*.so\n' >> /app/.git/info/exclude; \
    test -z "$(cd /app && git status --porcelain=v1 --untracked-files=all)"

# Candidate Python and the exact-source native extension both resolve under
# /app. Other release extensions are not copied into the candidate tree.
RUN set -eu; \
    site_dir="$(python3 -c 'import site; print(site.getsitepackages()[0])')"; \
    printf 'import sys; sys.path.insert(0, "/app")\n' \
      > "${site_dir}/vllm-candidate-source.pth"; \
    cd /tmp; \
    python3 -I -c 'import importlib.util,pathlib,torch,vllm; root=pathlib.Path("/app"); assert pathlib.Path(vllm.__file__).resolve().is_relative_to(root); spec=importlib.util.find_spec("vllm._moe_C"); assert spec and pathlib.Path(spec.origin).resolve().is_relative_to(root); torch.ops.load_library(spec.origin); assert torch.ops._moe_C.moe_permute_unpermute_supported()'; \
    test -z "$(cd /app && git status --porcelain=v1 --untracked-files=all)"

RUN groupadd --gid 10001 agent \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/agent agent \
    && chown -R agent:agent /app /home/agent \
    && chmod -R a-w /opt/cutlass

WORKDIR /app
USER 10001:10001
ENTRYPOINT []
CMD ["sleep", "infinity"]
