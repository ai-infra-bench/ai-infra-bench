# This wrapper selects the source CLI. Workspace mode separately determines
# whether other Node processes also inherit TSX. COPY needs no build context.
COPY --chown=0:0 --chmod=0755 <<'PI_SOURCE_CLI_EOF' /usr/local/bin/pi
#!/bin/sh
TSX_TSCONFIG_PATH=/workspace/pi/tsconfig.json \
NODE_OPTIONS=--import=/workspace/pi/node_modules/tsx/dist/loader.mjs \
exec node /workspace/pi/packages/coding-agent/src/cli.ts "$@"
PI_SOURCE_CLI_EOF
RUN --network=none test "$(stat -c %U /usr/local/bin/pi)" = root \
 && pi --version
