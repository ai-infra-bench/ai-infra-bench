import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = process.env.DSH_ROOT || '/workspace/deepseek-harness'
const tests = dirname(fileURLToPath(import.meta.url))
const require = createRequire(resolve(root, 'package.json'))
const ts = require('typescript')
const config = ts.readConfigFile(resolve(root, 'tsconfig.base.json'), ts.sys.readFile).config
const alias = [
  { find: /^@deepseek-ai\/dsh-llm-pi-ai\/src\/(.*)$/, replacement: resolve(root, 'packages/llm/llm-pi-ai/src/$1') },
  { find: /^@deepseek-ai\/dsh-api-session-controller\/src\/(.*)$/, replacement: resolve(root, 'packages/api/session-controller/src/$1') },
{ find: /^vitest$/, replacement: resolve(dirname(require.resolve('vitest/package.json')), 'dist/index.js') }]

export default {
  root,
  plugins: [{
    name: 'workspace-source',
    enforce: 'pre',
    transform(code, id) {
      const file = id.split('?', 1)[0]
      if (!/\.[cm]?tsx?$/.test(file) || !/^\s*@[A-Za-z_$][\w$]*/m.test(code)) return
      const result = ts.transpileModule(code, { fileName: file, compilerOptions: {
        target: ts.ScriptTarget.ES2024, module: ts.ModuleKind.ESNext,
        jsx: file.endsWith('x') ? ts.JsxEmit.ReactJSX : undefined, sourceMap: true,
      } })
      return { code: result.outputText.replace(/\n?\/\/# sourceMappingURL=.*$/u, '\n'), map: result.sourceMapText }
    },
    resolveId(source, importer) {
      if (!source.startsWith('@deepseek-ai/') && !['cordis', 'cosmokit', 'schemastery'].includes(source) && !source.startsWith('@cordisjs/')) return
      return ts.resolveModuleName(source, importer || resolve(root, 'entry.ts'), {
        baseUrl: root, paths: config.compilerOptions.paths,
        moduleResolution: ts.ModuleResolutionKind.Bundler,
      }, ts.sys).resolvedModule?.resolvedFileName
    },
  }],
  resolve: { alias },
  test: {
    include: [resolve(tests, 'review-probe.spec.ts')],
    pool: 'forks',
    maxWorkers: 1,
    fileParallelism: false,
    testTimeout: 12000,
    hookTimeout: 12000,
    reporters: ['default', 'json'],
    outputFile: { json: process.env.DSH_REPORT || '/logs/verifier/results.json' },
  },
}
