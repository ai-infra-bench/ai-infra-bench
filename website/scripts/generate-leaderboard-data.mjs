import { readFile, readdir, writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { orderTaskRepetitions, repetitionStatistics } from './leaderboard-statistics.mjs';

const projectDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function readOption(name, fallback) {
  const index = process.argv.indexOf(name);
  return index === -1 ? fallback : process.argv[index + 1];
}

const archiveRoot = path.resolve(
  readOption('--root', '/mnt/nas/ai-infra-bench/leaderboard'),
);
const release = readOption('--release', '2026-09-08');
const expectedAttempts = Number(readOption('--attempts', '4'));
const outputPath = path.resolve(
  readOption('--output', path.join(projectDir, 'app/generated/leaderboard.json')),
);

if (!Number.isInteger(expectedAttempts) || expectedAttempts < 1) {
  throw new Error(`--attempts must be a positive integer, received ${expectedAttempts}`);
}

async function walkJsonFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walkJsonFiles(entryPath));
    else if (entry.isFile() && entry.name.endsWith('.json')) files.push(entryPath);
  }
  return files.sort();
}

async function readJson(file) {
  return JSON.parse(await readFile(file, 'utf8'));
}

function mean(values) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function round(value, places = 4) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  const scale = 10 ** places;
  return Math.round(value * scale) / scale;
}

function parseDate(value) {
  const timestamp = Date.parse(value ?? '');
  return Number.isFinite(timestamp) ? timestamp : null;
}

function wilsonInterval(successes, total) {
  if (!total) return { low: null, high: null };
  const z = 1.959963984540054;
  const z2 = z ** 2;
  const proportion = successes / total;
  const denominator = 1 + z2 / total;
  const center = (proportion + z2 / (2 * total)) / denominator;
  const spread = z * Math.sqrt(
    proportion * (1 - proportion) / total + z2 / (4 * total ** 2),
  ) / denominator;
  return {
    low: round(Math.max(0, center - spread) * 100, 2),
    high: round(Math.min(1, center + spread) * 100, 2),
  };
}

function effortRank(effort) {
  return ({ low: 0, medium: 1, high: 2, xhigh: 3 })[effort] ?? 99;
}

const manifestDirectory = path.join(archiveRoot, 'manifests', release);
const manifests = await Promise.all(
  (await walkJsonFiles(manifestDirectory)).map(readJson),
);

if (!manifests.length) {
  throw new Error(`No manifests found in ${manifestDirectory}`);
}

const tasks = [...new Set(manifests.map((manifest) => manifest.task))].sort();
const configurationKeys = [...new Set(manifests.map((manifest) => [
  manifest.model,
  manifest.reasoning_effort,
  manifest.agent,
  manifest.agent_version,
].join('\u0000')))];

const validTrials = [];
const excludedTrials = [];

for (const manifest of manifests) {
  const publicManifest = {
    task: manifest.task,
    model: manifest.model,
    effort: manifest.reasoning_effort,
    agent: manifest.agent,
    agentVersion: manifest.agent_version,
    trial: manifest.trial_name,
    reasons: manifest.exclusion_reasons ?? [],
  };

  if (manifest.status !== 'valid') {
    excludedTrials.push(publicManifest);
    continue;
  }

  const trialDirectory = path.join(
    archiveRoot,
    'archive',
    release,
    manifest.task,
    manifest.model,
    manifest.reasoning_effort,
    `${manifest.agent}-${manifest.agent_version}`,
    manifest.trial_name,
  );
  const [result, trajectory] = await Promise.all([
    readJson(path.join(trialDirectory, 'result.json')),
    readJson(path.join(trialDirectory, 'agent/trajectory.json')),
  ]);
  const agentSteps = (trajectory.steps ?? []).filter((step) => step.source === 'agent');
  const containsAbort = (trajectory.steps ?? []).some(
    (step) => String(step.message ?? '').includes('<turn_aborted>'),
  );
  if (containsAbort || !trajectory.final_metrics || result.exception_info) {
    throw new Error(`Manifest marked valid but trajectory is invalid: ${manifest.trial_name}`);
  }

  const startedAt = parseDate(result.started_at);
  const finishedAt = parseDate(result.finished_at);
  validTrials.push({
    ...publicManifest,
    sourceJob: manifest.source_job,
    reward: Number((result.verifier_result?.rewards ?? {}).reward),
    costUsd: Number(result.agent_result?.cost_usd ?? trajectory.final_metrics.total_cost_usd ?? 0),
    inputTokens: Number(result.agent_result?.n_input_tokens ?? trajectory.final_metrics.total_prompt_tokens ?? 0),
    cachedTokens: Number(result.agent_result?.n_cache_tokens ?? trajectory.final_metrics.total_cached_tokens ?? 0),
    outputTokens: Number(result.agent_result?.n_output_tokens ?? trajectory.final_metrics.total_completion_tokens ?? 0),
    turns: agentSteps.length,
    toolCalls: agentSteps.reduce((sum, step) => sum + (step.tool_calls?.length ?? 0), 0),
    durationSeconds: startedAt !== null && finishedAt !== null ? (finishedAt - startedAt) / 1000 : null,
    startedAt: result.started_at,
    finishedAt: result.finished_at,
  });
}

const configurations = configurationKeys.map((key) => {
  const [model, effort, agent, agentVersion] = key.split('\u0000');
  const configurationManifests = manifests.filter((manifest) => manifest.model === model
    && manifest.reasoning_effort === effort && manifest.agent === agent && manifest.agent_version === agentVersion);
  const trials = validTrials.filter((trial) => (
    trial.model === model
    && trial.effort === effort
    && trial.agent === agent
    && trial.agentVersion === agentVersion
  ));
  const taskResults = tasks.map((task) => {
    const attempts = trials.filter((trial) => trial.task === task);
    return {
      task,
      attempts: attempts.length,
      passes: attempts.filter((trial) => trial.reward === 1).length,
      costUsd: round(attempts.reduce((sum, trial) => sum + trial.costUsd, 0)),
    };
  });
  const passes = trials.filter((trial) => trial.reward === 1).length;
  const tasksPassed = taskResults.filter((task) => task.passes > 0).length;
  const totalCostUsd = trials.reduce((sum, trial) => sum + trial.costUsd, 0);
  const passAverage = trials.length ? passes / trials.length * 100 : null;
  const passAtK = tasks.length ? tasksPassed / tasks.length * 100 : null;
  const repetitions = repetitionStatistics(tasks.map((task) => orderTaskRepetitions(
    trials.filter((trial) => trial.task === task),
    configurationManifests.filter((manifest) => manifest.task === task),
    expectedAttempts,
  )), expectedAttempts);

  return {
    id: [model, effort, agent, agentVersion].join('--'),
    model,
    modelLabel: model,
    effort,
    agent,
    agentVersion,
    status: taskResults.every((task) => task.attempts === expectedAttempts) ? 'complete' : 'partial',
    metrics: {
      passAverage: round(passAverage, 2),
      passAverageStd: round(repetitions?.standardDeviation, 2),
      repetitionPassRates: repetitions?.passRates.map((rate) => round(rate, 4)) ?? null,
      repetitionPassedTasks: repetitions?.passes ?? null,
      passAverageCi95: wilsonInterval(passes, trials.length),
      passAtK: round(passAtK, 2),
      passAtKCi95: wilsonInterval(tasksPassed, tasks.length),
      passedTrials: passes,
      validTrials: trials.length,
      expectedTrials: tasks.length * expectedAttempts,
      tasksPassed,
      taskCount: tasks.length,
      completeTasks: taskResults.filter((task) => task.attempts === expectedAttempts).length,
      totalCostUsd: round(totalCostUsd),
      averageCostUsd: round(mean(trials.map((trial) => trial.costUsd))),
      passesPer100Usd: totalCostUsd ? round(passes / totalCostUsd * 100, 2) : null,
      averageTurns: round(mean(trials.map((trial) => trial.turns)), 2),
      averageToolCalls: round(mean(trials.map((trial) => trial.toolCalls)), 2),
      averageOutputTokens: round(mean(trials.map((trial) => trial.outputTokens)), 0),
      averageDurationMinutes: round(mean(
        trials.map((trial) => trial.durationSeconds).filter((value) => value !== null),
      ) / 60, 2),
      inputTokens: trials.reduce((sum, trial) => sum + trial.inputTokens, 0),
      cachedTokens: trials.reduce((sum, trial) => sum + trial.cachedTokens, 0),
      outputTokens: trials.reduce((sum, trial) => sum + trial.outputTokens, 0),
    },
    tasks: taskResults,
  };
}).sort((a, b) => (
  (b.metrics.passAverage ?? -1) - (a.metrics.passAverage ?? -1)
  || a.model.localeCompare(b.model)
  || effortRank(b.effort) - effortRank(a.effort)
));

const finishedTimes = validTrials.map((trial) => parseDate(trial.finishedAt)).filter((value) => value !== null);
const startedTimes = validTrials.map((trial) => parseDate(trial.startedAt)).filter((value) => value !== null);
const exclusionReasons = {};
for (const trial of excludedTrials) {
  for (const reason of trial.reasons.length ? trial.reasons : ['unspecified']) {
    exclusionReasons[reason] = (exclusionReasons[reason] ?? 0) + 1;
  }
}

const data = {
  schemaVersion: 'ai_infra_bench_leaderboard.v1',
  generatedAt: new Date().toISOString(),
  release: {
    id: release,
    label: 'September 2026',
    expectedAttempts,
    taskCount: tasks.length,
    configurationCount: configurations.length,
    validTrials: validTrials.length,
    expectedTrials: tasks.length * configurations.length * expectedAttempts,
    excludedTrials: excludedTrials.length,
    status: configurations.every((configuration) => configuration.status === 'complete') ? 'complete' : 'partial',
    evaluatedFrom: startedTimes.length ? new Date(Math.min(...startedTimes)).toISOString() : null,
    evaluatedThrough: finishedTimes.length ? new Date(Math.max(...finishedTimes)).toISOString() : null,
  },
  methodology: {
    passAverage: 'Successful trials divided by all valid trials.',
    passAverageStd: `Sample standard deviation (ddof=1) of the ${expectedAttempts} complete repetition pass rates, in percentage points.`,
    repetitions: 'Attempts are ordered by execution start within each task. A later infrastructure replacement fills its original attempt slot; a complete task rerun uses the new batch order. Ambiguous replacement mappings are rejected.',
    passAtK: `Tasks with at least one success across ${expectedAttempts} valid attempts, divided by all tasks.`,
    confidenceInterval: 'Wilson score interval at 95% confidence.',
    costEfficiency: 'Successful trials per $100 of recorded model cost.',
  },
  tasks,
  configurations,
  exclusions: {
    count: excludedTrials.length,
    byReason: exclusionReasons,
    trials: excludedTrials.sort((a, b) => a.trial.localeCompare(b.trial)),
  },
};

await mkdir(path.dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${JSON.stringify(data, null, 2)}\n`);
console.log(JSON.stringify({
  output: outputPath,
  release,
  tasks: tasks.length,
  configurations: configurations.length,
  validTrials: validTrials.length,
  excludedTrials: excludedTrials.length,
  status: data.release.status,
}));
