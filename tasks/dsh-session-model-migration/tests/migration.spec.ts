import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, endpoint, completion, responseText, responses, harness, profile, turn, migrate } from './support.ts'

afterEach(cleanup)

describe('checked session migration', () => {
  it('continues real tool work across protocols and after durable reopen', async () => {
    const origin = await endpoint(), destination = await endpoint()
    origin.scripts.push(completion('Checking two values.', [{ id: 'old/a|fc_secret_A', value: 'alpha' }, { id: 'old?b|fc_secret_B', value: 'beta' }], 'I need both independent observations.'), completion('Both values are saved.'))
    const h = await harness({ origin: profile(origin.url, 'openai-completions', 'old-model'), destination: profile(destination.url, 'openai-responses', 'next-model', { responsesReasoningText: true }) })
    const agent = h.create(), sibling = h.create('sibling')
    await turn(h.ctx, agent, 'Record alpha and beta.')
    expect(h.recorded).toEqual(['alpha', 'beta'])
    const before = agent.session.snapshotEvents()
    const settingsBefore = await readFile(h.settings, 'utf8')
    await migrate(h, agent)
    expect(destination.requests).toHaveLength(0)
    expect(agent.session.snapshotEvents().slice(0, before.length)).toEqual(before)
    expect(h.ctx.agentDefaultModel.currentSelection()).toEqual({ provider: 'origin', model: 'old-model' })
    expect(await readFile(h.settings, 'utf8')).toBe(settingsBefore)
    expect(h.agents.selectionFor(sibling).current.provider).toBe('origin')
    const restored = await h.reopen(agent.session.snapshotEvents())
    destination.scripts.push(responses([
      { type: 'reasoning', id: 'rs_destination', summary: [{ type: 'summary_text', text: 'Continue the recorded work.' }], encrypted_content: 'destination-opaque-state' },
      { type: 'function_call', id: 'fc_destination', call_id: 'call_next', name: 'record_value', arguments: '{"value":"gamma"}', status: 'completed' },
    ]), responseText('All three values are saved.'))
    await turn(h.ctx, restored, 'Continue by recording gamma.')
    expect(h.recorded).toEqual(['alpha', 'beta', 'gamma'])
    expect(await readFile(join(h.root, 'work.txt'), 'utf8')).toBe('alpha\nbeta\ngamma')
    expect(origin.requests).toHaveLength(2)
    expect(destination.requests.map(r => r.path)).toEqual(['/responses', '/responses'])
    const payload = destination.requests[0].body
    expect(payload.model).toBe('next-model')
    const items = payload.input
    const reasonIndex = items.findIndex((i: any) => i.type === 'reasoning')
    expect(items[reasonIndex]).toMatchObject({ type: 'reasoning', content: [{ type: 'reasoning_text', text: 'I need both independent observations.' }] })
    const calls = items.filter((i: any) => i.type === 'function_call')
    const results = items.filter((i: any) => i.type === 'function_call_output')
    expect(calls).toHaveLength(2)
    expect(new Set(calls.map((c: any) => c.call_id)).size).toBe(2)
    for (const call of calls) {
      expect(items.indexOf(call)).toBeGreaterThan(reasonIndex)
      expect(results.find((r: any) => r.call_id === call.call_id)?.output).toContain(`recorded:${JSON.parse(call.arguments).value}`)
    }
    for (const item of items) {
      expect(['fc_secret_A', 'fc_secret_B']).not.toContain(item.id)
      expect(item.encrypted_content).toBeUndefined()
      expect(item.signature).toBeUndefined()
    }
    const followup = destination.requests[1].body.input
    expect(followup.find((i: any) => i.type === 'function_call_output' && i.call_id === 'call_next')?.output).toContain('recorded:gamma')
    expect(followup.find((i: any) => i.id === 'rs_destination')?.encrypted_content).toBe('destination-opaque-state')
    expect(restored.session.requestHeader().config.provider).toBe('destination')
    expect(restored.session.snapshotEvents().slice(0, before.length)).toEqual(before)
  })

  it('rejects insufficient capacity without damaging the old route', async () => {
    const origin = await endpoint(), destination = await endpoint()
    origin.scripts.push(completion('A long retained observation. '.repeat(80)))
    const h = await harness({ origin: profile(origin.url, 'openai-completions', 'old-model'), destination: profile(destination.url, 'openai-responses', 'next-model', { models: [{ id: 'next-model', contextWindow: 150, maxTokens: 128 }] }) })
    const agent = h.create()
    await turn(h.ctx, agent, 'Keep the observations.')
    const before = agent.session.snapshotEvents(), settingsBefore = await readFile(h.settings, 'utf8')
    await expect(migrate(h, agent)).rejects.toThrow(/\S/)
    expect(agent.session.snapshotEvents()).toEqual(before)
    expect(await readFile(h.settings, 'utf8')).toBe(settingsBefore)
    expect(destination.requests).toHaveLength(0)
    expect(h.agents.selectionFor(agent).current.provider).toBe('origin')
    origin.scripts.push(completion('The original session still works.'))
    await turn(h.ctx, agent, 'Continue here.')
    expect(origin.requests).toHaveLength(2)
    expect(agent.session.requestHeader().config.provider).toBe('origin')
  })
})
