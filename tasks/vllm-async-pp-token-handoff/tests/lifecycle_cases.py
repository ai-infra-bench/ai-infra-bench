"""Behavioral lifecycle cases using production scheduler interfaces.

Inputs are independent of the candidate's placeholder representation. Only
scheduled work, externally returned tokens, completion and subsequent progress
are assertions; internal counters are not scored.
"""
from collections import deque

from vllm.sampling_params import SamplingParams
from vllm.v1.request import Request
from vllm.v1.outputs import ModelRunnerOutput
from task_fixtures import build_scheduler


def scheduler_lifecycle(model):
    results = []
    for async_mode, pp_size in [(True, 2), (False, 2), (True, 1), (False, 1)]:
        scheduler = build_scheduler(model, async_scheduling=async_mode,
                                    pipeline_parallel_size=pp_size,
                                    max_model_len=128, max_num_seqs=4, max_num_batched_tokens=8)
        prompts = {'short': [31, 32, 33], 'long': list(range(41, 62))}
        limits = {'short': 4, 'long': 7}
        emitted = {key: [] for key in prompts}
        # Simulated arithmetic/sampling uses an independently counted stream;
        # scheduling, accounting and output collection are production code.
        cursors = dict.fromkeys(prompts, 0)
        scheduled_positions = dict.fromkeys(prompts, 0)
        pending = deque()
        for key, prompt in prompts.items():
            scheduler.add_request(Request(request_id=key, prompt_token_ids=prompt,
                sampling_params=SamplingParams(max_tokens=limits[key], ignore_eos=True),
                pooling_params=None, eos_token_id=None))
        rounds = 0
        while scheduler.get_num_unfinished_requests() or pending:
            rounds += 1
            assert rounds <= 80, 'scheduler failed to finish bounded workload'
            step = scheduler.schedule()
            ids = list(step.num_scheduled_tokens)
            samples = []
            for key in ids:
                scheduled_positions[key] += step.num_scheduled_tokens[key]
                if scheduled_positions[key] >= len(prompts[key]):
                    samples.append([101 + 100 * (key == 'long') + cursors[key]])
                    cursors[key] += 1
                else:
                    samples.append([])
            if ids:
                pending.append((step, ModelRunnerOutput(req_ids=ids,
                    req_id_to_index={key:i for i,key in enumerate(ids)},
                    sampled_token_ids=samples)))
            # Keep two batches in flight for async PP; also drain at starvation
            # and completion. A separate re-entry test rejects unnecessary gaps.
            depth = 2 if async_mode and pp_size == 2 else 1
            if pending and (len(pending) >= depth or not ids):
                scheduled, output = pending.popleft()
                returned = scheduler.update_from_output(scheduled, output)
                for batch in returned.values():
                    for item in batch.outputs:
                        emitted[item.request_id].extend(item.new_token_ids)
            elif not ids and not pending:
                raise AssertionError('unfinished requests stranded without work')
        expected = {key: list(range(101 + 100 * (key == 'long'),
                                    101 + 100 * (key == 'long') + limits[key]))
                    for key in prompts}
        assert emitted == expected, (emitted, expected)
        assert not scheduler.schedule().num_scheduled_tokens, 'finished requests rescheduled'
        # A fresh request after draining tests that completed ownership/accounting
        # does not strand a new workload.
        scheduler.add_request(Request(request_id='fresh', prompt_token_ids=[17, 19],
            sampling_params=SamplingParams(max_tokens=1, ignore_eos=True),
            pooling_params=None, eos_token_id=None))
        step = scheduler.schedule()
        assert set(step.num_scheduled_tokens) == {'fresh'}
        scheduler.update_from_output(step, ModelRunnerOutput(req_ids=['fresh'],
            req_id_to_index={'fresh':0}, sampled_token_ids=[[313]]))
        assert scheduler.get_num_unfinished_requests() == 0
        results.append({'async':async_mode, 'pp':pp_size, 'outputs':emitted, 'rounds':rounds})
    return results


def compaction_round(rank, invoke):
    import torch
    from worker_fixtures import make_runner, WORKLOADS, model_inputs_in_request_order, output_tokens_by_request
    prompts = {'finish': list(range(11, 19)), 'long': list(range(41, 78))}
    ids = list(prompts)
    sampled = torch.tensor([[311], [419]], dtype=torch.int32, device='cuda') if rank == 1 else None
    # The second generated token completes the leading request. Meanwhile the
    # long request has entered the cached-request update path with prompt left.
    runner = make_runner(ids, [False, True], sampled, prompts=prompts,
                         budgets={'finish': 2}, warmup_rounds=1)
    workload = WORKLOADS[runner]
    output = invoke(runner, is_sender=rank == 1)
    if rank == 1:
        materialized = output.get_output() if hasattr(output, 'get_output') else output
        assert output_tokens_by_request(materialized) == {'finish': [311], 'long': []}
        output = materialized
    workload.collect(output)
    chunks = []
    while workload.positions['long'] < len(prompts['long']):
        position = workload.positions['long']
        workload.execute_next()
        assert 'finish' not in workload.step.num_scheduled_tokens
        actual = model_inputs_in_request_order(runner, workload.step, ['long']).cpu().tolist()
        expected = prompts['long'][position:workload.positions['long']]
        # Agree on the assertion before either rank enters another sampling or
        # collection round. A token mismatch must not strand the other rank in
        # the test's own output-collection collective.
        import torch.distributed as dist
        from vllm.distributed.parallel_state import get_pp_group
        failures = [None, None]
        failure = None if actual == expected else (
            'prompt_corrupted_after_compaction', rank, position, actual, expected)
        dist.all_gather_object(failures, failure, group=get_pp_group().cpu_group)
        assert not any(failures), failures
        chunks.extend(actual)
        # Complete each real execute/sample/collection cycle before moving on.
        workload.collect(invoke(runner, is_sender=rank == 1, require_collective=False))
    return {'remaining_prompt': chunks, 'completed_removed': True}


def prefill_progress(rank, invoke):
    import torch
    import torch.distributed as dist
    from datetime import timedelta
    from worker_fixtures import make_runner, next_inputs, output_tokens_by_request
    prompts = {'a': list(range(11, 35)), 'b': list(range(41, 72))}
    ids = list(prompts)
    sampled = torch.tensor([[313], [421]], dtype=torch.int32, device='cuda') if rank == 1 else None
    runner = make_runner(ids, [True, True], sampled, prompts=prompts)
    control = dist.new_group([0, 1], backend='gloo', timeout=timedelta(seconds=30))
    signal = torch.tensor([1], dtype=torch.int32)
    if rank == 1:
        try:
            dist.recv(signal, src=0, group=control)
        except RuntimeError as exc:
            raise AssertionError("earlier stage did not advance while final sampling was withheld") from exc
    output = invoke(runner, is_sender=rank == 1, require_collective=False)
    if rank == 0:
        actual = next_inputs(runner, ids)
        assert actual == prompts['a'][8:16] + prompts['b'][8:16], actual
        dist.send(signal, dst=1, group=control)
    else:
        output = output.get_output() if hasattr(output, 'get_output') else output
        assert output_tokens_by_request(output) == {'a': [], 'b': []}
        next_inputs(runner, ids)
    dist.destroy_process_group(control)
    return {'earlier_stage_prepared_next_chunk': True}


def idle_last_stage(rank, invoke):
    import torch
    from worker_fixtures import make_runner, WORKLOADS
    sampled = torch.tensor([[101]], dtype=torch.int32, device='cuda') if rank == 1 else None
    runner = make_runner(['done'], [False], sampled, budgets={'done': 1})
    workload = WORKLOADS[runner]
    workload.collect(invoke(runner, is_sender=rank == 1))
    assert workload.scheduler.get_num_unfinished_requests() == 0
    workload.execute_next()
    assert not workload.step.num_scheduled_tokens
    result = invoke(runner, is_sender=rank == 1, require_collective=False)
    if result is not None:
        result = result.get_output() if hasattr(result, 'get_output') else result
        assert not result.req_ids and not result.sampled_token_ids
    return {'idle_completed': True}


def synchronous_runner(rank, invoke):
    import torch
    from worker_fixtures import make_runner, next_inputs, WORKLOADS, output_tokens_by_request
    ids = ['left', 'right']
    sampled = torch.tensor([[313], [421]], dtype=torch.int32, device='cuda') if rank == 1 else None
    runner = make_runner(ids, [False, False], sampled, async_mode=False)
    output = runner.sample_tokens(None)
    if rank == 1:
        assert output_tokens_by_request(output) == {'left': [313], 'right': [421]}
    WORKLOADS[runner].collect(output)
    actual = next_inputs(runner, ids[::-1])
    assert actual == [421, 313], ('synchronous_next_input', actual)
    return {'synchronous_outputs_preserved': True}
