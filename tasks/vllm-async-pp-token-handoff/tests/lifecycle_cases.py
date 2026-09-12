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
