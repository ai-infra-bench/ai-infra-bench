"""Exercise public generation without requiring a named chunk class."""

import asyncio
from collections import abc
import inspect
import json
import os
from pathlib import Path
import typing

from vllm.engine.arg_utils import AsyncEngineArgs
from vllm.sampling_params import RequestOutputKind, SamplingParams
from vllm.v1.engine.async_llm import AsyncLLM


class PromptValue(str):
    """Text also usable by an unannotated duck-typed prompt interface."""

    @property
    def prompt(self):
        return str(self)

    sampling_params = None


def chunk_factory(generate):
    """Use the declared public element type, never a prescribed symbol or module."""
    try:
        annotation = typing.get_type_hints(generate).get("prompt")
    except (NameError, TypeError, AttributeError):
        annotation = None

    def element(value):
        origin = typing.get_origin(value)
        if origin in (abc.AsyncGenerator, abc.AsyncIterable, abc.AsyncIterator):
            return typing.get_args(value)[0]
        for arg in typing.get_args(value):
            found = element(arg)
            if found is not None:
                return found
        return None

    declared = element(annotation)
    if declared is str:
        return str
    if typing.is_typeddict(declared):
        required = list(declared.__required_keys__)
        if len(required) == 1:
            return lambda prompt: {required[0]: prompt}
    if (inspect.isclass(declared) and declared not in (str, dict, object)
            and not typing.is_typeddict(declared)):
        try:
            parameters = list(inspect.signature(declared).parameters.values())
            first = next(p for p in parameters if p.kind not in
                         (p.VAR_POSITIONAL, p.VAR_KEYWORD))
            if first.kind == first.KEYWORD_ONLY:
                return lambda prompt: declared(**{first.name: prompt})
            return lambda prompt: declared(prompt)
        except (TypeError, ValueError, StopIteration):
            pass
    return PromptValue


async def collect(engine, case, make_chunk):
    seen = 0
    completed_segments = 0
    progress = asyncio.Condition()

    async def stream():
        for index, prompt in enumerate(case["chunks"]):
            yield make_chunk(prompt)
            if case["mode"] == "delayed":
                async with progress:
                    await progress.wait_for(lambda: completed_segments > index)

    prompt = case["chunks"][0] if case["mode"] == "ordinary" else stream()
    params = SamplingParams(
        max_tokens=case["budget"], temperature=0.0, ignore_eos=case["ignore_eos"],
        stop_token_ids=case["stop_ids"], output_kind=RequestOutputKind.DELTA,
    )
    rows = []
    async for out in engine.generate(prompt, params, case["request_id"]):
        outputs = [{
            "index": item.index, "tokens": list(item.token_ids),
            "finish_reason": item.finish_reason, "stop_reason": item.stop_reason,
        } for item in out.outputs]
        rows.append({"request_id": out.request_id, "finished": out.finished,
                     "outputs": outputs})
        async with progress:
            seen += sum(len(item["tokens"]) for item in outputs)
            completed_segments += sum(item["finish_reason"] is not None for item in outputs)
            progress.notify_all()
    assert seen == sum(case["segment_lengths"]), (
        f"{case['request_id']}: lost or duplicated output: {seen} tokens"
    )
    return {"ended": True, "rows": rows}


async def main():
    workload = json.loads(Path(os.environ["AIB_WORKLOAD"]).read_text())
    engine = AsyncLLM.from_engine_args(AsyncEngineArgs(
        model=os.environ["AIB_MODEL"], dtype="float32", max_model_len=128,
        max_num_seqs=4, enforce_eager=True, gpu_memory_utilization=0.05,
        kv_cache_memory_bytes=64 * 1024 * 1024,
    ))
    make_chunk = chunk_factory(engine.generate)
    cases = workload["cases"]
    results = {}
    try:
        for name, case in cases.items():
            if name == "concurrent_b":
                continue
            print(f"public case: {name}", flush=True)
            if name == "concurrent_a":
                pair = await asyncio.wait_for(asyncio.gather(
                    collect(engine, cases["concurrent_a"], make_chunk),
                    collect(engine, cases["concurrent_b"], make_chunk),
                ), timeout=90)
                results["concurrent_a"], results["concurrent_b"] = pair
            else:
                results[name] = await asyncio.wait_for(
                    collect(engine, case, make_chunk), timeout=90)
            print(f"completed public case: {name}", flush=True)
    finally:
        engine.shutdown()
    Path(os.environ["AIB_OBSERVATIONS"]).write_text(json.dumps({"cases": results}))


if __name__ == "__main__":
    asyncio.run(main())
