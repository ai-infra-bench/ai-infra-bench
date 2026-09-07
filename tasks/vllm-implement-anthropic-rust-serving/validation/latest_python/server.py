"""Run the actual Python frontend with scripted EngineCore outputs.

Only the EngineCore producer/transport is substituted. AsyncLLM, its input and
output processors, the real Qwen renderer/tokenizer, route handlers, tool and
reasoning parsers, and HTTP/SSE serialization execute from the reference vLLM
checkout. The observers do not modify requests or responses.
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
import functools
import json
import os
from pathlib import Path
from types import SimpleNamespace

import msgspec

from vllm.renderers.hf import HfRenderer
from vllm.renderers.online_renderer import OnlineRenderer
from vllm.v1.engine import EngineCoreOutput, EngineCoreOutputs, FinishReason
from vllm.v1.engine.core_client import EngineCoreClient
from vllm.v1.metrics.stats import PrefillStats


CURRENT_REQUEST = ContextVar("python_probe_chat_request", default=None)


def append_record(path: str, value: dict) -> None:
    with Path(path).open("a") as output:
        output.write(json.dumps(value, ensure_ascii=False) + "\n")


original_render_chat = OnlineRenderer.render_chat


@functools.wraps(original_render_chat)
async def observed_render_chat(self, request, **kwargs):
    token = CURRENT_REQUEST.set(request)
    try:
        return await original_render_chat(self, request, **kwargs)
    finally:
        CURRENT_REQUEST.reset(token)


OnlineRenderer.render_chat = observed_render_chat
original_render_messages = HfRenderer.render_messages_async


@functools.wraps(original_render_messages)
async def observed_render_messages(self, messages, params):
    result = await original_render_messages(self, messages, params)
    request = CURRENT_REQUEST.get()
    append_record(
        os.environ["AI_INFRA_SERVER_RENDER_CAPTURE_FILE"],
        {
            "chat_request": request.model_dump(mode="json")
            if request is not None
            else None,
            "template_kwargs": params.chat_template_kwargs,
            "prompt": result[1].get("prompt"),
        },
    )
    return result


HfRenderer.render_messages_async = observed_render_messages


class ScriptedCore:
    def __init__(self, *, renderer, **kwargs):
        self.tokenizer = renderer.get_tokenizer()
        self.resources = SimpleNamespace(engine_dead=False)
        self.engine_ranks_managed = [0]
        self.outputs = asyncio.Queue()
        self.response_index = 0
        self.script = json.loads(os.environ["AI_INFRA_SERVER_OUTPUTS_JSON"])
        self.chunk_sizes = json.loads(os.environ["AI_INFRA_SERVER_CHUNK_SIZES_JSON"])
        self.cached_tokens = int(os.environ["AI_INFRA_SERVER_CACHED_TOKENS"])
        self.finish_reason = FinishReason[
            os.environ["AI_INFRA_SERVER_FINISH_REASON"].upper()
        ]
        self.stop_reason = os.environ.get("AI_INFRA_SERVER_STOP_TEXT")
        self.tasks = set()
        self.aborted = set()

    async def add_request_async(self, request):
        prompt_ids = request.prompt_token_ids or []
        append_record(
            os.environ["AI_INFRA_SERVER_CAPTURE_FILE"],
            {
                "request_id": request.request_id,
                "external_req_id": request.external_req_id,
                "prompt_token_ids": prompt_ids,
                "prompt": self.tokenizer.decode(prompt_ids, skip_special_tokens=False),
                "sampling_params": msgspec.to_builtins(request.sampling_params),
                "reasoning_parser_kwargs": request.reasoning_parser_kwargs,
            },
        )
        text = self.script[self.response_index % len(self.script)]
        self.response_index += 1
        tokens = self.tokenizer.encode(text, add_special_tokens=False)
        limit = request.sampling_params.max_tokens
        hit_limit = len(tokens) >= limit
        tokens = tokens[:limit]
        task = asyncio.create_task(
            self.emit(
                request.request_id,
                prompt_ids,
                tokens,
                FinishReason.LENGTH if hit_limit else self.finish_reason,
                None if hit_limit else self.stop_reason,
            )
        )
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def emit(self, request_id, prompt_ids, tokens, finish_reason, stop_reason):
        offset = 0
        index = 0
        while offset < len(tokens):
            if request_id in self.aborted:
                return
            size = (
                (self.chunk_sizes[index] if index < len(self.chunk_sizes) else 1)
                if self.chunk_sizes
                else len(tokens)
            )
            chunk = tokens[offset : offset + max(1, size)]
            stats = None
            if offset == 0:
                stats = PrefillStats(
                    num_prompt_tokens=len(prompt_ids),
                    num_cached_tokens=self.cached_tokens,
                    num_local_cached_tokens=self.cached_tokens,
                )
            await self.outputs.put(
                EngineCoreOutputs(
                    outputs=[
                        EngineCoreOutput(
                            request_id=request_id,
                            new_token_ids=chunk,
                            prefill_stats=stats,
                        )
                    ]
                )
            )
            offset += len(chunk)
            index += 1
            # Permit output processing and concurrent requests between chunks.
            await asyncio.sleep(0)
        if request_id not in self.aborted:
            await self.outputs.put(
                EngineCoreOutputs(
                    outputs=[
                        EngineCoreOutput(
                            request_id=request_id,
                            new_token_ids=[],
                            finish_reason=finish_reason,
                            stop_reason=stop_reason,
                        )
                    ],
                    finished_requests={request_id},
                )
            )

    async def get_output_async(self):
        return await self.outputs.get()

    async def abort_requests_async(self, request_ids):
        self.aborted.update(request_ids)

    async def get_supported_tasks_async(self):
        return ("generate",)

    async def reset_mm_cache_async(self):
        pass

    async def reset_prefix_cache_async(self, *args, **kwargs):
        return True

    async def reset_encoder_cache_async(self):
        pass

    def dp_engines_running(self):
        return False

    def shutdown(self, timeout=None):
        for task in self.tasks:
            task.cancel()


EngineCoreClient.make_async_mp_client = staticmethod(
    lambda **kwargs: ScriptedCore(**kwargs)
)


if __name__ == "__main__":
    from vllm.entrypoints.cli.main import main

    main()
