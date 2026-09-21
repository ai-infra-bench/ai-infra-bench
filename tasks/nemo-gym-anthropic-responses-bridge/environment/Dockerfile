FROM public.ecr.aws/docker/library/python:3.12.13-slim-bookworm@sha256:6e13e65c55e33adf203d77ee371cf8bf5d81bd4902ef07565721f46bf44917af
RUN rm -f /etc/apt/sources.list.d/debian.sources \
 && printf 'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20260901T000000Z bookworm main\n' > /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends git ripgrep procps util-linux \
 && rm -rf /var/lib/apt/lists/*
COPY lock/requirements.txt /opt/bridge-requirements.txt
RUN pip install --no-cache-dir setuptools==80.9.0 wheel==0.45.1 \
 && pip install --no-cache-dir --no-build-isolation --no-deps --require-hashes -r /opt/bridge-requirements.txt
WORKDIR /workspace/Gym
RUN git init -q \
 && git config core.logAllRefUpdates false \
 && git fetch --depth=1 --no-tags https://github.com/NVIDIA-NeMo/Gym.git 797db2912ced96991ae4944a3fffc9d9c445ece0 \
 && git checkout -q -b main 797db2912ced96991ae4944a3fffc9d9c445ece0 \
 && rm -f .git/FETCH_HEAD \
 && test -z "$(git remote)" \
 && test -z "$(git status --porcelain)" \
 && test -z "$(git fsck --full --no-reflogs --unreachable 2>/dev/null)" \
 && test "$(git rev-list --all --count)" = 1 \
 && useradd --create-home --shell /bin/bash agent \
 && chown -R agent:agent /workspace/Gym
# Register normal project metadata/CLI entry points, then remove editable import
# hooks so the trusted verifier can never discover candidate source implicitly.
RUN pip install --no-cache-dir --no-build-isolation --no-deps -e . \
 && rm -f /usr/local/lib/python3.12/site-packages/__editable__*nemo_gym* \
 && chown -R agent:agent /workspace/Gym
ENV PYTHONPATH=/workspace/Gym
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["/bin/bash"]

# Public protocol specification accompanying the task request.
COPY bridge-contract.md /opt/nemo-gym/docs/bridge-contract.md
