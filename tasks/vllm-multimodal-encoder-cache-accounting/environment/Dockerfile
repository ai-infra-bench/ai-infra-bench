# vLLM 0.11.2 is the nearest released official image to base commit
# 676db55eecf8b6d9ec38ea243cf6f35ea8378ec6 (0.11.2.dev278). The amd64
# platform manifest is pinned, rather than the mutable release tag.
ARG BASE_IMAGE=vllm/vllm-openai@sha256:47a9896f86818fea323b2d38082758c62d9a0155d6fe6c4dbd7d735c556f680a
ARG VLLM_BASE_SHA=676db55eecf8b6d9ec38ea243cf6f35ea8378ec6
ARG VLLM_BASE_TREE=aafa39e6544cbeaf83b72985f83aaefd4e9e3456
ARG VLLM_ORACLE_SHA=f5f51e5931ffd99afe69696b60765b88d3eb13f2
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

FROM ${BASE_IMAGE}

ARG BASE_IMAGE
ARG VLLM_BASE_SHA
ARG VLLM_BASE_TREE
ARG VLLM_ORACLE_SHA
ARG VLLM_SOURCE_SHA256=ac774fb6bbf75b083d997dcb70b5cdf8746c6e6bfa8d95b3c2415a6c30240624
ARG VLLM_SOURCE_URL=https://codeload.github.com/vllm-project/vllm/tar.gz/676db55eecf8b6d9ec38ea243cf6f35ea8378ec6
ARG PYTEST_WHEEL_URL=https://files.pythonhosted.org/packages/d4/24/a372aaf5c9b7208e7112038812994107bc65a84cd00e0354a88c2c77a617/pytest-9.0.3-py3-none-any.whl
ARG PYTEST_WHEEL_SHA256=2c5efc453d45394fdd706ade797c0a81091eccd1d6e4bccfcd476e2b8e0ab5d9
ARG TBLIB_WHEEL_URL=https://files.pythonhosted.org/packages/27/44/aa5c8b10b2cce7a053018e0d132bd58e27527a0243c4985383d5b6fd93e9/tblib-3.1.0-py3-none-any.whl
ARG TBLIB_WHEEL_SHA256=670bb4582578134b3d81a84afa1b016128b429f3d48e6cbbaecc9d15675e984e
ARG INICONFIG_WHEEL_URL=https://files.pythonhosted.org/packages/2c/e1/e6716421ea10d38022b952c159d5161ca1193197fb744506875fbb87ea7b/iniconfig-2.1.0-py3-none-any.whl
ARG INICONFIG_WHEEL_SHA256=9deba5723312380e77435581c6bf4935c94cbfab9b1ed33ef8d238ea168eb760
ARG PACKAGING_WHEEL_URL=https://files.pythonhosted.org/packages/20/12/38679034af332785aac8774540895e234f4d07f7545804097de4b666afd8/packaging-25.0-py3-none-any.whl
ARG PACKAGING_WHEEL_SHA256=29572ef2b1f17581046b3a2227d5c611fb25ec70ca1ba8554b24b0e69331a484
ARG PLUGGY_WHEEL_URL=https://files.pythonhosted.org/packages/54/20/4d324d65cc6d9205fabedc306948156824eb9f0ee1633355a8f7ec5c66bf/pluggy-1.6.0-py3-none-any.whl
ARG PLUGGY_WHEEL_SHA256=e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746
ARG PYGMENTS_WHEEL_URL=https://files.pythonhosted.org/packages/f4/7e/a72dd26f3b0f4f2bf1dd8923c85f7ceb43172af56d63c7383eb62b332364/pygments-2.20.0-py3-none-any.whl
ARG PYGMENTS_WHEEL_SHA256=81a9e26dd42fd28a23a2d169d86d7ac03b46e2f8b59ed4698fb4785f946d0176

USER 0:0
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PIP_NO_INDEX=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VLLM_VERSION_OVERRIDE=0.11.2.dev278 \
    HOME=/home/agent

# Reject accidental tag-only or cross-platform overrides. Runtime dependencies
# and CUDA extensions come from the official v0.11.2 amd64 image.
RUN case "${BASE_IMAGE}" in \
      *@sha256:47a9896f86818fea323b2d38082758c62d9a0155d6fe6c4dbd7d735c556f680a) ;; \
      *) echo "BASE_IMAGE must be the frozen v0.11.2 amd64 manifest" >&2; exit 1 ;; \
    esac

# The former image omitted pytest, making the public reproduction unusable.
# Install a byte-locked test stack; runtime remains network-disabled.
RUN set -eu; \
    mkdir -p /tmp/pytest-wheels; \
    for item in \
      "${PYTEST_WHEEL_URL}|${PYTEST_WHEEL_SHA256}|pytest-9.0.3-py3-none-any.whl" \
      "${TBLIB_WHEEL_URL}|${TBLIB_WHEEL_SHA256}|tblib-3.1.0-py3-none-any.whl" \
      "${INICONFIG_WHEEL_URL}|${INICONFIG_WHEEL_SHA256}|iniconfig-2.1.0-py3-none-any.whl" \
      "${PACKAGING_WHEEL_URL}|${PACKAGING_WHEEL_SHA256}|packaging-25.0-py3-none-any.whl" \
      "${PLUGGY_WHEEL_URL}|${PLUGGY_WHEEL_SHA256}|pluggy-1.6.0-py3-none-any.whl" \
      "${PYGMENTS_WHEEL_URL}|${PYGMENTS_WHEEL_SHA256}|pygments-2.20.0-py3-none-any.whl"; do \
        url="${item%%|*}"; rest="${item#*|}"; \
        digest="${rest%%|*}"; file="${rest##*|}"; \
        curl --fail --location --retry 5 --connect-timeout 30 \
          "${url}" -o "/tmp/pytest-wheels/${file}"; \
        printf '%s  %s\n' "${digest}" "/tmp/pytest-wheels/${file}" \
          | sha256sum --check --strict; \
      done; \
    python3 -m pip install --no-index --no-deps /tmp/pytest-wheels/*.whl; \
    python3 -m pytest --version | grep -F 'pytest 9.0.3'; \
    rm -rf /tmp/pytest-wheels

# Preserve the official image's compiled extensions and generated version
# module separately. Candidate Python source is then materialized from the
# exact, hash-verified base commit.
# Force-add is required because the upstream archive contains a few tracked
# files that also match the repository's own ignore rules.
RUN set -eu; \
    installed_vllm="$(python3 -c 'import pathlib,vllm; print(pathlib.Path(vllm.__file__).resolve().parent)')"; \
    mkdir -p /opt/vllm-native-overlay; \
    cd "${installed_vllm}"; \
    find . -type f \( -name '*.so' -o -name '_version.py' \) -print0 \
      | tar --null --files-from=- -cf - \
      | tar -C /opt/vllm-native-overlay -xf -; \
    test -n "$(find /opt/vllm-native-overlay -type f -name '*.so' -print -quit)"

RUN set -eu; \
    curl --fail --location --retry 5 --connect-timeout 30 \
      "${VLLM_SOURCE_URL}" \
      -o /tmp/vllm-source.tar.gz; \
    printf '%s  %s\n' "${VLLM_SOURCE_SHA256}" /tmp/vllm-source.tar.gz \
      | sha256sum --check --strict; \
    mkdir -p /app; \
    tar -xzf /tmp/vllm-source.tar.gz -C /app --strip-components=1; \
    rm /tmp/vllm-source.tar.gz

COPY --from=git-history /vllm-history/.git /app/.git

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

# Apply only the compiled shared objects from the same official release line.
# Their exact runtime locations are ignored without hiding any candidate Python
# source. An executable .pth places /app before the installed wheel package.
RUN set -eu; \
    cp -a /opt/vllm-native-overlay/. /app/vllm/; \
    cd /app; \
    find /opt/vllm-native-overlay -type f -printf '/vllm/%P\n' \
      | sort >> .git/info/exclude; \
    site_dir="$(python3 -c 'import site; print(site.getsitepackages()[0])')"; \
    printf 'import sys; sys.path.insert(0, "/app")\n' \
      > "${site_dir}/vllm-candidate-source.pth"; \
    cd /tmp; \
    python3 -I -c 'import importlib.util,pathlib,torch,vllm; root=pathlib.Path("/app"); assert pathlib.Path(vllm.__file__).resolve().is_relative_to(root); spec=importlib.util.find_spec("vllm._C"); assert spec and pathlib.Path(spec.origin).resolve().is_relative_to(root); assert torch.__version__.startswith("2.9."); assert torch.version.cuda == "12.9"'; \
    cd /app; \
    test -z "$(git status --porcelain=v1 --untracked-files=all)"

RUN groupadd --gid 10001 agent \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/agent agent \
    && chown -R agent:agent /app /home/agent \
    && chmod -R a-w /opt/vllm-native-overlay

WORKDIR /app
USER 10001:10001
RUN python3 -m pytest --collect-only -q tests/v1/core/test_encoder_cache_manager.py
ENTRYPOINT []
CMD ["sleep", "infinity"]
