# Python frontend comparison for the selected verifier scope

Reference: vLLM `32601ef7a1ce8aaa6d777778435ec499248906fb`, resolved from main
on September 5, 2026, with `anthropic==1.3.0` and PyTorch `2.13.0+cpu`.
This is an immutable reference. It never enters the canonical agent image.

The hardened suite collects 93 cases: 21 SDK fixture controls, 53 Anthropic
behavior cases and 19 native API/backend controls. Ten separate checks use a
real CPU model runner with dummy weights. Actual measured results and exact
inputs are recorded in `results.json` and `../e2e-evidence.json`.

| Current file | Cases |
| --- | ---: |
| test_sdk_fixture.py | 21 |
| test_rust_sdk_matrix.py | 24 |
| test_rust_request_matrix.py | 21 |
| test_rust_historical_regressions.py | 9 |
| test_real_qwen_backend.py | 18 |

Compared with the 77-case suite at benchmark commit `497a5b6`, this adds six
SDK max_tokens cases, eight OpenAI generation-parameter cases, and two native
tool-none cases. The fixed SDK no longer directly exposes temperature/top_p/top_k
on Messages.create; those options are tested only as existing OpenAI behavior.
The engines truncate scripted tokens at the actual received max_tokens and
report length termination. Both parallel-tool success cases now request 128
tokens for their 66-token script. The tool-none candidate predicate no longer
requires a particular internal tool mode or parallel flag.

The instruction retains the previously selected broad SDK objective. Coverage
still omits the user-excluded hosted/search/reference types, thinking request
and signature semantics, engine errors/error envelopes, authentication and
media. Neither the reference nor a full score proves complete SDK compatibility.

## Boundary and reproduction

`pytest_plugin.py` replaces each test module's launcher with `PythonServer`.
The requests and assertions run unchanged. The complete pinned Python serving
application runs actual input/output processing, Qwen rendering/tokenization,
parsers, routing and HTTP/SSE. `ScriptedCore` replaces EngineCore generation
and transport with Qwen token IDs, preserving the received generation limit.
No HTTP response is rewritten. The separate CPU checks execute real dummy weights.

Use image `ai-infra-bench/reference-python-anthropic:main-32601ef7a1ce`, ID
`sha256:161033171dcf370e0ec4e8d46ce44ac60441fe3dbfb60a87db51ef5f9b68793f`.
The full source and installed package snapshot are identified in `results.json`
and `installed-packages.txt`.

Mount this directory at `/probe`, current `tests/` at `/tests`, and a writable
directory at `/logs`, with network disabled. Run `bash /probe/run.sh` and run
`python /tests/python_frontend_control.py` with `--shm-size 1g` for CPU controls.
`record_results.py` checks frozen hashes and collected counts before writing
the measured record.

Three reference-only patches under `controls/` qualify the new predicates:

- `ignore-generation-limit.patch`: deliberately replaces the Anthropic
  generation limit with 512; the six SDK limit cases must fail.
- `alternative-tool-none-normalization.patch`: sets the unused internal
  parallel flag to false when tools are disabled; all tested behavior must pass.

- `alternative-named-tool-normalization.patch`: represents a named selection
  as a required call from a singleton allowed tool set; the named-tool case must pass.

Apply each patch separately to a clean reference source and run the same tests.
They are not Rust solutions and never enter the agent image or reward verifier.
The native counterparts are declared in `../ci-cases.json`; their full reward
remains zero because the Anthropic routes are absent, while the qualification
record checks their native case results separately.

Pre-hardening results are archived under `../history/497a5b6/`. The original
115-case audit remains under `../history/f4163bc/`. No complete Rust Oracle
or complete alternative implementation is claimed.
