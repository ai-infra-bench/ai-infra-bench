import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, endpoint, responses, responseText, harness, profile, turn, migrate } from './support.ts'

afterEach(cleanup)
const history = (reasoning: boolean) => [
  ...(reasoning ? [{ type: 'reasoning', id: 'rs_origin_a', summary: [{ type: 'summary_text', text: 'First inspect alpha.' }], encrypted_content: 'opaque-origin-a' }] : []),
  { type: 'message', id: 'msg_origin_private', role: 'assistant', status: 'completed', content: [{ type: 'output_text', text: 'Inspecting both.', annotations: [] }] },
  { type: 'function_call', id: 'fc_origin_a', call_id: 'call_origin_a', name: 'record_value', arguments: '{"value":"alpha"}', status: 'completed' },
  ...(reasoning ? [{ type: 'reasoning', id: 'rs_origin_b', summary: [{ type: 'summary_text', text: 'Then inspect beta.' }], encrypted_content: 'opaque-origin-b' }] : []),
  { type: 'function_call', id: 'fc_origin_b', call_id: 'call_origin_b', name: 'record_value', arguments: '{"value":"beta"}', status: 'completed' },
]

describe('Responses reasoning compatibility', () => {
  it.each(['provider', 'model'])('preserves ordered plaintext while discarding foreign native state on a %s change', async change => {
    const source = await endpoint(), target = await endpoint()
    source.scripts.push(responses(history(true)), responseText('Source work complete.'))
    const sameProvider = change === 'model'
    const h = await harness({
      origin: profile(source.url, 'openai-responses', 'old-model', sameProvider ? { responsesReasoningText: true, models: [{ id: 'old-model', contextWindow: 65536, maxTokens: 128 }, { id: 'next-model', contextWindow: 65536, maxTokens: 128 }] } : {}),
      destination: profile(target.url, 'openai-responses', 'next-model', { responsesReasoningText: true }),
    })
    const agent = h.create()
    await turn(h.ctx, agent, 'Record two values.')
    expect(h.recorded).toEqual(['alpha', 'beta'])
    // Native replay must already retain the original opaque data before migration.
    expect(JSON.stringify(source.requests[1].body.input)).toContain('opaque-origin-a')
    const before = agent.session.snapshotEvents()
    await migrate(h, agent, sameProvider ? 'origin' : 'destination')
    const server = sameProvider ? source : target
    server.scripts.push(responseText('Continued on the selected model.'))
    await turn(h.ctx, agent, 'Review the retained work.')
    const input = server.requests.at(-1)!.body.input
    const meaningful = input.filter((i: any) => i.type === 'reasoning' || i.type === 'function_call' || (i.type === 'message' && i.role === 'assistant' && JSON.stringify(i).includes('Inspecting both.')))
    expect(meaningful.map((i: any) => i.type)).toEqual(['reasoning', 'message', 'function_call', 'reasoning', 'function_call'])
    expect(meaningful[0]).toMatchObject({ type: 'reasoning', content: [{ type: 'reasoning_text', text: 'First inspect alpha.' }] })
    expect(meaningful[3]).toMatchObject({ type: 'reasoning', content: [{ type: 'reasoning_text', text: 'Then inspect beta.' }] })
    for (const item of input) {
      expect(['rs_origin_a', 'rs_origin_b', 'fc_origin_a', 'fc_origin_b', 'msg_origin_private']).not.toContain(item.id)
      expect(item.encrypted_content).toBeUndefined()
      expect(item.signature).toBeUndefined()
    }
    expect(JSON.stringify(input)).not.toContain('opaque-origin-')
    for (const call of input.filter((i: any) => i.type === 'function_call')) expect(input.find((i: any) => i.type === 'function_call_output' && i.call_id === call.call_id)?.output).toContain(`recorded:${JSON.parse(call.arguments).value}`)
    expect(agent.session.snapshotEvents().slice(0, before.length)).toEqual(before)
  })

  it.each([false, true])('does not invent unavailable reasoning (enabled=%s)', async enabled => {
    const source = await endpoint(), target = await endpoint()
    source.scripts.push(responses(history(false)), responseText('Saved.'))
    const h = await harness({ origin: profile(source.url, 'openai-responses', 'old-model'), destination: profile(target.url, 'openai-responses', 'next-model', { responsesReasoningText: enabled }) })
    const agent = h.create(); await turn(h.ctx, agent, 'Record two values.'); await migrate(h, agent)
    target.scripts.push(responseText('Continued.')); await turn(h.ctx, agent, 'Continue.')
    const input = target.requests[0].body.input
    expect(input.filter((i: any) => i.type === 'reasoning')).toHaveLength(0)
    expect(input.filter((i: any) => i.type === 'function_call')).toHaveLength(2)
  })

  it('keeps non-opted-in cross-route serialization unchanged', async () => {
    const source = await endpoint(), target = await endpoint()
    source.scripts.push(responses(history(true)), responseText('Saved.'))
    const h = await harness({ origin: profile(source.url, 'openai-responses', 'old-model'), destination: profile(target.url, 'openai-responses', 'next-model') })
    const agent = h.create(); await turn(h.ctx, agent, 'Record two values.'); await migrate(h, agent)
    target.scripts.push(responseText('Continued.')); await turn(h.ctx, agent, 'Continue.')
    const input = target.requests[0].body.input
    expect(input.filter((i: any) => i.type === 'reasoning')).toHaveLength(0)
    expect(JSON.stringify(input)).toContain('First inspect alpha.')
    expect(JSON.stringify(input)).not.toContain('opaque-origin-a')
  })

  it('rejects a plaintext reasoning option on a non-Responses provider', async () => {
    const server = await endpoint()
    await expect(harness({ invalid: profile(server.url, 'openai-completions', 'm', { responsesReasoningText: true }) })).rejects.toThrow(/\S/)
    expect(server.requests).toEqual([])
  })
})
