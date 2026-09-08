function chronological(trials, startedAt, name) {
  for (const trial of trials) {
    if (!Number.isFinite(Date.parse(trial[startedAt]))) {
      throw new Error(`Missing execution time for ${trial[name]}`);
    }
  }
  return [...trials].sort((a, b) => Date.parse(a[startedAt]) - Date.parse(b[startedAt])
    || a[startedAt].localeCompare(b[startedAt]) || a[name].localeCompare(b[name]));
}

// Harbor submits repetitions in order. Number each task's attempts by execution
// start, preserving an invalid original's slot when its replacement runs later.
export function orderTaskRepetitions(trials, manifests, expectedAttempts) {
  if (trials.length !== expectedAttempts) return null;
  const byName = new Map(trials.map((trial) => [trial.trial, trial]));
  if (byName.size !== trials.length) throw new Error('Duplicate trial in repetition data');

  const jobs = new Set(trials.map((trial) => trial.sourceJob));
  if (jobs.size === 1) return chronological(trials, 'startedAt', 'trial');

  const sourceBatches = new Map();
  for (const manifest of manifests) {
    const batch = sourceBatches.get(manifest.source_job) ?? [];
    batch.push(manifest);
    sourceBatches.set(manifest.source_job, batch);
  }
  const originals = [...sourceBatches.values()].filter((batch) => batch.length === expectedAttempts
    && batch.some((manifest) => byName.has(manifest.trial_name)));
  if (originals.length === 1) {
    const original = chronological(originals[0], 'started_at', 'trial_name');
    const originalNames = new Set(original.map((manifest) => manifest.trial_name));
    const missing = original.filter((manifest) => !byName.has(manifest.trial_name));
    const replacements = trials.filter((trial) => !originalNames.has(trial.trial));
    if (missing.length === 1 && missing[0].status === 'excluded' && replacements.length === 1) {
      return original.map((manifest) => byName.get(manifest.trial_name) ?? replacements[0]);
    }
  }

  if (manifests.every((manifest) => manifest.status === 'valid')) {
    return chronological(trials, 'startedAt', 'trial');
  }
  throw new Error(`Ambiguous replacement-to-repetition mapping for ${trials[0]?.task ?? 'task'}`);
}

export function repetitionStatistics(taskRepetitions, expectedAttempts) {
  if (!taskRepetitions.length || taskRepetitions.some((trials) => !trials || trials.length !== expectedAttempts)) return null;
  const passes = Array.from({ length: expectedAttempts }, (_, index) => (
    taskRepetitions.reduce((sum, trials) => {
      const reward = trials[index].reward;
      if (reward !== 0 && reward !== 1) throw new Error('Pass statistics require binary rewards');
      return sum + reward;
    }, 0)
  ));
  const passRates = passes.map((count) => 100 * count / taskRepetitions.length);
  const mean = passRates.reduce((sum, value) => sum + value, 0) / expectedAttempts;
  const standardDeviation = expectedAttempts > 1
    ? Math.sqrt(passRates.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (expectedAttempts - 1))
    : null;
  return { passes, passRates, mean, standardDeviation };
}
