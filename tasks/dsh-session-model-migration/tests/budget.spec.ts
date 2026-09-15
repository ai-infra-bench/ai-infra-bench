import { afterEach, describe, expect, it, vi } from 'vitest'
import { LlmAdapter, createUserMessage } from '@deepseek-ai/dsh-llm'
import { PiAiAdapter } from '@deepseek-ai/dsh-llm-pi-ai'
import { cleanup, endpoint, completion, responseText, harness, profile, turn, migrate } from './support.ts'

afterEach(async () => { vi.restoreAllMocks(); await cleanup() })

// Absence is the existing adapter contract for unknown metadata. Positive
// capacity cases below resolve actual pi-ai profiles through the Loader.
class UnknownCatalog extends LlmAdapter {
  constructor(readonly windowKnown: boolean) { super() }
  async resolveModel(provider: string, model: string) {
    return { provider, id: model, name: model, ...(this.windowKnown ? { context: { contextWindow: 65536 } } : {}), defaultMaxTokens: 32 }
  }
  async *stream(): AsyncIterable<any> { throw new Error('admission must not generate') }
}
async function setup(options = {}) {
  const origin = await endpoint(), destination = await endpoint()
  origin.scripts.push(completion('Reasonably long retained work. '.repeat(60)))
  const providers = {
    origin: profile(origin.url, 'openai-completions', 'old-model', { models: [{ id: 'old-model', contextWindow: 65536, maxTokens: 512 }] }),
    destination: profile(destination.url, 'openai-responses', 'next-model', { models: [{ id: 'next-model', contextWindow: 65536, maxTokens: 256 }] }),
  }
  const h = await harness(providers), agent = h.create('main', options)
  await turn(h.ctx, agent, 'Retain the complete observations and tool definitions.')
  const resize = async (window: number, output = 256) => {
    providers.destination = profile(destination.url, 'openai-responses', 'next-model', { models: [{ id: 'next-model', contextWindow: window, maxTokens: output }] })
    await h.ctx.settings.update('llm-pi-ai', { providers })
  }
  return { h, agent, destination, origin, resize }
}
function estimate(h: any, agent: any, maxTokens = 256) {
  const previous = agent.session.requestHeader()
  return h.ctx.tokenMeter.measure(agent.session, { ...previous, config: { ...previous.config, provider: 'destination', model: 'next-model', maxTokens } }).totalTokens
}

describe('destination budget and admission', () => {
  it('allows exact fit, reprices history and tools, and checks an already selected route again', async () => {
    const { h, agent, destination, resize } = await setup()
    const input = estimate(h, agent)
    expect(input).toBeGreaterThan(400)
    const headerless = h.ctx.tokenMeter.measure(agent.session, { config: { provider: 'destination', model: 'next-model', maxTokens: 256 } }).totalTokens
    expect(input).toBeGreaterThan(headerless)
    await resize(input + 255)
    const before = agent.session.snapshotEvents()
    await expect(migrate(h, agent)).rejects.toThrow(/\S/)
    expect(agent.session.snapshotEvents()).toEqual(before)
    await resize(input + 256)
    await migrate(h, agent)
    expect(h.agents.selectionFor(agent).current.provider).toBe('destination')
    const selected = agent.session.snapshotEvents()
    await resize(input + 255)
    await expect(migrate(h, agent)).rejects.toThrow(/\S/)
    expect(agent.session.snapshotEvents()).toEqual(selected)
    expect(destination.requests).toHaveLength(0)
  })

  it('replaces the old adapter output default with the destination default after reopen', async () => {
    const { h, agent, destination, resize } = await setup()
    expect(agent.session.requestHeader().adapterDefaults.maxTokens).toBe(true)
    await resize(estimate(h, agent) + 256)
    await migrate(h, agent)
    const reopened = await h.reopen(agent.session.snapshotEvents())
    await resize(65536)
    destination.scripts.push(responseText('Continued.'))
    await turn(h.ctx, reopened, 'Continue.')
    expect(destination.requests).toHaveLength(1)
    expect(destination.requests[0].body.max_output_tokens).toBe(256)
  })

  it('retains an explicit output allowance through admission and continuation', async () => {
    const { h, agent, destination, resize } = await setup({ maxTokens: 177 })
    const input = estimate(h, agent, 177)
    await resize(input + 176)
    await expect(migrate(h, agent)).rejects.toThrow(/\S/)
    await resize(input + 177)
    await migrate(h, agent)
    await resize(65536)
    destination.scripts.push(responseText('Continued.'))
    await turn(h.ctx, agent, 'Continue.')
    expect(destination.requests[0].body.max_output_tokens).toBe(177)
  })

  it.each([false, true])('refuses unknown output capacity even with a caller allowance (window known=%s)', async windowKnown => {
    const h = await harness({})
    h.ctx.llm.registerAdapter(['destination'], new UnknownCatalog(windowKnown))
    const agent = h.create('unknown-capacity', { maxTokens: 19 })
    const before = agent.session.snapshotEvents()
    await expect(migrate(h, agent)).rejects.toThrow(/\S/)
    expect(agent.session.snapshotEvents()).toEqual(before)
  })

  it('admits an empty session at a window equal to its output allowance', async () => {
    const destination = await endpoint()
    const h = await harness({ destination: profile(destination.url, 'openai-responses', 'next-model', { models: [{ id: 'next-model', contextWindow: 32, maxTokens: 32 }] }) })
    const agent = h.create()
    await migrate(h, agent)
    expect(h.agents.selectionFor(agent).current.provider).toBe('destination')
    expect(destination.requests).toHaveLength(0)
  })

  it('rejects queued input without consuming or rewriting it', async () => {
    const { h, agent, destination } = await setup()
    agent.inbox.append('next-step', createUserMessage({ content: [{ type: 'text', text: 'pending work' }], source: { kind: 'user' } }))
    const before = agent.session.snapshotEvents()
    await expect(migrate(h, agent)).rejects.toThrow(/\S/)
    expect(agent.session.snapshotEvents()).toEqual(before)
    expect(agent.inbox.nextStep).toHaveLength(1)
    expect(destination.requests).toHaveLength(0)
  })

  it('rejects stale checks when the session changes during catalog lookup', async () => {
    const { h, agent } = await setup()
    const entered = Promise.withResolvers<void>(), release = Promise.withResolvers<void>()
    // Delay the existing adapter boundary; keep actual metadata resolution intact.
    for (const method of ['prepareCall', 'resolveModel'] as const) {
      const original = PiAiAdapter.prototype[method]
      vi.spyOn(PiAiAdapter.prototype, method).mockImplementation(async function (this: PiAiAdapter, ...args: any[]) {
        entered.resolve(); await release.promise
        return original.apply(this, args as any)
      } as any)
    }
    const checking = migrate(h, agent)
    const rejected = expect(checking).rejects.toThrow(/\S/)
    await entered.promise
    agent.inbox.append('next-step', createUserMessage({ content: [{ type: 'text', text: 'briefly queued' }], source: { kind: 'user' } }))
    agent.inbox.clear()
    const changed = agent.session.snapshotEvents()
    release.resolve()
    await rejected
    expect(agent.session.snapshotEvents()).toEqual(changed)
    expect(h.agents.selectionFor(agent).current.provider).toBe('origin')
  })

  it('refuses migration during an active generation with no queued input', async () => {
    const { h, agent, destination } = await setup()
    await migrate(h, agent)
    const entered = Promise.withResolvers<void>(), release = Promise.withResolvers<void>()
    destination.gates.push(async () => { entered.resolve(); await release.promise })
    destination.scripts.push(responseText('Continued.'))
    const running = turn(h.ctx, agent, 'Keep working.')
    await entered.promise
    expect(agent.status).toBe('running')
    expect(agent.inbox.hasPending).toBe(false)
    const before = agent.session.snapshotEvents()
    try {
      await expect(migrate(h, agent)).rejects.toThrow(/\S/)
      expect(agent.session.snapshotEvents()).toEqual(before)
    } finally { release.resolve(); await running }
    expect(destination.requests).toHaveLength(1)
  })

  it('keeps legacy selection permissive and saves its deployment default', async () => {
    const { h, agent, resize } = await setup()
    await resize(1)
    await h.commands.selectModel({ sessionId: agent.session.id, provider: 'destination', model: 'next-model' })
    expect(h.agents.selectionFor(agent).current.provider).toBe('destination')
    expect(h.ctx.agentDefaultModel.currentSelection().provider).toBe('destination')
  })
})
