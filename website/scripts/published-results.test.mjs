import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { MODEL_COLORS } from '../app/lib/leaderboard-chart.ts';

const snapshot = JSON.parse(await readFile(new URL('../app/generated/leaderboard.json', import.meta.url), 'utf8'));

test('published results contain measured configurations with reconciled task totals', () => {
  assert.equal(snapshot.release.configurationCount, snapshot.configurations.length);
  let validTrials = 0;
  for (const configuration of snapshot.configurations) {
    assert.doesNotMatch(configuration.model, /mock|synthetic|simulated/i);
    assert.equal(configuration.synthetic, undefined);
    assert.ok(Object.hasOwn(MODEL_COLORS, configuration.model), 'Register a stable colour for each published model');
    assert.equal(configuration.tasks.length, snapshot.release.taskCount);
    const attempts = configuration.tasks.reduce((sum, task) => sum + task.attempts, 0);
    const passes = configuration.tasks.reduce((sum, task) => sum + task.passes, 0);
    assert.equal(configuration.metrics.validTrials, attempts);
    assert.equal(configuration.metrics.passedTrials, passes);
    assert.ok(attempts > 0);
    assert.ok(Math.abs(configuration.metrics.passAverage - 100 * passes / attempts) <= 0.0051);
    for (const task of configuration.tasks) {
      assert.ok(Number.isInteger(task.attempts) && task.attempts >= 0 && task.attempts <= snapshot.release.expectedAttempts);
      assert.ok(Number.isInteger(task.passes) && task.passes >= 0 && task.passes <= task.attempts);
    }
    validTrials += attempts;
  }
  assert.equal(snapshot.release.validTrials, validTrials);
});
