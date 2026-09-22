# Source workspace: validate the frozen catalog and checkout without compiling
# dist/. This mode does not claim a successful TypeScript build.
# Preserve source resolution for native tests, dynamic imports and subprocesses,
# matching the original source workspace instead of relying only on the pi CLI.
ENV TSX_TSCONFIG_PATH=/workspace/pi/tsconfig.json
ENV NODE_OPTIONS=--import=/workspace/pi/node_modules/tsx/dist/loader.mjs
RUN --network=none node packages/ai/scripts/check-model-data.ts \
 && test -z "$(git status --porcelain)"

# Keep the upstream source test smoke and required offline search tools. The
# source-only pi wrapper below also checks its CLI without network.
RUN --network=none cd packages/coding-agent \
 && node ../../node_modules/vitest/vitest.mjs run --reporter=dot test/path-utils.test.ts \
 && command -v fd && command -v rg
