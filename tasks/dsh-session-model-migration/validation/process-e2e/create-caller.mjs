/** First-process input producer only. Uses the shipped public Agent factory.
 * Removed from the second process's overlay; never supplies restored state.
 */
import { writeFile } from 'node:fs/promises'
export const inject = ['agents', 'agentPresets', 'sessionController', 'appReady']
export function apply(ctx, config) {
  ctx.appReady.onReady(() => {
    void (async () => {
      await ctx.agents.create({
        sessionId: config.sessionId,
        agentOptions: { provider: 'origin', model: 'old-model', maxTokens: config.maxTokens },
        meta: { cwd: process.cwd(), agentPreset: 'minimal' },
        setup: async agentCtx => { await ctx.agentPresets.mount(agentCtx, 'minimal') },
      })
      await writeFile(config.readyFile, JSON.stringify({ pid: process.pid, sessionId: config.sessionId }))
    })().catch(error => { console.error(error); process.exitCode = 1 })
  })
}
