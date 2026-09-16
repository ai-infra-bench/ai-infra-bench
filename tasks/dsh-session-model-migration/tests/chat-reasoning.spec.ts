/** Chat reasoning compatibility through the real SDK and tools. */
import { afterEach, expect, it } from 'vitest'
import { cleanup, completion, endpoint, harness, migrate, profile, turn } from './support.ts'

afterEach(cleanup)

it.each([false, true])('preserves opt-in Chat reasoning through real SDK and tool continuation (enabled=%s)', async enabled => {
  const source = await endpoint(), target = await endpoint()
  source.scripts.push(
    completion('Inspecting.', [{ id: 'call.a', value: 'alpha' }, { id: 'call/a', value: 'beta' }], 'Inspect both values.'),
    completion('Source finished.', [], 'Both values are saved.'),
  )
  const h = await harness({
    origin: profile(source.url, 'openai-completions', 'old-model'),
    destination: profile(target.url, 'openai-completions', 'next-model', { chatReasoningText: enabled }),
  })
  const agent = h.create()
  await turn(h.ctx, agent, 'Record two values.')
  const before = agent.session.snapshotEvents()
  await migrate(h, agent)
  target.scripts.push(
    completion('Continuing.', [{ id: 'native_next', value: 'gamma' }], 'Save the next value.'),
    completion('Finished.'),
  )
  await turn(h.ctx, agent, 'Continue the work.')
  expect(h.recorded).toEqual(['alpha', 'beta', 'gamma'])
  for (const request of target.requests) {
    expect(request.path).toBe('/chat/completions')
    const assistants = request.body.messages.filter((m: any) => m.role === 'assistant')
    expect(assistants[0].reasoning_content).toBe(enabled ? 'Inspect both values.' : undefined)
    expect(assistants[1].reasoning_content).toBe(enabled ? 'Both values are saved.' : undefined)
    const calls = assistants.flatMap((m: any) => m.tool_calls ?? [])
    expect(new Set(calls.map((c: any) => c.id)).size).toBe(calls.length)
    for (const call of calls) {
      const result = request.body.messages.find((m: any) => m.role === 'tool' && m.tool_call_id === call.id)
      expect(result.content).toContain(`recorded:${JSON.parse(call.function.arguments).value}`)
    }
  }
  const native = target.requests[1].body.messages.find((m: any) => m.role === 'assistant' && m.tool_calls?.some((c: any) => c.id === 'native_next'))
  expect(native.reasoning_content).toBe('Save the next value.')
  expect(agent.session.snapshotEvents().slice(0, before.length)).toEqual(before)
})

it('rejects Chat plaintext replay on a Responses route', async () => {
  const server = await endpoint()
  await expect(harness({ invalid: profile(server.url, 'openai-responses', 'm', { chatReasoningText: true }) })).rejects.toThrow(/\S/)
  expect(server.requests).toEqual([])
})

it('rejects a nonboolean Chat plaintext option', async () => {
  const server = await endpoint()
  await expect(harness({ invalid: profile(server.url, 'openai-completions', 'm', { chatReasoningText: 'false' }) })).rejects.toThrow(/\S/)
  expect(server.requests).toEqual([])
})


it.each(['provider', 'model'])('preserves reasoning-only assistant on a %s change after reopen', async change => {
  const source = await endpoint(), target = await endpoint()
  const sameProvider = change === 'model'
  source.scripts.push(completion('', [], 'Retain this reasoning without fabricating an answer.'))
  const h = await harness({
    origin: profile(source.url, 'openai-completions', 'old-model', sameProvider ? {
      chatReasoningText: true,
      models: [{ id: 'old-model', contextWindow: 65536, maxTokens: 128 }, { id: 'next-model', contextWindow: 65536, maxTokens: 128 }],
    } : {}),
    destination: profile(target.url, 'openai-completions', 'next-model', { chatReasoningText: true }),
  })
  const agent = h.create()
  await turn(h.ctx, agent, 'Keep the available work.')
  const before = agent.session.snapshotEvents()
  await migrate(h, agent, sameProvider ? 'origin' : 'destination')
  const reopened = await h.reopen(agent.session.snapshotEvents())
  const server = sameProvider ? source : target
  server.scripts.push(completion('Continued.'))
  await turn(h.ctx, reopened, 'Continue after reopening.')
  const assistants = server.requests.at(-1)!.body.messages.filter((message: any) => message.role === 'assistant')
  expect(assistants).toHaveLength(1)
  expect(assistants[0].reasoning_content).toBe('Retain this reasoning without fabricating an answer.')
  expect(assistants[0].content == null || assistants[0].content === '').toBe(true)
  expect(assistants[0].tool_calls ?? []).toHaveLength(0)
  expect(reopened.session.snapshotEvents().slice(0, before.length)).toEqual(before)
})
