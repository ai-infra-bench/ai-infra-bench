#!/usr/bin/env python3
import asyncio, json, os
from vllm.v1.engine.async_llm import AsyncLLM, StreamingInput
from vllm.engine.arg_utils import AsyncEngineArgs
from vllm.sampling_params import RequestOutputKind, SamplingParams

async def collect(engine, request_id, chunks, delay=0.0):
    async def stream():
        for chunk in chunks:
            yield StreamingInput(prompt=chunk)
            if delay:
                await asyncio.sleep(delay)
    rows=[]
    async for out in engine.generate(stream(), SamplingParams(max_tokens=2, temperature=0.0, ignore_eos=True, output_kind=RequestOutputKind.DELTA), request_id):
        rows.append({'request_id': out.request_id, 'finished': out.finished,
                     'tokens': [list(item.token_ids) for item in out.outputs]})
    return rows

def engine_for(model):
    return AsyncLLM.from_engine_args(AsyncEngineArgs(
        model=model, max_model_len=64, max_num_seqs=4, enforce_eager=True,
        gpu_memory_utilization=0.05, kv_cache_memory_bytes=64*1024*1024))

def validate_rows(rows, request_id):
    assert rows and rows[-1]['finished'], f'{request_id}: no terminal output'
    assert all(row['request_id'] == request_id for row in rows)
    assert all(not row['finished'] for row in rows[:-1])
    tokens=[token for row in rows for group in row['tokens'] for token in group]
    assert tokens, f'{request_id}: no generated tokens'
    return tokens

async def main():
    workload=json.loads(open(os.environ['AIB_WORKLOAD']).read())
    model=os.environ['AIB_MODEL']
    chunks=workload['chunks']
    bunched_engine=engine_for(model)
    try:
        bunched=await collect(bunched_engine,'bunched',chunks)
    finally:
        bunched_engine.shutdown()
    spaced_engine=engine_for(model)
    try:
        spaced=await collect(spaced_engine,'spaced',chunks,0.15)
    finally:
        spaced_engine.shutdown()
    bunched_tokens=validate_rows(bunched,'bunched')
    spaced_tokens=validate_rows(spaced,'spaced')
    assert bunched_tokens == spaced_tokens, 'burst and delayed input changed public output'
    concurrent_engine=engine_for(model)
    try:
        concurrent=await asyncio.gather(
            collect(concurrent_engine,'session-a',workload['session_a'],0.03),
            collect(concurrent_engine,'session-b',workload['session_b'],0.05),
        )
    finally:
        concurrent_engine.shutdown()
    concurrent_tokens=[validate_rows(rows,rid) for rows,rid in zip(concurrent,['session-a','session-b'])]
    reuse_engine=engine_for(model)
    try:
        first=await collect(reuse_engine,'reused',workload['reuse_first'])
        second=await collect(reuse_engine,'reused',workload['reuse_second'])
    finally:
        reuse_engine.shutdown()
    validate_rows(first,'reused'); validate_rows(second,'reused')
    with open(os.environ['AIB_OBSERVATIONS'],'w') as f:
        json.dump({'bunched':bunched,'spaced':spaced,'concurrent':concurrent,
                   'reuse':[first,second]},f)

if __name__=='__main__':
    asyncio.run(main())
