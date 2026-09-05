# Python frontend comparison for the selected verifier scope

Reference: vLLM main resolved on September 5, 2026 to
`32601ef7a1ce8aaa6d777778435ec499248906fb`, with `anthropic==1.3.0` and
PyTorch `2.13.0+cpu`. This is an immutable reference, not a moving latest claim.

The final run passed **77/77**, with zero failures, errors or skips. The separate
real CPU dummy-weight controls passed **10/10**.

| Current file | Passed | Failed |
| --- | ---: | ---: |
| test_sdk_fixture.py | 21 | 0 |
| test_rust_sdk_matrix.py | 18 | 0 |
| test_rust_request_matrix.py | 21 | 0 |
| test_rust_historical_regressions.py | 9 | 0 |
| test_real_qwen_backend.py | 8 | 0 |

The current suite has 77 tests: 21 SDK fixture controls and 56 server cases,
including 47 Anthropic cases and nine native API/backend controls. Exact run
results and input hashes are recorded in [results.json](results.json).

The instruction retains the user's original broad SDK-compatibility objective.
Scoring intentionally omits unsupported SDK/tool/cloud types and the twelve
remaining protocol/error/authentication failure cases at the user's request.
It does not prove full compatibility with all functionality named in the SDK.

Relative to the original 115 cases, the selected suite removes ten request-success
variants, three unsupported/irrelevant count variants, fourteen fixture-only
expectations, and twelve protocol/error/authentication cases. It adds one native
OpenAI reasoning control with thinking explicitly enabled. Custom-tool definitions
no longer require input_examples or other unsupported options. Ordinary tool
result text, tool JSON fragmentation, concurrency, structured output and prompt
counting remain covered.

The original 95-pass/20-failure audit and its complete per-case explanation are
preserved under [history](../history/f4163bc/latest_python/). Those historical
failures were used to select coverage; they are not current failing test results.
No claim is made that the excluded bugs have been fixed upstream.

## Boundary and reproduction

`pytest_plugin.py` replaces only each test module's server launcher with
`PythonServer`; requests and assertions execute unchanged. The full pinned
`vllm serve` application runs real AsyncLLM input/output processing, Qwen
rendering/tokenization, tool/reasoning parsers, routing and HTTP/SSE conversion.
`ScriptedCore` supplies actual Qwen token IDs and replaces EngineCore generation
and transport. No HTTP response is rewritten. GPU/model computation and
EngineCore IPC are outside this comparison. A separate ten-control run executes
the real CPU runner with dummy weights.

Use image `ai-infra-bench/reference-python-anthropic:main-32601ef7a1ce`, ID
`sha256:161033171dcf370e0ec4e8d46ce44ac60441fe3dbfb60a87db51ef5f9b68793f`.
`Dockerfile.reference` builds it from the complete upstream archive. Source
hashes and exact package versions are retained in `results.json` and
`installed-packages.txt`; the reference dependency consistency check passed.

Mount this directory at `/probe`, current `tests/` at `/tests`, and a writable
output directory at `/logs`, with network disabled. Run `bash /probe/run.sh`.
Run `python /tests/python_frontend_control.py` with `--shm-size 1g` for the
separate real CPU controls. `record_results.py` consumes the retained artifact
paths and validates frozen input hashes and collection counts before writing
evidence. Its `python-current.xml`/log inputs are the artifacts from `run.sh`.

The canonical agent image and July Base are unchanged. Latest source and these
comparison scripts remain outside that image. No complete Rust solution or
Oracle pass is claimed.
