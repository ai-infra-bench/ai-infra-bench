# Historical audit: before the scope correction

These files describe benchmark commit `f4163bcf3166fd1799341d0bbc5defa8afea65b5`,
which collected 115 cases. They are immutable historical observations and
recommendations, not the current contract or current results.

- The pinned-Base Python probes measured 29/15 request results and 8/2 converter
  results. Their case map covers the old 115-case suite.
- The latest-Python comparison measured 95 passes and 20 failures against vLLM
  `e962733e08d10f7ca65dac4df99e116460b8b174`. Its full 20-case explanation,
  raw supplementary observations, and original adapter are in `latest_python/`.
- `e2e-evidence.json` records the earlier five Base and five control trials.

To reproduce, check out the benchmark commit above, restore these files under
its `validation/` directory in their original layout, and use that commit's
`tests/`. Running these historical scripts against the current tests would
change their inputs and would not reproduce the recorded counts.

The current contract and measured results are in `../../contract-matrix.md`,
`../../latest_python/`, and `../../e2e-evidence.json`.
