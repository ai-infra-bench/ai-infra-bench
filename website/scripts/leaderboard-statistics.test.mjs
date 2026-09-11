import assert from 'node:assert/strict';
import test from 'node:test';
import { orderTaskRepetitions, repetitionStatistics } from './leaderboard-statistics.mjs';

const trial = (name, hour, reward, sourceJob = 'original') => ({
  trial: name, task: 'example-task', startedAt: `2026-09-08T${String(hour).padStart(2, '0')}:00:00Z`, reward, sourceJob,
});
const manifest = (entry, status = 'valid') => ({
  trial_name: entry.trial, started_at: entry.startedAt, source_job: entry.sourceJob, status,
});

test('std is across complete repetition scores, with the sample denominator', () => {
  const matrix = [[1, 0, 1, 0], [1, 1, 0, 0]].map((rewards) => rewards.map((reward) => ({ reward })));
  const result = repetitionStatistics(matrix, 4);
  assert.deepEqual(result.passRates, [100, 50, 50, 0]);
  assert.equal(result.mean, 50);
  assert.ok(Math.abs(result.standardDeviation - Math.sqrt(5000 / 3)) < 1e-10);
});

test('late replacement fills the invalid original slot, not the final round', () => {
  const original = [trial('a', 1, 0), trial('bad', 2, 1), trial('c', 3, 1), trial('d', 4, 0)];
  const repair = trial('repair', 10, 1, 'repair-job');
  const manifests = [...original.map((t, i) => manifest(t, i === 1 ? 'excluded' : 'valid')), manifest(repair)];
  const ordered = orderTaskRepetitions([original[3], repair, original[0], original[2]], manifests, 4);
  assert.deepEqual(ordered.map((t) => t.trial), ['a', 'repair', 'c', 'd']);
  assert.deepEqual(ordered.map((t) => t.reward), [0, 1, 1, 0]);
});

test('a complete rerun uses its own chronological attempt order', () => {
  const old = [1, 2, 3, 4].map((hour) => trial('old-' + hour, hour, 0));
  const fresh = [5, 6, 7, 8].map((hour) => trial('new-' + hour, hour, hour % 2, 'rerun'));
  const ordered = orderTaskRepetitions([...fresh].reverse(), [...old.map((t) => manifest(t, 'excluded')), ...fresh.map((t) => manifest(t))], 4);
  assert.deepEqual(ordered.map((t) => t.trial), fresh.map((t) => t.trial));
});

test('partial repetitions have no std instead of pretending to be zero', () => {
  assert.equal(orderTaskRepetitions([trial('a', 1, 1)], [], 4), null);
  assert.equal(repetitionStatistics([null], 4), null);
});

test('ambiguous multiple replacements fail rather than fabricate rounds', () => {
  const original = [1, 2, 3, 4].map((hour) => trial('old-' + hour, hour, hour % 2));
  const repairs = [trial('repair-a', 10, 1, 'repair'), trial('repair-b', 11, 0, 'repair')];
  const manifests = [...original.map((t, i) => manifest(t, i < 2 ? 'excluded' : 'valid')), ...repairs.map((t) => manifest(t))];
  assert.throws(() => orderTaskRepetitions([...original.slice(2), ...repairs], manifests, 4), /Ambiguous replacement/);
});

test('verified missing slots preserve chronology without inventing a failed attempt', () => {
  const observed = [trial('first', 1, 1), trial('second', 2, 0), trial('third', 3, 1)];
  const mapped = orderTaskRepetitions([...observed].reverse(), observed.map(t => manifest(t)), 4, [4]);
  assert.deepEqual(mapped, [...observed, null]);
  const other = [trial('a', 1, 1), trial('b', 2, 0), trial('c', 3, 0), trial('d', 4, 1)];
  assert.equal(repetitionStatistics([mapped, other], 4), null);
  const stats = repetitionStatistics([mapped, other], 4, { allowPartial: true });
  assert.deepEqual(stats.taskCounts, [2, 2, 2, 1]);
  assert.deepEqual(stats.passRates, [100, 0, 50, 100]);
  assert.ok(Math.abs(stats.standardDeviation - Math.sqrt(6875 / 3)) < 1e-8);
});

test('missing slots are explicit and can occur at the start, not only at the end', () => {
  const observed = [trial('a', 2, 1), trial('b', 3, 0), trial('c', 4, 1)];
  const manifests = observed.map(t => manifest(t));
  assert.equal(orderTaskRepetitions(observed, manifests, 4), null);
  assert.deepEqual(orderTaskRepetitions(observed, manifests, 4, [1]), [null, ...observed]);
  for (const slots of [[0], [5], [1, 1], [1, 2]]) assert.throws(() => orderTaskRepetitions(observed, manifests, 4, slots), /Invalid missing/);
  assert.throws(() => orderTaskRepetitions([...observed.slice(0, 2), trial('repair', 8, 1, 'repair')], manifests, 4, [4]), /explicit full mapping/);
});

test('a now-complete group supersedes its old missing-slot hint', () => {
  const observed = [1, 2, 3, 4].map(i => trial('a' + i, i, i % 2));
  assert.deepEqual(orderTaskRepetitions(observed, observed.map(t => manifest(t)), 4, [4]), observed);
});
