import { afterEach, expect, it } from 'vitest'
import { cleanup, endpoint, harness } from './support.ts'
afterEach(cleanup)
it('accepts an installed Responses model when its protocol is inherited from the catalog', async () => {
  const server = await endpoint()
  for (const enabled of [false, true]) {
    const h = await harness({ openai: {
      apiKeyEnv: 'MIGRATION_FIXTURE_KEY', baseURL: server.url,
      models: [{ id: 'gpt-4.1' }], responsesReasoningText: enabled,
    } })
    expect(await h.ctx.llm.resolveCallConfig({ provider: 'openai', model: 'gpt-4.1' })).toMatchObject({ provider: 'openai', model: 'gpt-4.1' })
  }
  expect(server.requests).toEqual([])
})
