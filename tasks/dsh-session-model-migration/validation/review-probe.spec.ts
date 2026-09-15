/** Independent review case: a failed second selection cannot erase a pending first selection. */
import { afterEach, expect, it } from 'vitest'
import { cleanup, endpoint, completion, responseText, harness, profile, turn, migrate } from '../tests/support.ts'
afterEach(cleanup)
it('retains a pending destination across a failed second migration and reopening', async () => {
  const source = await endpoint(), target = await endpoint()
  source.scripts.push(completion('Retained original work.'))
  const h = await harness({ origin: profile(source.url, 'openai-completions', 'old-model'), destination: profile(target.url, 'openai-responses', 'next-model', { responsesReasoningText: true }) })
  const agent = h.create()
  await turn(h.ctx, agent, 'Begin the work.')
  await migrate(h, agent)
  const selected = agent.session.snapshotEvents()
  await expect(migrate(h, agent, 'unregistered-route', 'missing')).rejects.toThrow()
  expect(agent.session.snapshotEvents()).toEqual(selected)
  const restored = await h.reopen(selected)
  target.scripts.push(responseText('Destination resumed.'))
  await turn(h.ctx, restored, 'Continue.')
  expect(target.requests).toHaveLength(1)
  expect(target.requests[0].body.model).toBe('next-model')
  expect(JSON.stringify(target.requests[0].body.input)).toContain('Retained original work.')
  expect(source.requests).toHaveLength(1)
})
