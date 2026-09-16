FROM node:22.23.2-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 AS source
RUN rm -f /etc/apt/sources.list.d/debian.sources \
 && printf 'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20260901T000000Z bookworm main\n' > /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git python3 build-essential curl ripgrep \
 && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /workspace/deepseek-harness \
 && git -C /workspace/deepseek-harness init -q \
 && git -C /workspace/deepseek-harness config core.logAllRefUpdates false \
 && git -C /workspace/deepseek-harness fetch --no-tags https://github.com/deepseek-ai/deepseek-harness.git 4e84901e6471b79ec0338099867ebb4606d12bb5 \
 && git -C /workspace/deepseek-harness checkout -q -b main 4e84901e6471b79ec0338099867ebb4606d12bb5 \
 && rm -f /workspace/deepseek-harness/.git/FETCH_HEAD \
 && git -C /workspace/deepseek-harness reflog expire --expire=now --all \
 && git -C /workspace/deepseek-harness gc --prune=now \
 && test -z "$(git -C /workspace/deepseek-harness fsck --full --no-reflogs --unreachable 2>/dev/null)" \
 && test -z "$(git -C /workspace/deepseek-harness remote)"

FROM source AS runtime
WORKDIR /workspace/deepseek-harness
RUN npm install -g pnpm@11.7.0 --no-audit --no-fund \
 && pnpm install --frozen-lockfile --ignore-scripts \
 && test -z "$(git status --porcelain)" \
 && test "$(git rev-parse HEAD)" = 4e84901e6471b79ec0338099867ebb4606d12bb5 \
 && test -z "$(git for-each-ref --format='%(refname)' refs/remotes refs/tags)" \
 && test ! -e .git/logs \
 && test ! -e .git/shallow
ENV CI=true
CMD ["/bin/bash"]
