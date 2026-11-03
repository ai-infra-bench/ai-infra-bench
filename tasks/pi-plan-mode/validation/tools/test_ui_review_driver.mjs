import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readReview, navigateReview } from '../../tests/ui_review_driver.mjs';

for (const wrap of [false, true]) {
  for (const initial of [0, 1, 2]) {
    test(`navigate ${wrap ? 'wrap' : 'clamp'} from ${initial}, reordered decorated labels`, async () => {
      const actions = ['Refine', 'Execute', 'Stay'];
      let selected = initial, activated = false, checks = 0;
      const surface = {
        read: () => readReview(actions.map((action, index) => `│ ${selected === index ? '→' : ' '} \x1b[31m${action}: explanation\x1b[0m │`)),
        async key(key) {
          if (key === '\r') { activated = true; return; }
          assert.ok(['\x1b[A', '\x1b[B'].includes(key));
          const next = selected + (key === '\x1b[B' ? 1 : -1);
          selected = wrap ? (next + actions.length) % actions.length : Math.max(0, Math.min(actions.length - 1, next));
        },
      };
      const visited = await navigateReview(surface, 'Execute', async () => { checks++; assert.equal(activated, false); });
      assert.equal(surface.read().selected, 'Execute');
      assert.equal(visited.size, 3);
      assert.ok(checks > 0);
      assert.equal(activated, false);
    });
  }
}
test('full word, single visible selection, no substring or ambiguous acceptance', () => {
  for (const text of ['→ Executed', '→ StayHere', '→ Refine2']) assert.equal(readReview([text]).action, undefined);
  for (const text of ['Execute\nStay\nRefine', '→ Execute\n→ Stay']) assert.equal(readReview([text]), undefined);
  assert.equal(readReview(['→ Execute—do it']).selected, 'Execute');
});
test('closed surface never receives a key', async () => {
  await assert.rejects(navigateReview({ read: () => undefined, key: () => assert.fail('inactive input') }, 'Execute'), /no longer active/);
});
test('unreachable actions rejected without activation', async () => {
  let keys = 0;
  await assert.rejects(navigateReview({ read: () => readReview(['→ Execute']), key: async (key) => { assert.notEqual(key, '\r'); keys++; } }, 'Execute'), /did not reach all/);
  assert.equal(keys, 2);
});
test('navigation invariant failure is propagated before activation', async () => {
  await assert.rejects(navigateReview({ read: () => readReview(['→ Execute']), key: async (key) => assert.notEqual(key, '\r') }, 'Stay', async () => { throw new Error('navigation approved'); }), /navigation approved/);
});

test('extra visible actions are navigable but not relabelled as required actions', async () => {
  const labels = ['Stay', 'Help', 'Refine', 'Execute']; let index = 0;
  const surface = { read: () => readReview(labels.map((label, n) => `${n === index ? '→' : ' '} ${label}`)), key: async (key) => { index = Math.max(0, Math.min(labels.length - 1, index + (key === '\x1b[B' ? 1 : -1))); } };
  const visited = await navigateReview(surface, 'Stay');
  assert.equal(visited.size, 3); assert.equal(surface.read().action, 'Stay');
});
