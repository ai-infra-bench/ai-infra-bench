# Website

The homepage includes the leaderboard and task catalog. The production site is
published at <https://infrabench.ai/> using GitHub Pages.

## Local development

From `website/`:

```sh
npm ci
npm run dev
```

Task pages are generated from the repository's `tasks/` directory. Leaderboard
results come from the committed `app/generated/leaderboard.json` snapshot.

The selected layout is documented in [SELECTED_DESIGN.md](SELECTED_DESIGN.md).
The homepage shows the comparison chart, Results and six tasks per page.
The standalone task catalogue shows eight tasks per page with search, Work type
and Domain filters. Only recorded results appear in the chart and table.

Run the full website test suite with `npm run test:website` (chart geometry,
label density and focus, task filtering/pagination, and archive statistics).

## Updating leaderboard results

Keep full Harbor trial directories in the external archive, preserving their
original names. The default archive root is
`/mnt/nas/ai-infra-bench/leaderboard`:

```text
archive/<release>/<task>/<model>/<effort>/<agent-version>/<original-trial-name>/
manifests/<release>/<task>/<model>/<effort>/<agent-version>/<original-trial-name>.json
```

For a new release, archive completed Harbor jobs from the repository root,
then update `leaderboard-source.json` to point to that release's two directories:

```sh
python3 tools/leaderboard/archive_harbor_trials.py \
  --release new-release \
  /path/to/harbor-job
```

The archiver verifies copied files with a tree checksum. It retains invalid runs
with exclusion reasons instead of counting them toward scores. It requires
Python 3.11+ and `rsync`. Use `--root` to choose another archive location.

Then regenerate the public snapshot from `website/`:

```sh
npm run generate:leaderboard
npm run test:leaderboard
```

The current source is configured in `leaderboard-source.json`. The archive was
renamed to `archive/v0-17task`, while its complete manifests remain under
`manifests/2026-09-08`. These directories are deliberately mapped independently;
no NAS rename or raw-result modification is required. For another release,
update that file, or pass `--source <file>`. Explicit `--root`, `--release`,
`--archive-dir` and `--manifest-dir` options retain the legacy CLI workflow.
When importing a new release, keep its archive and manifest mapping in sync.

Generation checks archive/manifest coverage, duplicate entries, trial identity,
binary rewards, trajectory completion and recorded resource metrics before
writing the snapshot. Unlisted or missing directories fail generation instead
of silently dropping data. Excluded trials remain excluded, including API and
environment failures and aborted trajectories.

Review and commit `app/generated/leaderboard.json` together with any website
changes. Raw trial directories and private trajectories stay outside the Git
repository. Model IDs are displayed verbatim.

Pass average is the fraction of successful valid trials. Its displayed standard
deviation is the sample standard deviation (`ddof=1`) of the four repetition
pass rates. Each repetition's denominator is its actual observed task count;
missing attempts are not imputed as failures. Attempts are ordered by execution start within each task;
a later infrastructure replacement fills the invalid original's repetition
slot. Ambiguous replacement mappings fail generation. Incomplete task groups
require verified missing repetition slots in the source configuration. For the
current Sol xhigh run, the missing fourth mooncake-hybrid-pd-layout attempt was
an API-rate-limit failure absent from the NAS release. Its repetition task
counts are `[17, 17, 17, 16]`; its pooled pass average uses 67 valid trials, while
sample standard deviation uses those four observed-denominator repetition
rates. The two statistics thus use explicit, different weighting when counts
are unequal. Filling that archived attempt later automatically restores four
complete rounds. No extra partial-state badge is shown on the website.

The retained JSON Pass@4 field is the fraction of
tasks solved at least once, and is only an exact pass@4 when all attempts are
present; it is not displayed in the current website. Costs include valid runs only.

## CI and deployment

For PRs that change `website/` or `tasks/`, the `Website validation` job installs
locked dependencies with Node 22, runs the full website test suite, type checking and
lint, and builds the static site. The existing required `Task validation` check
also requires this website job to pass when it runs.

CI builds the committed leaderboard snapshot; it does not regenerate results or
connect to the NAS. To reproduce the production build locally:

```sh
GITHUB_PAGES_BASE_PATH='' \
NEXT_PUBLIC_SITE_URL=https://infrabench.ai \
npm run build:pages
```

After a merge to `main`, the existing `Publish task images` workflow publishes
the website when `website/` or `tasks/` changed and any selected task image checks
succeeded. Its `publish-website` job builds `dist/client/` with an empty base path,
then uses `ROOT_PAGES_TOKEN` to publish the artifact to the `main` branch of
`ai-infra-bench/ai-infra-bench.github.io`. GitHub Pages serves that repository's
root. Opening a PR does not update the live site.

### Custom domain

`infrabench.ai` is the canonical domain. Keep `public/CNAME` in the source:
the publication job replaces the generated site's branch, so configuring the
domain only in the destination repository is not persistent. Both website CI
and publication verify that the emitted `dist/client/CNAME` contains this domain.

Configure the custom domain in the **ai-infra-bench.github.io repository's**
Pages settings before pointing DNS at GitHub. In Cloudflare, use these records
with proxy status **DNS only** and automatic TTL:

| Type | Name | Content |
| --- | --- | --- |
| A | @ | 185.199.108.153 |
| A | @ | 185.199.109.153 |
| A | @ | 185.199.110.153 |
| A | @ | 185.199.111.153 |
| CNAME | www | ai-infra-bench.github.io |

Remove only conflicting website records for `@` or `www`; retain unrelated
mail and verification records. Do not add wildcard records or a redirect back
to github.io. After DNS validation and certificate issuance, enable **Enforce
HTTPS** in Pages settings. GitHub recommends also verifying ownership under
the organization's Settings > Pages and retaining its DNS TXT challenge.

See [GitHub's custom domain guide](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site).

### Legacy `.html` URL redirects

GitHub Pages serves the static `.html` files directly and cannot emit HTTP 301
responses. To permanently redirect legacy `.html` URLs, deploy the optional
Cloudflare Worker in the repository `cloudflare/` directory and attach it to the `infrabench.ai/*` route:

```sh
cd cloudflare
npx wrangler deploy
```

The Worker redirects `/index.html`, `/leaderboard.html`, `/tasks.html`, and task
URLs ending in `.html` to their clean URL while passing all other requests
through to GitHub Pages. The `infrabench.ai` DNS record must be proxied through
Cloudflare for the route to run. Keep the DNS and Pages custom-domain settings
otherwise unchanged.
