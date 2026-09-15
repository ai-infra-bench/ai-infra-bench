> Since v0.0.5, the mandatory offline process suite lives in `../../tests/process/`. This directory retains the earlier supplemental experiments; current scoring evidence is in `../v005-review.md`.

# Model migration: actual process and disk acceptance

This supplementary acceptance suite starts the shipped `dsh web` CLI, calls its
HTTP Session Remote, runs the real Bash tool, shuts the host down, and starts a
new host over the same JSONL/Zstandard persistence directory. The restored
session receives no seed, copied events, caller allowance, or destination
selection from the test parent.

It supplements the v0.0.4 verifier's 32 tests. It is **not yet a reward-bearing
verifier**, and does not change the recorded v0.0.4 scores/pass@4. Its parent and
candidate currently run under the same container UID; before promotion to
scoring, isolate the trusted parent, freeze a new verifier image, and rerun
artifact-transfer and completion controls through Harbor.

## Deterministic acceptance

Only model forward computation is substituted. A stateful HTTP/SSE provider
checks each real SDK request before returning the next response; routing,
TokenMeter, Agent loop, Remote validation, persistence, cold restoration and
shell execution are production implementations.

| Case | Observed behavior |
| --- | --- |
| `main` | Read two invoice files through separate Bash calls; checked migration; real host exit/restart; paired history and plaintext thinking reach Responses; another Bash call writes a correct report; destination-native call replay survives. |
| `empty-same` | Caller cap 73; migrate an empty session; restart; checked select the same destination; actual request still uses 73, not default 256. |
| `empty-third` | Same sequence, then a third destination; actual request uses 73, not default 384. |
| `reject` | A destination with insufficient context is refused without generation; after restart the original route can continue using saved tool results. |
| `defaults` | No caller cap; after migration/restart use destination default 256; another migration uses third-model default 384. |

All five also exercise an independent sibling session and compare deployment
settings/catalog and the logical persisted event prefix. Dedicated existing
unit tests retain responsibility for exact rejection-time event immutability,
races, all collision families, disabled behavior and capacity boundaries.

`create-caller.mjs` is an input producer using public `ctx.agents.create` and the
shipped minimal preset. It supplies an explicit caller allowance only in the
first host. The second overlay omits this plugin completely. It does not
implement migration, write a selection record, or reconstruct restored state.
The public Session create Remote does not accept a caller allowance at Base;
this avoids requiring a candidate-specific new creation/selection parameter.

Run inside a disposable built checkout/container:

```bash
python3 /absolute/path/process-e2e/run.py \
  --root /workspace/deepseek-harness \
  --out /tmp/process-acceptance
```

Use a fresh output directory. `--cases baseline` proves ordinary Base
boot/request/persist/restart/resume before testing the new feature. Base assets
were built with `npm run build`. Each complete candidate patch was then applied
and host/client runtime assets rebuilt with the repository's `tsdown` commands.
This is runtime bundling, **not a passing repository typecheck**: the full Oracle
`build:lib` attempt found type errors in its submitted test fixtures, recorded
separately in the run evidence.

The container owns the outer isolation boundary. `DSH_PERMISSION_MODE` is set
to `danger-full-access` because its image lacks a usable nested OS sandbox;
real shell commands still execute in each case's disposable workspace. No
production sandbox implementation is replaced.

## Live acceptance

`live-proxy.py` forwards actual requests and complete SSE responses without
rewriting history or generating scripted output. It keeps API keys on the
credential-owning machine, applies the AIDP `extra.session_id` affinity header,
and captures credential-free wire evidence. One proxy serves one acceptance
attempt; do not mix attempts in its evidence collection. It must be used only
on the private test network and stopped afterwards.

```bash
python3 live-proxy.py --env-file /private/existing.env --key-index 1 \
  --port 20235 --out /tmp/live-proxy-evidence

python3 run-live.py --root /workspace/deepseek-harness \
  --proxy http://PRIVATE_TEST_HOST:20235 \
  --source-api openai-responses --source-model gpt-6-astra \
  --destination-model gpt-5.6-sol --out /tmp/live-acceptance
```

The current credential mapping matches the existing experiment setup:
`GPT56_EXPERIMENT_API_KEYS[1]` for GPT-6 and `[0]` for GPT-5.6. Both request
`high`. The declared 65,536-token context and 16,384 output ceiling are
conservative test configuration, not measurements of the actual model limits.

The first live attempt used the supplied `v2/crawl` Completions endpoint. It
rejected GPT-6 function tools with `reasoning_effort=high` (HTTP 400), so that
cross-protocol live path is not certified. Responses-to-Responses acceptance
is recorded separately. Missing source reasoning is explicitly reported and
must not be called a passing real plaintext-reasoning migration.

Native encrypted reasoning requires stable upstream affinity. The first
Responses attempt lacked that header and failed; it is retained as a failed
attempt. The corrected GPT-6-to-GPT-5.6 attempt passed with fixed per-model affinity
across the host restart. A further reverse attempt did expose source plaintext
reasoning, but the target rejected it. Identical-payload probes confirm both
GPT-6 and GPT-5.6 reject nonempty reasoning.content on these AIDP routes, even
after adding the required summary field. See the review for the exact scope.
No automatic retries or silent rerolls are performed by this suite.

### Additional AIDP models (2026-09-12)

`ali-deepseek-v4-pro` and `Minimax-M3` use the existing experiment key at
`--key-index` (1 in this run). Their AIDP product routes reject Responses with
HTTP 400 / `-1026`, although both support Chat Completions with high reasoning
and tools. This observation is about these gateway routes, not every endpoint
offered by their model providers.

For Chat-to-Chat acceptance, set `--destination-api openai-completions`; the
default remains `openai-responses`. DeepSeek's Chat profile explicitly disables
the developer role and store field and uses `max_tokens`, through the existing
DSH compatibility settings. Absolute workspace file paths avoid depending on a
model's assumed working directory. The live test also requires the report's
contents to return through a real tool result.

Both migration directions passed after that configuration correction. Initial
developer-role failures are retained. Chat uses the SDK's ordinary foreign
history projection: the available reasoning arrived as assistant text, not in
`reasoning_content`. The result records both representations separately; a Chat
pass does **not** certify the opt-in Responses reasoning extension. The source
SSE reasoning fragments are joined before comparing decoded strings, avoiding
JSON escaping and chunk-boundary artifacts in the evidence check.

See `../extra-models-live-review-20260912.md` for all attempts and evidence.

### Direct Chat reasoning contract experiment

`chat-contract.py` tests the real endpoint contract independently of DSH. It
starts a source Python process, performs actual inference and two invoice-file
reads, persists the complete portable assistant messages, and waits for process
exit. A new destination process sends the exact saved history, including
`reasoning_content` on its original assistant messages. The destination must
write and read back a correct report without rereading the invoices. Amounts
are generated for each attempt; report validation checks the three data lines
and permits an optional terminal newline.

```bash
python3 chat-contract.py \
  --source-model ali-deepseek-v4-pro --destination-model Minimax-M3 \
  --env-file /private/existing.env \
  --out /tmp/fresh-chat-contract
```

Swap the two model names to test the reverse direction. Both directions passed
the corrected observer with five actual high-effort requests each. All initial
attempts are retained, including a strict-terminal-newline failure. The proxy,
SDK and DSH are absent from this experiment: it demonstrates acceptance of
portable reasoning by the tested AIDP Chat endpoints, **not** that the DSH SDK
already preserves that field. The actual DSH process suite above remains
necessary. See `../chat-contract-review-20260912.md` for results, limits and the
subsequent comparison with official DeepSeek, MiniMax and OpenAI documentation.

### Strict real DSH Chat acceptance

The later full-DSH run is recorded in `../dsh-chat-real-review-20260912.md`.
Apply `chat-reasoning.patch` on top of the historical v0.0.4 Oracle `feature.patch` (archived in `../history/v004-before-v005.tar.gz`)
and rebuild the host assets before enabling the new Chat adapter option.
The patch changes DSH's provider configuration and request projection; it does
not patch the test proxy or replace pi-ai, tools, persistence, or the Agent loop.

```bash
python3 run-live.py --root /workspace/deepseek-harness \
  --source-model ali-deepseek-v4-pro --source-api openai-completions \
  --destination-model Minimax-M3 --destination-api openai-completions \
  --require-reasoning-field --chat-reasoning-text \
  --proxy http://PRIVATE_TEST_HOST:20263 --out /tmp/fresh-dsh-chat-live
```

Use a separate proxy and output directory for the reverse direction. The strict
flag requires actual nonempty source reasoning and checks its exact text and
association with source tool calls on every destination request. Reasoning in
ordinary assistant text does not pass. CLI exit, cold disk recovery, subsequent
real file writes and tool verification remain mandatory. Report comparison
accepts an optional terminal newline while requiring all three data lines.

Without the adapter patch/option the strict real DSH baseline failed exactly at
the reasoning field assertion. With it both directions passed. The original
32 tests and four additional real-SDK Chat checks in `../chat-reasoning.spec.ts`
also passed. These are supplemental validation runs; the frozen task's formal
verifier and scoring have not been changed. Live inference requires a connected
validation environment; these runs used Docker host networking.

## Evidence and controls

See `../process-e2e-review-20260912.md` and the accompanying compressed evidence.
Each case records parent-observed child PIDs/exits, actual requests, Remote
results, decoded on-disk records, raw Zstandard artifacts and the report file.
Browser login tokens are redacted from host logs; credentials are never copied.

`mutate-control.py` creates two disposable, complete Oracle mutations:

- `volatile-selection`: keep the new route in memory but omit its durable event;
  the test must fail because the first generated request after restart uses A.
- `early-success-exit`: call `process.exit(0)` inside checked migration;
  the parent must fail because the Remote call and required workflow never finish.

A successful child exit or an existing output file alone cannot pass acceptance.
These controls establish ordinary behavioral sensitivity, not adversarial
resistance of this supplementary runner.
