import { afterEach, expect, it } from 'vitest'
import { cleanup, endpoint, completion, responseText, harness, profile, turn, migrate } from './support.ts'
afterEach(cleanup)
it.each([
  { label: 'two shared prefixes', ids: ['shared|opaque_a', 'shared|opaque_b'] },
  { label: 'three calls with mixed prefixes', ids: ['same|item_a', 'independent|item_b', 'same|item_c'] },
  { label: 'long_prefix', ids: ['call_' + 'x'.repeat(70) + 'a', 'call_' + 'x'.repeat(70) + 'b'] },
  { label: 'punctuation', ids: ['call.alpha', 'call/alpha'] },
  { label: 'named_route', ids: ['shared|item_a', 'shared|item_b'], provider: 'openai' },
  { label: 'ordinary', ids: ['call_alpha', 'call_beta'] },
])('keeps distinct tool calls paired: $label', async ({ ids, provider = 'destination' }) => {
  const source = await endpoint(), destination = await endpoint()
  const values = ids.map((_, i) => `value-${i}`)
  source.scripts.push(completion('Inspect independent values.', ids.map((id, i) => ({ id, value: values[i] })), 'All observations matter.'), completion('Saved.'))
  const h = await harness({
    origin: profile(source.url, 'openai-completions', 'old-model'),
    [provider]: profile(destination.url, 'openai-responses', 'next-model', { responsesReasoningText: true }),
  })
  const agent = h.create()
  await turn(h.ctx, agent, 'Record the independent values.')
  expect(h.recorded).toEqual(values)
  const saved = agent.session.snapshotEvents()
  await migrate(h, agent, provider)
  expect(destination.requests).toHaveLength(0)
  destination.scripts.push(responseText('Reviewed.'))
  await turn(h.ctx, agent, 'Review retained work.')
  const input = destination.requests[0].body.input
  const calls = input.filter((i: any) => i.type === 'function_call')
  const results = input.filter((i: any) => i.type === 'function_call_output')
  expect(calls).toHaveLength(ids.length)
  expect(new Set(calls.map((i: any) => i.call_id)).size).toBe(ids.length)
  expect(results).toHaveLength(ids.length)
  for (const call of calls) {
    const matched = results.filter((i: any) => i.call_id === call.call_id)
    expect(matched).toHaveLength(1)
    expect(matched[0].output).toContain(`recorded:${JSON.parse(call.arguments).value}`)
  }
  expect(agent.session.snapshotEvents().slice(0, saved.length)).toEqual(saved)
})
