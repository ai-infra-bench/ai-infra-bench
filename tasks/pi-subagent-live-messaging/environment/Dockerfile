FROM node:22.23.2-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5
RUN rm -f /etc/apt/sources.list.d/debian.sources \
 && printf 'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20260901T000000Z bookworm main\n' > /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git python3 curl ripgrep \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace/pi
RUN git init -q \
 && git config core.logAllRefUpdates false \
 && git fetch --no-tags https://github.com/earendil-works/pi.git 71dca871bc80b6bc97be37f0ca3189399d651fff \
 && git checkout -q -b main 71dca871bc80b6bc97be37f0ca3189399d651fff \
 && rm -f .git/FETCH_HEAD \
 && git reflog expire --expire=now --all \
 && git gc --prune=now \
 && test -z "$(git fsck --full --no-reflogs --unreachable 2>/dev/null)" \
 && npm ci --ignore-scripts --no-audit --no-fund
# Only the release's generated JSON catalogs, never its compiled source.
COPY model-data.tar.gz /tmp/pi-model-data.tar.gz
RUN tar -xzf /tmp/pi-model-data.tar.gz -C packages/ai/src/providers \
 && rm /tmp/pi-model-data.tar.gz \
 && node packages/ai/scripts/check-model-data.ts \
 && test -z "$(git status --porcelain)" \
 && test -z "$(git remote)" \
 && test ! -e .git/logs
ENV TSX_TSCONFIG_PATH=/workspace/pi/tsconfig.json
ENV NODE_OPTIONS=--import=/workspace/pi/node_modules/tsx/dist/loader.mjs
ENV PI_NO_LOCAL_LLM=1
RUN printf '#!/bin/sh\nexec node /workspace/pi/packages/coding-agent/src/cli.ts "$@"\n' > /usr/local/bin/pi \
 && chmod +x /usr/local/bin/pi \
 && pi --version \
 && useradd --create-home --shell /bin/bash agent \
 && chown -R agent:agent /workspace/pi
CMD ["/bin/bash"]
