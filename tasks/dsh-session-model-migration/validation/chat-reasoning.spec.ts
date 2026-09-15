/** Additional Chat contract checks; not part of the frozen v0.0.4 score. */
import { afterEach, expect, it } from 'vitest'
import { cleanup, completion, endpoint, harness, migrate, profile, turn } from '../tests/support.ts'

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
  const { resolveProfiles } = await import('@deepseek-ai/dsh-llm-pi-ai/src/config.ts')
  expect(() => resolveProfiles({ invalid: profile('http://127.0.0.1', 'openai-responses', 'm', { chatReasoningText: true }) })).toThrow(/chatReasoningText/)
})

it('rejects a nonboolean Chat plaintext option', async () => {
  const { resolveProfiles } = await import('@deepseek-ai/dsh-llm-pi-ai/src/config.ts')
  expect(() => resolveProfiles({ invalid: profile('http://127.0.0.1', 'openai-completions', 'm', { chatReasoningText: 'false' }) })).toThrow(/chatReasoningText/)
})
