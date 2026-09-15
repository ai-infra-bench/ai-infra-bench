import { afterEach, expect, it } from 'vitest'
import { cleanup, endpoint, completion, responseText, harness, profile, turn, migrate } from './support.ts'

afterEach(cleanup)

it('retains an explicit allowance below declared model output capacity after migration and reopen', async () => {
  const source = await endpoint(), destination = await endpoint()
  source.scripts.push(completion('Retained work.'))
  const h = await harness({
    origin: profile(source.url, 'openai-completions', 'old-model', {
      models: [{ id: 'old-model', contextWindow: 65536, maxTokens: 512 }],
    }),
    destination: profile(destination.url, 'openai-responses', 'next-model', {
      models: [{ id: 'next-model', contextWindow: 65536, maxTokens: 256 }],
    }),
  })
  const agent = h.create('work-with-explicit-cap', { maxTokens: 177 })
  await turn(h.ctx, agent, 'Retain my work and output allowance.')
  expect(agent.session.requestHeader().config.maxTokens).toBe(177)
  await migrate(h, agent)
  expect(destination.requests).toHaveLength(0)
  const reopened = await h.reopen(agent.session.snapshotEvents())
  destination.scripts.push(responseText('Continued after reopening.'))
  await turn(h.ctx, reopened, 'Continue.')
  expect(destination.requests).toHaveLength(1)
  expect(destination.requests[0].body.max_output_tokens).toBe(177)
})

it('retains an explicit allowance below declared model output capacity when an empty migrated session is reopened', async () => {
  const destination = await endpoint()
  const h = await harness({ destination: profile(destination.url, 'openai-responses', 'next-model', {
    models: [{ id: 'next-model', contextWindow: 65536, maxTokens: 256 }],
  }) })
  const agent = h.create('empty-with-explicit-cap', { maxTokens: 73 })
  expect(agent.session.requestHeader()).toBeUndefined()
  await migrate(h, agent)
  expect(destination.requests).toHaveLength(0)
  const reopened = await h.reopen(agent.session.snapshotEvents())
  destination.scripts.push(responseText('First work after reopening.'))
  await turn(h.ctx, reopened, 'Start work.')
  expect(destination.requests).toHaveLength(1)
  expect(destination.requests[0].body.max_output_tokens).toBe(73)
})

it('retains an explicit allowance below declared model output capacity for another empty session and output capacity', async () => {
  const destination = await endpoint()
  const h = await harness({ destination: profile(destination.url, 'openai-responses', 'next-model', {
    models: [{ id: 'next-model', contextWindow: 65536, maxTokens: 384 }],
  }) })
  const agent = h.create('another-empty-with-explicit-cap', { maxTokens: 91 })
  expect(agent.session.requestHeader()).toBeUndefined()
  await migrate(h, agent)
  expect(destination.requests).toHaveLength(0)
  const reopened = await h.reopen(agent.session.snapshotEvents())
  destination.scripts.push(responseText('First work after reopening.'))
  await turn(h.ctx, reopened, 'Start work.')
  expect(destination.requests).toHaveLength(1)
  expect(destination.requests[0].body.max_output_tokens).toBe(91)
})

it('rejects a caller allowance above the declared destination output capability', async () => {
  const source = await endpoint(), destination = await endpoint()
  source.scripts.push(completion('Retained work within source capability.'))
  const h = await harness({
    origin: profile(source.url, 'openai-completions', 'old-model', {
      models: [{ id: 'old-model', contextWindow: 65536, maxTokens: 256 }],
    }),
    destination: profile(destination.url, 'openai-responses', 'next-model', {
      models: [{ id: 'next-model', contextWindow: 65536, maxTokens: 64 }],
    }),
  })
  const agent = h.create('explicit-above-destination-limit', { maxTokens: 73 })
  await turn(h.ctx, agent, 'Preserve my explicit output allowance.')
  expect(agent.session.requestHeader().config.maxTokens).toBe(73)
  const before = agent.session.snapshotEvents()
  await expect(migrate(h, agent)).rejects.toThrow()
  expect(agent.session.snapshotEvents()).toEqual(before)
  expect(h.agents.selectionFor(agent).current.provider).toBe('origin')
  expect(destination.requests).toHaveLength(0)
})

it('keeps adapter defaults destination-owned through consecutive migrations and reopening', async () => {
  const source = await endpoint(), destination = await endpoint(), third = await endpoint()
  source.scripts.push(completion('Retained work.'))
  const h = await harness({
    origin: profile(source.url, 'openai-completions', 'old-model', { models: [{ id: 'old-model', contextWindow: 65536, maxTokens: 512 }] }),
    destination: profile(destination.url, 'openai-responses', 'next-model', { models: [{ id: 'next-model', contextWindow: 65536, maxTokens: 256 }] }),
    third: profile(third.url, 'openai-responses', 'third-model', { models: [{ id: 'third-model', contextWindow: 65536, maxTokens: 384 }] }),
  })
  const agent = h.create()
  await turn(h.ctx, agent, 'Keep the work.')
  await migrate(h, agent)
  await migrate(h, agent, 'third', 'third-model')
  const reopened = await h.reopen(agent.session.snapshotEvents())
  third.scripts.push(responseText('Continued.'))
  await turn(h.ctx, reopened, 'Continue after reopening.')
  expect(third.requests[0].body.max_output_tokens).toBe(384)
  await migrate(h, reopened)
  destination.scripts.push(responseText('Continued again.'))
  await turn(h.ctx, reopened, 'Continue on the earlier destination.')
  expect(destination.requests[0].body.max_output_tokens).toBe(256)
})

it.each([undefined, 73])('uses known capability without inventing a request default (caller=%s)', async caller => {
  const destination = await endpoint()
  // An installed catalog model has a capability even without a profile request default.
  // Fixed external fixture fact: gpt-4.1 in the installed pi-ai 0.84.2 catalog.
  // Do not obtain the expected capacity from candidate-private resolver helpers.
  const capacity = 32768
  expect(capacity).toBeGreaterThan(73)
  const providers = { openai: { apiKeyEnv: 'MIGRATION_FIXTURE_KEY', baseURL: destination.url, models: [{ id: 'gpt-4.1', contextWindow: capacity }] } }
  const h = await harness(providers)
  const agent = h.create('catalog-capacity', caller === undefined ? {} : { maxTokens: caller })
  const reserve = caller ?? capacity
  await h.ctx.settings.update('llm-pi-ai', { providers: { openai: { ...providers.openai, models: [{ id: 'gpt-4.1', contextWindow: reserve - 1 }] } } })
  const before = agent.session.snapshotEvents()
  await expect(migrate(h, agent, 'openai', 'gpt-4.1')).rejects.toThrow(/\S/)
  expect(agent.session.snapshotEvents()).toEqual(before)
  await h.ctx.settings.update('llm-pi-ai', { providers: { openai: { ...providers.openai, models: [{ id: 'gpt-4.1', contextWindow: reserve }] } } })
  await migrate(h, agent, 'openai', 'gpt-4.1')
  expect(destination.requests).toHaveLength(0)
  const reopened = await h.reopen(agent.session.snapshotEvents())
  // Admission covers retained work. Give the subsequent new prompt ample room.
  await h.ctx.settings.update('llm-pi-ai', { providers: { openai: { ...providers.openai, models: [{ id: 'gpt-4.1', contextWindow: 65536 }] } } })
  destination.scripts.push(responseText('First work.'))
  await turn(h.ctx, reopened, 'Start work.')
  expect(destination.requests).toHaveLength(1)
  if (caller !== undefined) expect(destination.requests[0].body.max_output_tokens).toBe(caller)
  expect(reopened.session.requestHeader().config.maxTokens).toBe(caller)
})
