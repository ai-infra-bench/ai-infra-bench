import test from 'node:test';
import assert from 'node:assert/strict';
import { MODEL_COLORS, modelColor } from '../app/lib/leaderboard-chart.ts';

test('published model colours are literal data encodings, not theme tokens', () => {
  assert.equal(modelColor('gpt-6-astra'), '#3d657c');
  assert.equal(modelColor('gpt-5.6-sol'), '#a16454');
  assert.equal(new Set(Object.values(MODEL_COLORS)).size, Object.keys(MODEL_COLORS).length);
  for (const colour of Object.values(MODEL_COLORS)) assert.match(colour, /^#[0-9a-f]{6}$/i);
});
test('adding, hiding and sorting configurations cannot change existing colours', () => {
  const models = Object.keys(MODEL_COLORS);
  const before = Object.fromEntries(models.map(model => [model, modelColor(model)]));
  for (const model of ['future-model-for-test', ...models.toReversed(), 'other-model-for-test']) {
    if (Object.hasOwn(before, model)) assert.equal(modelColor(model), before[model]);
  }
  assert.equal(modelColor('future-model-for-test'), modelColor('future-model-for-test'));
});
