# Latest Python frontend comparison

This is a separate diagnostic reference environment. The scored task's Base
commit, canonical image, instruction, and all 115 pytest cases are unchanged.
The complete Chinese failure review is in [failures.md](failures.md).

## Results

Reference source: vLLM main `e962733e08d10f7ca65dac4df99e116460b8b174`.
Client: `anthropic==1.3.0`. PyTorch: `2.13.0+cpu`.
Test source: benchmark commit `f4163bcf3166fd1799341d0bbc5defa8afea65b5`.

| Existing test file | Passed | Failed |
| --- | ---: | ---: |
| test_sdk_fixture.py | 35 | 0 |
| test_rust_sdk_matrix.py | 18 | 5 |
| test_rust_request_matrix.py | 26 | 15 |
| test_rust_historical_regressions.py | 9 | 0 |
| test_real_qwen_backend.py | 7 | 0 |
| Total | 95 | 20 |

There were zero errors and zero skips. The 35 SDK-fixture cases do not target
the Python server. The 80 server cases therefore passed 60 and failed 20; after
excluding eight existing-route/backend controls, the 72 Anthropic cases passed
52 and failed 20. A separate real CPU dummy-weight run passed all ten existing
Python frontend controls.

## Boundary

`pytest_plugin.py` replaces each test module's server factory with `PythonServer`.
It does not replace, suppress, xfail, or alter requests/assertions. The adapter
starts the actual latest `vllm serve` Python application and observes converted
requests, renderer parameters, and EngineCore input. The semantic observation
records contain actual Python values under the capture interface expected by
the tests; they do not synthesize missing options or rewrite responses.

The substituted component is the EngineCore producer/transport, implemented by
`ScriptedCore`. Real `AsyncLLM`, its input/output processors, model/tokenizer
configuration, Qwen Jinja rendering, tokenization, tool/reasoning parsers,
Anthropic/OpenAI handlers, authentication, and HTTP/SSE paths execute from the
latest source tree. Generated text is encoded with the real Qwen tokenizer and
delivered as deterministic `EngineCoreOutput` token chunks. This does not test
GPU/model computation or EngineCore IPC. The separate ten-control run does use
the real CPU runner and dummy weights.

`probe_details.py` separately diagnoses thinking configuration, missing thinking
signature, x-api-key versus Bearer authentication, and swallowed stream errors.
`probe_negative_requests.py` replays request failures to save raw HTTP bodies.
Those supplementary probes are not counted as extra scored tests.

## Reproduce

Use the retained reference-only image
`ai-infra-bench/reference-python-anthropic:main-e962733e08d1`, image ID
`sha256:fd803711169b26d1a40d0d0dea108912b5457b74bf4c12f44f8ba3e5254adc59`.
It was built from the full upstream archive for the source SHA above using
`Dockerfile.reference`; it is not a mixture of selected new frontend files and
old vLLM source. Key runtime source files were compared byte-for-byte with that
archive, and `uv pip check --system` passed. The exact installed package snapshot
is in `installed-packages.txt`.

Mount this directory at `/probe`, the task's `tests/` at `/tests`, and an output
directory at `/logs`; use network disabled. Run `bash /probe/run.sh`. Expected
diagnostic pytest status for the recorded revision is 1, with 95 passed and 20
failed. Run supplementary probes with `PYTHONPATH=/probe:/tests`:

```sh
python /probe/probe_details.py --output /logs/failure-details.json
python /probe/probe_negative_requests.py --output /logs/negative-responses.json
```

The standalone ten-check CPU run uses `python /tests/python_frontend_control.py`
in a separate container with `--shm-size 1g`. The first setup attempt with Docker's
64 MiB default failed before serving because the latest CPU worker required
160 MiB shared memory. The rerun with adequate shared memory passed; this setup
failure is not included among the 20 API incompatibilities.

The canonical benchmark Base remains
`sha256:535bb97cac5f23043e7874dfde5037c1fee6d76d180d1da2e6e8217ca161d125`.
Latest source and these diagnostic files must never enter that agent image.
No complete conforming Rust implementation or Oracle pass is claimed.

## Decisions

The recommendations concern the discussed narrower vLLM capability scope. They
are not scoring changes: ten failure cases retain their behavior objectives,
four should be rewritten or merged, and six unsupported-feature success
requirements should be removed. See the full per-case reasoning before changing
the instruction or verifier. A failing latest-Python result alone is neither a
reason to keep a test nor a reason to remove it.
