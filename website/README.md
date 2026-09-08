# Website

The homepage includes the leaderboard and task catalog. The production site is
published at <https://ai-infra-bench.github.io/>.

## Local development

From `website/`:

```sh
npm ci
npm run dev
```

Task pages are generated from the repository's `tasks/` directory. Leaderboard
results come from the committed `app/generated/leaderboard.json` snapshot.

## Updating leaderboard results

Keep full Harbor trial directories in the external archive, preserving their
original names. The default archive root is
`/mnt/nas/ai-infra-bench/leaderboard`:

```text
archive/<release>/<task>/<model>/<effort>/<agent-version>/<original-trial-name>/
manifests/<release>/<task>/<model>/<effort>/<agent-version>/<original-trial-name>.json
```

From the repository root, archive one or more completed Harbor jobs:

```sh
python3 tools/leaderboard/archive_harbor_trials.py \
  --release 2026-09-08 \
  /path/to/harbor-job
```

The archiver verifies copied files with a tree checksum. It retains invalid runs
with exclusion reasons instead of counting them toward scores. It requires
Python 3.11+ and `rsync`. Use `--root` to choose another archive location.

Then regenerate the public snapshot from `website/`:

```sh
npm run generate:leaderboard -- --release 2026-09-08 --attempts 4
npm run test:leaderboard
```

Review and commit `app/generated/leaderboard.json` together with any website
changes. Raw trial directories and private trajectories stay outside the Git
repository. Model IDs are displayed verbatim.

Pass average is the fraction of successful valid trials. Its displayed standard
deviation is the sample standard deviation (`ddof=1`) of the four complete
repetition pass rates. Attempts are ordered by execution start within each task;
a later infrastructure replacement fills the invalid original's repetition
slot. Ambiguous replacement mappings fail generation. Pass@4 is the fraction of
tasks solved at least once in four valid attempts. Costs include valid runs only.

## CI and deployment

For PRs that change `website/` or `tasks/`, the `Website validation` job installs
locked dependencies with Node 22, runs the statistics tests, type checking and
lint, and builds the static site. The existing required `Task validation` check
also requires this website job to pass when it runs.

CI builds the committed leaderboard snapshot; it does not regenerate results or
connect to the NAS. To reproduce the production build locally:

```sh
GITHUB_PAGES_BASE_PATH='' \
NEXT_PUBLIC_SITE_URL=https://ai-infra-bench.github.io \
npm run build:pages
```

After a merge to `main`, the existing `Publish task images` workflow publishes
the website when `website/` or `tasks/` changed and any selected task image checks
succeeded. Its `publish-website` job builds `dist/client/` with an empty base path,
then uses `ROOT_PAGES_TOKEN` to publish the artifact to the `main` branch of
`ai-infra-bench/ai-infra-bench.github.io`. GitHub Pages serves that repository's
root. Opening a PR does not update the live site.
