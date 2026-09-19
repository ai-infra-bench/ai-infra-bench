# Pre-final integration checks

The first original-image Harbor Oracle ran all 24 behavioral groups, but Harbor rejected the result because `reward.json` contained a nonnumeric `completed_checks` list. The report now lives in `behavior-report.json`; `reward.json` contains only the numeric primary reward. Both reward files are initialized to zero before grading starts.

The next Harbor trial completed with reward 1 and no execution errors. It exposed a separate CI-reader incompatibility: this Harbor version names a single-key aggregate `mean`, while the older repository helper only looked for `metrics[].reward`. Repository-wide parsing of the explicitly named `reward_stats.reward` distribution, with a legacy fallback and regression coverage, had already merged in PR #75. This task PR therefore contains no `.github` change. Neither integration fix changes the behavioral contract.

These checks preceded the final artifact freeze. The final 18-case matrix in `../run-results.json` is the acceptance record.
