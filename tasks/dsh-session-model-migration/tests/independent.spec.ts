import { afterEach, expect, it } from 'vitest'
import { cleanup, endpoint, completion, responseText, responses, harness, profile, turn, migrate } from './support.ts'

afterEach(cleanup)

it('reprices a retained conversation instead of reusing high source usage', async () => {
  const source = await endpoint(), destination = await endpoint()
  const events = completion('A retained observation that fits the destination.')
  const last = JSON.parse(events.at(-2)!)
  last.usage = { prompt_tokens: 4096, completion_tokens: 32 }
  events[events.length - 2] = JSON.stringify(last)
  source.scripts.push(events)
  const providers = {
    origin: profile(source.url, 'openai-completions', 'old-model'),
    destination: profile(destination.url, 'openai-responses', 'next-model'),
  }
  const h = await harness(providers), agent = h.create()
  await turn(h.ctx, agent, 'Keep this observation.')
  const header = agent.session.requestHeader()
  const sourceTokens = h.ctx.tokenMeter.measure(agent.session, header).totalTokens
  const destinationTokens = h.ctx.tokenMeter.measure(agent.session, {
    ...header, config: { ...header.config, provider: 'destination', model: 'next-model' },
  }).totalTokens
  expect(sourceTokens).toBeGreaterThan(destinationTokens + 128)
  await h.ctx.settings.update('llm-pi-ai', { providers: {
    ...providers,
    destination: profile(destination.url, 'openai-responses', 'next-model', {
      models: [{ id: 'next-model', contextWindow: destinationTokens + 128, maxTokens: 128 }],
    }),
  } })
  const before = agent.session.snapshotEvents()
  await migrate(h, agent)
  expect(destination.requests).toEqual([])
  expect(agent.session.snapshotEvents().slice(0, before.length)).toEqual(before)
})

it('carries Responses-only reasoning into Chat after reopening', async () => {
  const source = await endpoint(), destination = await endpoint()
  source.scripts.push(responses([
    { type: 'reasoning', id: 'rs_source_only', summary: [{ type: 'summary_text', text: 'Check the provenance before continuing.' }], encrypted_content: 'source-private-state' },
  ]))
  const h = await harness({
    origin: profile(source.url, 'openai-responses', 'old-model'),
    destination: profile(destination.url, 'openai-completions', 'next-model', { chatReasoningText: true }),
  })
  const agent = h.create()
  await turn(h.ctx, agent, 'Think about the retained evidence.')
  const before = agent.session.snapshotEvents()
  await migrate(h, agent)
  const reopened = await h.reopen(agent.session.snapshotEvents())
  destination.scripts.push(completion('Continued.'))
  await turn(h.ctx, reopened, 'Continue.')
  const body = destination.requests[0].body
  const assistant = body.messages.filter((m: any) => m.role === 'assistant')
  expect(assistant).toHaveLength(1)
  expect(assistant[0].reasoning_content).toBe('Check the provenance before continuing.')
  expect(JSON.stringify(body)).not.toContain('source-private-state')
  expect(reopened.session.snapshotEvents().slice(0, before.length)).toEqual(before)
})

it('restores source-native replay after a round trip through another provider', async () => {
  const source = await endpoint(), destination = await endpoint()
  source.scripts.push(responses([
    { type: 'reasoning', id: 'rs_return_home', summary: [{ type: 'summary_text', text: 'Inspect the original value.' }], encrypted_content: 'native-return-state' },
    { type: 'function_call', id: 'fc_return_home', call_id: 'call_return_home', name: 'record_value', arguments: '{"value":"alpha"}', status: 'completed' },
  ]), responseText('Saved on source.'))
  const h = await harness({
    origin: profile(source.url, 'openai-responses', 'old-model', { responsesReasoningText: true }),
    destination: profile(destination.url, 'openai-responses', 'next-model', { responsesReasoningText: true }),
  })
  const agent = h.create()
  await turn(h.ctx, agent, 'Inspect alpha.')
  const before = agent.session.snapshotEvents()
  await migrate(h, agent)
  destination.scripts.push(responseText('Reviewed away from source.'))
  await turn(h.ctx, agent, 'Review the work.')
  await migrate(h, agent, 'origin', 'old-model')
  const reopened = await h.reopen(agent.session.snapshotEvents())
  source.scripts.push(responseText('Continued at home.'))
  await turn(h.ctx, reopened, 'Continue at the original provider.')
  const input = source.requests.at(-1)!.body.input
  expect(input.find((i: any) => i.id === 'rs_return_home')?.encrypted_content).toBe('native-return-state')
  expect(input.find((i: any) => i.id === 'fc_return_home')?.call_id).toBe('call_return_home')
  expect(input.find((i: any) => i.type === 'function_call_output' && i.call_id === 'call_return_home')?.output).toContain('recorded:alpha')
  expect(reopened.session.snapshotEvents().slice(0, before.length)).toEqual(before)
})
