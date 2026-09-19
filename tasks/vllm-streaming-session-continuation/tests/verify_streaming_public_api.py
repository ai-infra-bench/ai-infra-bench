"""Exercise public generation without requiring a named chunk class."""

import asyncio
import json
import os
from pathlib import Path

from streaming_input_adapter import chunk_factory

from vllm.engine.arg_utils import AsyncEngineArgs
from vllm.sampling_params import RequestOutputKind, SamplingParams
from vllm.v1.engine.async_llm import AsyncLLM


async def collect(engine, case, make_chunk):
    completed_segments = 0
    progress = asyncio.Condition()

    async def stream():
        for index, prompt in enumerate(case["chunks"]):
            yield make_chunk(prompt)
            if case["mode"] == "delayed":
                async with progress:
                    await progress.wait_for(lambda: completed_segments > index)

    prompt = case["chunks"][0] if case["mode"] == "ordinary" else stream()
    sampling_options = dict(
        max_tokens=case["budget"], temperature=0.0, ignore_eos=case["ignore_eos"],
        stop_token_ids=case["stop_ids"],
        include_stop_str_in_output=case["include_stop"],
    )
    if case["output_kind"] == "delta":
        sampling_options["output_kind"] = RequestOutputKind.DELTA
    # Ordinary cumulative cases exercise the existing public default.
    params = SamplingParams(**sampling_options)
    rows = []
    async for out in engine.generate(prompt, params, case["request_id"]):
        outputs = [{
            "index": item.index, "tokens": list(item.token_ids),
            "text": item.text,
            "finish_reason": item.finish_reason, "stop_reason": item.stop_reason,
        } for item in out.outputs]
        rows.append({"request_id": out.request_id, "finished": out.finished,
                     "outputs": outputs})
        async with progress:
            completed_segments += sum(item["finish_reason"] is not None for item in outputs)
            progress.notify_all()
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
