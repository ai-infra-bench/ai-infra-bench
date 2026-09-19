import test from 'node:test';
import assert from 'node:assert/strict';
import { formatLabel, formatTaskTitle } from '../app/lib/task-format.ts';

test('workload aliases have one display label', () => {
  for (const value of ['bugfix', 'bug_fix', 'bug-fix', 'Bug Fix']) assert.equal(formatLabel(value), 'Bug fix');
});
test('technical acronyms retain their spelling', () => {
  assert.equal(formatLabel('serving_api'), 'Serving API');
  assert.equal(formatLabel('kv_cache_data_movement'), 'KV cache data movement');
  assert.equal(formatLabel('cpu'), 'CPU');
});
test('task titles remain unchanged', () => {
  assert.equal(formatTaskTitle('vllm-pyav-target-frame-selection'), 'PyAV Target Frame Selection');
  assert.equal(formatTaskTitle('vllm-rust-tool-entity-preservation'), 'Rust Tool Entity Preservation');
});
