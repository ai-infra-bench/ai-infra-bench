# Rollout review report and evidence

Start with whether the observed rewards can be trusted and whether the task can
be retained. Separate candidate correctness, scoring correctness, and evidence
completeness. Explain the material mechanism, not just the exception label or
the agent's self-report.

State the approved validation mode, review/experiment scope, and artifact
inventory first. Separate test validity, demonstrated candidate behavior, and
full-task solvability. An accepted verifier-only mode may support the first two
without evidence for the third; report that limit without inventing an Oracle
requirement or certifying the complete task.

## Per-attempt records

Include all requested attempts in one table, keeping original and replayed
results in separate columns or tables. Record:

- task name/version and immutable task revision or snapshot identity;
- trial ID, model, reasoning effort, and model revision if actually recorded;
- agent harness/name/version and Harbor version;
- total, agent, and verifier elapsed time;
- Agent Step, tool-call count, modified file count, added/deleted lines;
- verifier passed/total, failures, errors, skips, lifecycle completion, reward;
- actual reward-zero cause, independent correctness finding, suspected or
  confirmed scoring defect, and hack assessment;
- final-artifact availability, evidence links, and remaining limitations.

Define metrics rather than conflating them. For ATIF, count `source=agent`
steps separately from total trajectory steps. State whether tool counts use
top-level orchestrator calls or nested/native tool operations; parallel nested
commands are not necessarily separate model turns. Count final tracked and
untracked files and line additions/deletions, not cumulative edit operations;
separate production and test changes when useful. Record binary files separately.

Do not parse a patch's numstat from a nested repository directory where Git may
silently exclude paths outside that prefix. Use a known repository root and
cross-check the changed paths against the captured status and artifact archive.
Missing data is 'not recorded', not zero. Redact credentials from excerpts.

If final snapshots are missing, mark final file/line counts unavailable even if
the trajectory records edit commands. Directly evidenced behavior failures may
still be confirmed, but final-code review, complete replay, and full hack
screening must remain incomplete. Equivalent immutable snapshots are acceptable;
a valid empty patch is not automatically missing evidence.

## Findings

For each material finding provide:

1. Contract requirement and whether it was explicit, necessarily inferable,
   ambiguous, or absent. Separate SDK/schema constraints, semantic requirements,
   and reference observations; state any explicitly required reference parity.
2. Affected attempts and the trajectory actions/final code that caused it.
3. Minimal valid input/event sequence and expected versus observed behavior.
4. Actual reproduction command, image/task/patch identities, pre-run input
   hashes and post-run checks, effective comparison conditions, logs, and
   whether it ran through grading or only a diagnostic substitute. Retrospective
   hashes must not be labeled as pre-run evidence.
5. Attribution: agent defect, uncovered defect accepted by verifier, overstrict
   assertion, broken fixture/scorer, insufficient environment, answer exposure,
   or unresolved evidence. Use multiple attributions where necessary.
6. Smallest supported remediation and current validation state.

Use 'confirmed' for reproduced or directly evidenced findings, 'suspected' for
untested hypotheses, and 'inconclusive' for missing/conflicting evidence. State
'no hack observed in the reviewed material' when warranted; missing trajectories
or artifacts prevent a complete hack assessment. Answer leakage can invalidate
an evaluation even without evidence that the agent intentionally sought it.

## Campaign synthesis

Group attempts by causal defect and behavior, not patch similarity alone. Show
an attempt-by-behavior matrix for differential cases and explain why a given
case passes some incomplete answers while rejecting others. Keep original
reward, individual new-case outcome, and revised full-suite reward distinct.

Use this compact handoff for each proposed case:

```text
Behavior / contract basis:
Approved validation mode / experimental scope:
Artifact availability / resulting conclusion limits:
Legal input and stable entrypoint:
Independent expected result:
Reference role / effective comparison conditions:
Real components and justified substitutions:
Why existing coverage misses it:
Original attempt outcomes / new-case outcomes:
Mode-appropriate controls / remaining solvability evidence gaps:
Frozen input identity / validation stage and checks actually run:
Diagnosis confidence and scoring-promotion status:
```

After changes, report the final version, executed controls/replays, remaining
issues, and commit/push state. Do not interpret a small number of SOTA rollouts
as a reliable population pass rate, or an all-zero set as proof of unsolvability.
Tests derived from the observed candidates provide development evidence; model
comparisons on a revised benchmark need fresh frozen evaluation data.
