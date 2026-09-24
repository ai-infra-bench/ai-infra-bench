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
    assert.ok(snapshot.release.batches.some(batch => batch.label === configuration.batchLabel));
    assert.equal(configuration.tasks.length, snapshot.release.taskCount);
    const attempts = configuration.tasks.reduce((sum, task) => sum + task.attempts, 0);
    const passes = configuration.tasks.reduce((sum, task) => sum + task.passes, 0);
    assert.equal(configuration.metrics.validTrials, attempts);
    assert.ok(configuration.metrics.costObservedTrials > 0);
    assert.ok(configuration.metrics.costObservedTrials <= attempts);
    if (configuration.metrics.costObservedTrials < attempts) assert.equal(configuration.metrics.passesPer100Usd, null);
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

test('the nine certified Sep 24 configurations appear alongside the retained old batch', () => {
  const expected = new Map([
    ['gpt-6-sol--xhigh--codex--0.156.1', 47],
    ['gpt-6-sol--high--codex--0.156.1', 42],
    ['gpt-6-sol--medium--codex--0.156.1', 36],
    ['gpt-6-sol--low--codex--0.156.1', 31],
    ['gpt-6-luna--xhigh--codex--0.156.1', 29],
    ['gpt-6-luna--high--codex--0.156.1', 24],
    ['gpt-6-luna--medium--codex--0.156.1', 14],
    ['gpt-6-luna--low--codex--0.156.1', 4],
    ['deepseek-flash--default--claude-code--2.1.278', 29],
  ]);
  const current = snapshot.configurations.filter(configuration => configuration.batchLabel === 'Sep 24');
  assert.equal(current.length, expected.size);
  assert.equal(snapshot.configurations.filter(configuration => configuration.batchLabel === 'Sep 08').length, 8);
  for (const configuration of current) {
    assert.equal(configuration.status, 'complete');
    assert.equal(configuration.metrics.validTrials, 68);
    assert.equal(configuration.metrics.passedTrials, expected.get(configuration.id));
  }
  const deepseek = current.find(configuration => configuration.model === 'deepseek-flash');
  assert.equal(deepseek.metrics.costObservedTrials, 67);
  assert.equal(deepseek.metrics.passesPer100Usd, null);
  assert.equal(snapshot.exclusions.trials.filter(trial => trial.model === 'deepseek-flash').length, 5);
});
