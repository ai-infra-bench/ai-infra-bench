import { readdir } from 'node:fs/promises';
import path from 'node:path';

export function manifestPathParts(manifest) {
  for (const field of ['task', 'model', 'reasoning_effort', 'agent', 'agent_version', 'trial_name']) {
    if (typeof manifest[field] !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(manifest[field])) throw new Error('Unsafe or missing manifest path field');
  }
  const parts = [manifest.task, manifest.model, manifest.reasoning_effort, `${manifest.agent}-${manifest.agent_version}`, manifest.trial_name];
  if (!['valid', 'excluded'].includes(manifest.status)) throw new Error('Unknown manifest status');
  return parts;
}

// Only the five archive layout levels are scanned, never nested task artifacts.
export async function assertArchiveCoverage(directory, manifests) {
  const expected = new Set();
  for (const manifest of manifests) {
    const key = manifestPathParts(manifest).join('/');
    if (expected.has(key)) throw new Error(`Duplicate manifest: ${key}`);
    expected.add(key);
  }
  const actual = new Set();
  async function walk(current, parts = []) {
    if (parts.length === 5) { actual.add(parts.join('/')); return; }
    for (const entry of await readdir(current, { withFileTypes: true })) {
      if (entry.isDirectory()) await walk(path.join(current, entry.name), [...parts, entry.name]);
      else if (entry.isSymbolicLink()) throw new Error(`Archive layout contains a symlink: ${entry.name}`);
    }
  }
  await walk(directory);
  const missing = [...expected].filter(key => !actual.has(key));
  const unlisted = [...actual].filter(key => !expected.has(key));
  if (missing.length || unlisted.length) throw new Error(`Archive/manifest mismatch: ${missing.length} missing, ${unlisted.length} unlisted. ${[...missing, ...unlisted].slice(0, 5).join(', ')}`);
}

export function assertTrialIdentity(manifest, result, config, trajectory) {
  const equal = (actual, expected, label) => {
    if (actual !== expected) throw new Error(`${manifest.trial_name}: ${label} mismatch`);
  };
  equal(result.task_name?.replace(/^ai-infra-bench\//, ''), manifest.task, 'task');
  equal(result.trial_name, manifest.trial_name, 'trial');
  equal(config.trial_name, manifest.trial_name, 'configured trial');
  equal(config.agent?.model_name, manifest.model, 'configured model');
  equal(config.agent?.name, manifest.agent, 'agent');
  equal(config.agent?.kwargs?.version, manifest.agent_version, 'agent version');
  equal(result.task_checksum, manifest.task_checksum, 'task checksum');
  equal(result.started_at, manifest.started_at, 'start time');
  equal(result.finished_at, manifest.finished_at, 'finish time');
  if (trajectory?.agent) {
    equal(trajectory.agent.model_name, manifest.model, 'trajectory model');
    equal(trajectory.agent.version, manifest.agent_version, 'trajectory version');
  }
}

export function assertValidOutcome(manifest, result, trajectory) {
  const reward = result.verifier_result?.rewards?.reward;
  if (reward !== 0 && reward !== 1) throw new Error(`${manifest.trial_name}: missing or non-binary reward`);
  if (manifest.reward !== reward) throw new Error(`${manifest.trial_name}: reward differs from manifest`);
  if (result.exception_info || !trajectory?.final_metrics || !Array.isArray(trajectory.steps)
    || trajectory.steps.some(step => String(step.message ?? '').includes('<turn_aborted>'))) {
    throw new Error(`Manifest marked valid but trajectory is invalid: ${manifest.trial_name}`);
  }
  const started = Date.parse(result.started_at), finished = Date.parse(result.finished_at);
  if (!Number.isFinite(started) || !Number.isFinite(finished) || finished < started) throw new Error(`${manifest.trial_name}: invalid execution times`);
}

export function recordedMetric(resultValue, trajectoryValue, label) {
  const value = resultValue ?? trajectoryValue;
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) throw new Error(`Missing or invalid ${label}`);
  return value;
}
