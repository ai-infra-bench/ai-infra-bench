/** External HTTP fixture plus real Loader, sessions, token meter, tools and agent loop. */
import { createServer } from 'node:http'
import { mkdtemp, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { Context } from '@deepseek-ai/cordis'
import Loader from '@deepseek-ai/cordis-plugin-loader'
import Include from '@deepseek-ai/cordis-plugin-include'
import LlmRuntime, { createUserMessage } from '@deepseek-ai/dsh-llm'
import * as LlmPiAi from '@deepseek-ai/dsh-llm-pi-ai'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import SessionProjectionRegistry from '@deepseek-ai/dsh-session-projection'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime, { defineContentToolFixture } from '@deepseek-ai/dsh-tools'
import AgentRegistry from '@deepseek-ai/dsh-agent'
import AgentLoop from '@deepseek-ai/dsh-agent-loop'
import AgentDefaultModel from '@deepseek-ai/dsh-agent-default-model'
import FileSettingsProvider from '@deepseek-ai/dsh-settings-file'
import TypertRegistry from '@deepseek-ai/dsh-typert-registry'
import TokenMeter from '@deepseek-ai/dsh-token-meter'
import { ApiSessionAgentController } from '@deepseek-ai/dsh-api-session-controller/src/agent.ts'
import { SessionCommandController } from '@deepseek-ai/dsh-api-session-controller/src/commands.ts'
import { installModelSelectionProjection } from '@deepseek-ai/dsh-api-session-controller/src/model-selection-projection.ts'

export const dispose: (() => Promise<unknown>)[] = []
export async function cleanup() { for (const close of dispose.splice(0).reverse()) await close() }
export async function endpoint() {
  const requests: { path: string; body: any }[] = []
  const scripts: string[][] = []
  const gates: (() => Promise<void>)[] = []
  const server = createServer(async (req, res) => {
    let body = ''; for await (const chunk of req) body += chunk
    requests.push({ path: req.url!, body: JSON.parse(body || '{}') })
    const events = scripts.shift()
    if (!events) { res.writeHead(500); res.end('unexpected provider generation'); return }
    await gates.shift()?.()
    res.writeHead(200, { 'Content-Type': 'text/event-stream' })
    for (const event of events) res.write(`data: ${event}\n\n`)
    res.end()
  })
  await new Promise<void>(r => server.listen(0, '127.0.0.1', r))
  dispose.push(async () => { server.closeAllConnections(); await new Promise<void>(r => server.close(() => r())) })
  return { requests, scripts, gates, url: `http://127.0.0.1:${(server.address() as any).port}` }
}
export function completion(text: string, calls: { id: string; value: string }[] = [], reasoning?: string) {
  const deltas: any[] = [{ role: 'assistant', content: '' }]
  if (reasoning) deltas.push({ reasoning_content: reasoning })
  if (text) deltas.push({ content: text })
  if (calls.length) deltas.push({ tool_calls: calls.map((c, index) => ({ index, id: c.id, type: 'function', function: { name: 'record_value', arguments: JSON.stringify({ value: c.value }) } })) })
  return [...deltas.map(delta => JSON.stringify({ choices: [{ index: 0, delta, finish_reason: null }] })), JSON.stringify({ choices: [{ index: 0, delta: {}, finish_reason: calls.length ? 'tool_calls' : 'stop' }], usage: { prompt_tokens: 11, completion_tokens: 7 } }), '[DONE]']
}
export function responses(items: any[]) {
  const response = { id: 'resp_destination_native', model: 'next-model', status: 'completed', output: items, usage: { input_tokens: 13, output_tokens: 9, total_tokens: 22 } }
  return [JSON.stringify({ type: 'response.created', response: { ...response, status: 'in_progress', output: [] } }), ...items.flatMap((item, output_index) => [JSON.stringify({ type: 'response.output_item.added', output_index, item }), JSON.stringify({ type: 'response.output_item.done', output_index, item })]), JSON.stringify({ type: 'response.completed', response })]
}
export const responseText = (text: string) => responses([{ type: 'message', id: 'msg_destination', role: 'assistant', status: 'completed', content: [{ type: 'output_text', text, annotations: [] }] }])

export async function harness(providers: Record<string, any>) {
  const root = await mkdtemp(join(tmpdir(), 'migration-'))
  dispose.push(() => rm(root, { recursive: true, force: true }))
  const settings = join(root, 'settings.yaml')
  await writeFile(settings, '{}\n')
  process.env.MIGRATION_FIXTURE_KEY = 'local-test-key'
  const modules = new Map<string, any>([
    ['typert', TypertRegistry], ['llm', LlmRuntime], ['settings', FileSettingsProvider], ['sessions', SessionStore],
    ['projection', SessionProjectionRegistry], ['meter', TokenMeter], ['prompt', SystemPrompt],
    ['tools', ToolRuntime], ['agents', AgentRegistry], ['loop', AgentLoop],
    ['default-model', AgentDefaultModel], ['pi', LlmPiAi],
  ])
  const config: Record<string, any> = {
    settings: { path: settings }, prompt: { persona: 'Retain the work and use record_value when requested.' },
    loop: { agents: [] }, 'default-model': { provider: 'origin', model: 'old-model' }, pi: { providers },
  }
  const configPath = join(root, 'cordis.yml')
  await writeFile(configPath, JSON.stringify([...modules.keys()].map(name => ({ id: name, name, ...(config[name] ? { config: config[name] } : {}) }))))
  const ctx = new Context()
  dispose.push(() => ctx.fiber.dispose())
  ctx.baseUrl = pathToFileURL(root).href + '/'
  await ctx.plugin(Loader)
  ctx.loader.builtins.include = Include
  ctx.loader.internal = { version: 'v2', async import(name: string) { if (!modules.has(name)) throw new Error(name); return modules.get(name) } } as any
  await ctx.loader.create({ name: 'cordis:include', config: { path: pathToFileURL(configPath).href } })
  await ctx.loader.await()
  installModelSelectionProjection(ctx)
  const agents = new ApiSessionAgentController(ctx)
  const commands = new SessionCommandController(ctx, agents, root)
  const recorded: string[] = []
  ctx.tools.register(defineContentToolFixture({
    name: 'record_value', description: 'Write an observed value to the work file.',
    parameters: { value: { type: 'string' } },
    async execute(args: any) {
      recorded.push(args.value)
      await writeFile(join(root, 'work.txt'), recorded.join('\n'))
      return [{ type: 'text', text: `recorded:${args.value}` }]
    },
  }))
  const create = (id = 'main', options: any = {}) => {
    const agent = ctx.agentLoop.create(SessionId(id), { provider: 'origin', model: 'old-model', ...options })
    agents.selectionFor(agent)
    return agent
  }
  const reopen = async (events: any[]) => {
    const handle = await ctx.agents.create({ sessionId: SessionId('restored'), seed: JSON.parse(JSON.stringify(events)), agentOptions: { provider: 'origin', model: 'old-model' } })
    const agent = ctx.agents.get(SessionId('restored'))!
    agents.selectionFor(agent)
    return agent
  }
  return { ctx, commands, agents, root, settings, recorded, create, reopen }
}
export function profile(url: string, api: string, model: string, extra: any = {}) {
  return { apiKeyEnv: 'MIGRATION_FIXTURE_KEY', baseURL: url, api, models: [{ id: model, contextWindow: 65536, maxTokens: 128 }], ...extra }
}
export async function turn(ctx: Context, agent: any, text: string) {
  const idle = new Promise<void>(r => { const off = ctx.on('agent/status', ({ agent: subject, status }: any) => { if (subject === agent && status === 'idle') { off(); r() } }) })
  agent.followup(createUserMessage({ content: [{ type: 'text', text }], source: { kind: 'user' } }))
  await idle
}
export async function migrate(h: Awaited<ReturnType<typeof harness>>, agent: any, provider = 'destination', model = 'next-model') {
  return h.commands.selectModel({ sessionId: agent.session.id, provider, model, migration: 'checked' } as any)
}
