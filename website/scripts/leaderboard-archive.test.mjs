import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { assertArchiveCoverage, assertTrialIdentity, assertValidOutcome, manifestPathParts, recordedMetric } from './leaderboard-archive.mjs';

const manifest = { task: 'task-a', model: 'model-a', reasoning_effort: 'high', agent: 'codex', agent_version: '0.153.4', trial_name: 'trial-a', status: 'valid', reward: 1, task_checksum: 'task-hash', started_at: '2026-09-08T00:00:00Z', finished_at: '2026-09-08T00:01:00Z' };
function fixture(m = manifest) {
  const agent = { name: m.agent, model_name: m.model, kwargs: { version: m.agent_version } };
  const result = { task_name: 'ai-infra-bench/' + m.task, trial_name: m.trial_name, task_checksum: m.task_checksum, started_at: m.started_at, finished_at: m.finished_at, exception_info: null, agent_result: { cost_usd: 1, n_input_tokens: 100, n_cache_tokens: 50, n_output_tokens: 20 }, verifier_result: { rewards: { reward: m.reward } } };
  const config = { trial_name: m.trial_name, agent };
  const trajectory = { agent: { model_name: m.model, version: m.agent_version }, final_metrics: { total_cost_usd: 1 }, steps: [{ source: 'agent', message: 'done', tool_calls: [] }] };
  return { result, config, trajectory };
}

test('archive identity and outcomes are validated before aggregation', () => {
  const { result, config, trajectory } = fixture();
  assertTrialIdentity(manifest, result, config, trajectory);
  assertValidOutcome(manifest, result, trajectory);
  assert.throws(() => assertTrialIdentity(manifest, { ...result, task_name: 'wrong' }, config, trajectory), /task mismatch/);
  assert.throws(() => assertTrialIdentity(manifest, result, { ...config, agent: { ...config.agent, model_name: 'wrong' } }, trajectory), /model mismatch/);
  for (const reward of [undefined, null, '1', 0.5, NaN]) assert.throws(() => assertValidOutcome(manifest, { ...result, verifier_result: { rewards: { reward } } }, trajectory), /reward/);
  assert.throws(() => assertValidOutcome(manifest, result, { ...trajectory, steps: [{ message: '<turn_aborted>' }] }), /invalid/);
  assert.throws(() => assertValidOutcome(manifest, { ...result, exception_info: { exception_type: 'ApiRateLimitError' } }, trajectory), /invalid/);
});

test('safe metadata paths and zero versus missing measurements', () => {
  assert.equal(manifestPathParts(manifest).join('/'), 'task-a/model-a/high/codex-0.153.4/trial-a');
  for (const task of ['../outside', '', undefined]) assert.throws(() => manifestPathParts({ ...manifest, task }), /Unsafe/);
  assert.throws(() => manifestPathParts({ ...manifest, agent: undefined }), /Unsafe/);
  assert.throws(() => manifestPathParts({ ...manifest, status: 'pending' }), /status/);
  assert.equal(recordedMetric(0, 10, 'cost'), 0);
  assert.equal(recordedMetric(null, 10, 'cost'), 10);
  for (const value of [null, undefined, NaN, Infinity, -1, '0']) assert.throws(() => recordedMetric(value, null, 'cost'), /invalid/);
});

test('moved archive, independent manifest location and partial statistics work end to end', async t => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'leaderboard-fixture-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const archive = path.join(root, 'archive', 'v0-17task'), manifests = path.join(root, 'manifests', 'old-date');
  const all = [];
  for (const [task, rewards] of [['task-a', [1, 0, 1, 1]], ['task-b', [1, 0, 0]]]) {
    for (const [index, reward] of rewards.entries()) {
      const m = { ...manifest, task, trial_name: task + '-' + index, reward, source_job: 'single-job', started_at: `2026-09-08T0${index}:00:00Z`, finished_at: `2026-09-08T0${index}:01:00Z` };
      const parts = manifestPathParts(m), trial = path.join(archive, ...parts), mf = path.join(manifests, ...parts.slice(0, -1), parts.at(-1) + '.json');
      await mkdir(trial, { recursive: true }); await mkdir(path.join(trial, 'agent')); await mkdir(path.dirname(mf), { recursive: true });
      const f = fixture(m); await writeFile(mf, JSON.stringify(m));
      await writeFile(path.join(trial, 'result.json'), JSON.stringify(f.result)); await writeFile(path.join(trial, 'config.json'), JSON.stringify(f.config)); await writeFile(path.join(trial, 'agent/trajectory.json'), JSON.stringify(f.trajectory));
      all.push(m);
    }
  }
  const configFile = path.join(root, 'source.json'), output = path.join(root, 'data.json');
  await writeFile(configFile, JSON.stringify({ release: 'v0-17task', archiveDirectory: archive, manifestDirectory: manifests, expectedAttempts: 4, missingRepetitions: [{ configurationId: 'model-a--high--codex--0.153.4', task: 'task-b', slots: [4] }] }));
  const command = () => spawnSync(process.execPath, [new URL('./generate-leaderboard-data.mjs', import.meta.url).pathname, '--source', configFile, '--output', output], { encoding: 'utf8' });
  const run = command(); assert.equal(run.status, 0, run.stderr);
  const data = JSON.parse(await readFile(output, 'utf8')), metrics = data.configurations[0].metrics;
  assert.equal(data.release.id, 'v0-17task'); assert.equal(data.release.validTrials, 7); assert.equal(metrics.passAverage, 57.14);
  assert.equal(metrics.passAverageStd, 47.87); assert.deepEqual(metrics.repetitionTaskCounts, [2, 2, 2, 1]);
  const saved = await readFile(output, 'utf8');
  await mkdir(path.join(archive, 'task-a/model-a/high/codex-0.153.4/unlisted-trial'));
  await assert.rejects(assertArchiveCoverage(archive, all), /1 unlisted/);
  assert.notEqual(command().status, 0); assert.equal(await readFile(output, 'utf8'), saved);
});
