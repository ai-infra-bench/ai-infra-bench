# ai-infra-bench/vllm-implement-derender-rust-serving

Implement the two derender endpoints in vLLM's native Rust frontend. The
[instruction](instruction.md) is the user's frozen query. The task covers
non-streaming text, reasoning/tool parsing, logprobs/usage, and supported
plain-text chunked processing with continuation on independent server
instances. Derender runs without model weights or an inference engine.

## Environment

- vLLM Base: `e473e9036f979d546830aece9855027049faf0ba`.
- CPU only: 8 CPUs, 48 GiB RAM, no runtime network access, 10-hour agent budget.
- Rust 1.95, Python 3.12.11, torch 2.13.0+cpu, transformers 5.16.1,
  tokenizers 0.23.2; exact dependencies are in `environment/lock/`.
- Qwen configuration, tokenizer and template metadata at
  `/opt/models/qwen-template`, pinned to
  `6a9e13bd6fc8f0983b9b99948120bc37f49c13e9`. No model tensors are included.
- Retained image:
  `ai-infra-bench/vllm-implement-derender-rust-serving:base-e473e9036f97`.
- Image ID:
  `sha256:b7e97708ef2d0f3455034d533f9a9a3e80eaa106ba72b5af568b2ccbc87ec1c1`.

The Dockerfile is a task-scoped hardened expansion of the merged Anthropic
Rust-serving task's all-in-one environment. It builds from an empty context,
requires the Rust executable, and vendors Cargo dependencies for offline work.

## Verification

The verifier builds the native executable and sends actual TCP HTTP requests
to its production render-only server. Model output token IDs are ordinary
derender inputs. The tokenizer, parser, request/response code and independent
server processes run for real.

Reward is 1 only when all 87 unique HTTP cases pass without errors or skips,
and the server/chat crate suites finish with at least 673 passes and no failed,
ignored or filtered cases. State is carried opaquely between independent
servers. Long deferred text and null/omitted/empty token deltas are covered.

| Current functional qualification | HTTP passed / failed / errors | Reward |
| --- | ---: | ---: |
| alternative-native-decoder-replay | 87 / 0 / 0 | 1 |
| base | 9 / 78 / 0 | 0 |
| discard-client-state | 48 / 39 / 0 | 0 |
| discard-logprobs | 84 / 3 / 0 | 0 |
| ignore-prompt-usage | 81 / 6 / 0 | 0 |
| omit-terminal-flush | 61 / 26 / 0 | 0 |
| oracle | 87 / 0 / 0 | 1 |
| plain-text-only | 79 / 8 / 0 | 0 |
| reject-long-returned-state | 79 / 8 / 0 | 0 |
| reject-null-stream-delta | 83 / 4 / 0 | 0 |

Fresh Oracle and alternative Harbor trials score 1 with no framework errors.
Each correct binary also passes two complete HTTP stability rounds and six
independent growing-state/empty-event challenges. Native runtime files and their
existing Python-forwarding CI control remain unchanged; this functional round
does not rerun isolation probes. Earlier 49/67-case evidence is historical.

HTTP coverage uses the supplied Qwen vocabulary/template and Hermes/Qwen3
parser configurations. Chunked reasoning/tool parsing, chunked logprobs and
GPU/model-performance validation are outside this supported scope. See the
[contract](validation/contract-matrix.md), [review](validation/review-report.md)
and [measured evidence](validation/e2e-evidence.json) for details.

## Layout

```text
instruction.md              Frozen user query
task.toml                   Source, resources and execution budgets
environment/                Self-contained Dockerfile, lock and image identity
solution/                   Qualified native Rust patch and application script
tests/                      HTTP verifier and existing-API regression gates
validation/                 Contract, provenance, controls and measured results
```

## Run

From the benchmark repository root, prepare a copy using the retained image:

```bash
derender_case_dir=$(mktemp -d)
python3 .github/scripts/task_ci.py prepare-case \
  --task vllm-implement-derender-rust-serving \
  --image ai-infra-bench/vllm-implement-derender-rust-serving:base-e473e9036f97 \
  --case oracle --output "$derender_case_dir"
harbor run --path "$derender_case_dir" --agent oracle --env docker \
  --jobs-dir jobs --job-name derender-oracle \
  --n-concurrent 1 --cpus ignore --memory ignore --delete --yes
```

For a real-agent trial, set `DERENDER_EVAL_MODEL` to the intended provider/model
identifier and use the same prepared task:

```bash
harbor run --path "$derender_case_dir" --agent terminus-2 \
  --model "$DERENDER_EVAL_MODEL" --env docker --jobs-dir jobs
```

To rebuild the environment without copying task files into it:

```bash
derender_build_context=$(mktemp -d)
docker buildx build --load --provenance=false \
  --tag ai-infra-bench/vllm-implement-derender-rust-serving:base-e473e9036f97 \
  --file tasks/vllm-implement-derender-rust-serving/environment/Dockerfile \
  "$derender_build_context"
```

The reference patch is derived from the public Rust derender proposal and
adapted to this Base; it is kept out of the agent image. See
[solution provenance](validation/solution-provenance.md). Real-agent difficulty
has not been measured by this qualification work.
