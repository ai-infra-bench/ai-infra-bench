from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI


def _completion(index: int, token_ids: list[int], finish_reason=None, logprobs=None):
    from vllm.outputs import CompletionOutput

    return CompletionOutput(
        index=index,
        text="",
        token_ids=token_ids,
        cumulative_logprob=None,
        logprobs=logprobs,
        finish_reason=finish_reason,
    )


def _request_output(
    request_id: str,
    prompt_token_ids: list[int],
    outputs,
    *,
    finished: bool,
    num_cached_tokens: int | None = None,
):
    from vllm.outputs import RequestOutput

    return RequestOutput(
        request_id=request_id,
        prompt=None,
        prompt_token_ids=prompt_token_ids,
        prompt_logprobs=None,
        outputs=outputs,
        finished=finished,
        metrics=None,
        lora_request=None,
        encoder_prompt=None,
        encoder_prompt_token_ids=None,
        num_cached_tokens=num_cached_tokens,
    )


class FakeEngine:
    errored = False
    dead_error = RuntimeError("engine unavailable")

    async def is_tracing_enabled(self) -> bool:
        return False

    def generate(self, engine_input, sampling_params, request_id, **_kwargs):
        from vllm.logprobs import Logprob
        from vllm.sampling_params import RequestOutputKind

        prompt = list(engine_input["prompt_token_ids"])
        scenario = prompt[0] if prompt else 0
        count = sampling_params.n
        streaming = sampling_params.output_kind == RequestOutputKind.DELTA

        async def results():
            if not streaming:
                if scenario == 901:
                    cumulative_steps = [[71], [71]]
                elif scenario == 902:
                    cumulative_steps = [[71], [71], [71, 72, 73], [71, 72, 73, 74]]
                else:
                    cumulative_steps = [[71], [71, 72, 73], [71, 72, 73, 74]]
                for step_index, tokens in enumerate(cumulative_steps):
                    final = step_index == len(cumulative_steps) - 1
                    outputs = []
                    for i in range(count):
                        current = [token + i * 100 for token in tokens]
                        top = None
                        if sampling_params.logprobs is not None:
                            top = [
                                {token: Logprob(logprob=-0.1, rank=1)}
                                for token in current
                            ]
                        outputs.append(
                            _completion(
                                i,
                                current,
                                ("error" if scenario == 901 else "length")
                                if final
                                else None,
                                top,
                            )
                        )
                    yield _request_output(
                        request_id,
                        prompt,
                        outputs,
                        finished=final,
                        num_cached_tokens=2 if scenario == 904 else None,
                    )
                    await asyncio.sleep(0.04)
                return

            if scenario == 901:
                yield _request_output(
                    request_id,
                    prompt,
                    [_completion(0, [71])],
                    finished=False,
                )
                await asyncio.sleep(0.04)
                yield _request_output(
                    request_id,
                    prompt,
                    [_completion(0, [], "error")],
                    finished=True,
                )
                return

            steps = [[71], [72, 73], [74]]
            if scenario == 902:
                steps.insert(1, [])
            for step_index, tokens in enumerate(steps):
                final = step_index == len(steps) - 1
                outputs = []
                for index in range(count):
                    current = [token + index * 100 for token in tokens]
                    top = None
                    if sampling_params.logprobs is not None:
                        top = [
                            {token: Logprob(logprob=-0.1, rank=1)}
                            for token in current
                        ]
                    outputs.append(
                        _completion(
                            index,
                            current,
                            "length" if final else None,
                            top,
                        )
                    )
                yield _request_output(
                    request_id,
                    prompt,
                    outputs,
                    finished=final,
                    num_cached_tokens=2 if scenario == 904 else None,
                )
                await asyncio.sleep(0.04)

        return results()


class FakeModels:
    lora_requests: dict = {}

    def model_name(self, _lora_request) -> str:
        return "local-token-engine"


class FakeRender:
    async def preprocess_completion(self, request, **_kwargs):
        return ({"prompt_token_ids": list(request.token_ids)},)


def build_handler():
    from vllm.entrypoints.serve.disagg.serving import ServingTokens

    handler = ServingTokens.__new__(ServingTokens)
    handler.engine_client = FakeEngine()
    handler.models = FakeModels()
    handler.openai_serving_render = FakeRender()
    handler.force_no_detokenize = False
    handler.request_logger = None
    handler.enable_prompt_tokens_details = True
    handler.enable_log_outputs = False

    async def check_model(_request):
        return None

    async def trace_headers(_headers):
        return None

    handler._check_model = check_model
    handler._maybe_get_adapters = lambda *_args, **_kwargs: None
    handler._log_inputs = lambda *_args, **_kwargs: None
    handler._get_trace_headers = trace_headers
    return handler


def create_app() -> FastAPI:
    from vllm.entrypoints.serve.disagg.api_router import router

    app = FastAPI()
    app.state.args = SimpleNamespace(tokens_only=False)
    app.state.enable_server_load_tracking = False
    app.state.serving_tokens = build_handler()
    app.state.engine_client = app.state.serving_tokens.engine_client
    app.include_router(router)
    return app


app = create_app()
