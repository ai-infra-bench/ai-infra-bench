# The build itself runs without network: pi's own root `build:offline` script (the root
# `build` with the ai package's `build:offline`, i.e. without `generate-models`). No tracked
# file may change.
RUN --network=none npm run build:offline \
 && test -z "$(git status --porcelain)"

# Smoke: the published entry points exist, the faux provider is importable,
# vitest collects, and the CLI starts without network.
RUN test -f packages/coding-agent/dist/index.js \
 && test -f packages/ai/dist/providers/faux.js \
 && node -e "import('@earendil-works/pi-ai/providers/faux').then(m => { if (typeof m.fauxProvider !== 'function') throw new Error('faux missing'); })" \
 && (cd packages/coding-agent && node ../../node_modules/vitest/vitest.mjs run --reporter=dot test/path-utils.test.ts) \
 && node packages/coding-agent/dist/cli.js --version \
 && node --input-type=module -e "import { DefaultResourceLoader, SettingsManager } from '@earendil-works/pi-coding-agent'; const l = new DefaultResourceLoader({ cwd: '/workspace/pi', agentDir: '/tmp/pi-smoke-agent', settingsManager: SettingsManager.inMemory({}), additionalExtensionPaths: ['/workspace/pi/packages/coding-agent/examples/extensions/hello.ts'], noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true }); await l.reload(); const e = l.getExtensions(); if (e.errors.length || e.extensions.length !== 1) { console.error(e.errors); process.exit(1); }" \
 && command -v fd && command -v rg
