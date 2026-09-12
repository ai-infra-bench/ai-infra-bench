"""Validate raw runner and persistent-batch observations in the trusted parent."""
import math
EXPECTED_STAGES = ['repeated_continuation','partial_absorption','interleaved_sessions','prompt_embeddings','ordinary_new_request','sampling_refresh','mrope_refresh','pooling_refresh']
def check(raw, workload):
    assert len(raw['initial']) == 2 and len(raw['updates']) == 6
    assert raw['initial'] == {rid:v['prompt'] for rid,v in workload['initial'].items()}, 'initial prompts differ from current workload'
    expected = dict(workload['initial'])
    previous = raw['initial_snapshot']['states']
    assert set(previous) == set(expected)
    for rid, prescribed in expected.items():
        assert previous[rid]['prompt'] == prescribed['prompt']
        assert previous[rid]['outputs'] == previous[rid]['batch_outputs'] == prescribed['outputs']
        assert previous[rid]['batch_tokens'] == prescribed['prompt']
    for update, req in zip(raw['updates'], workload['updates']):
        assert update['input'] == req, 'request differs from current workload'
        rid=req['id']; observed=update['observed']; states=observed['states']
        expected[rid]=req
        assert set(states)==set(expected)
        assert set(observed['rows'])==set(expected) and len(observed['rows'])==len(expected)
        for other, before in previous.items():
            if other != rid:
                assert states[other]==before, f'unrelated session changed: {other}'
        state=states[rid]; prompt=req['prompt']; embeds=req['embeds']; length=len(prompt if prompt is not None else embeds)
        assert state['prompt']==prompt and state['embeds']==embeds
        assert state['outputs']==state['batch_outputs']==[]
        assert state['length']==state['batch_length']==state['batch_total']==length
        assert state['computed']==state['batch_computed']==req['computed']
        assert state['blocks']==req['blocks'] and state['batch_blocks']==req['blocks'][0]
        assert state['mm']==req['mm'] and state['temperature']==req['temperature']
        assert math.isclose(state['batch_temperature'],req['temperature'],abs_tol=1e-6)
        assert state['seed']==state['generator_seed']==req['seed']
        assert state['prompt_logprobs']==req['prompt_logprobs']
        assert state['batch_tokens']==prompt
        assert state['batch_embeds']==embeds
        previous=states
    assert len(raw['mrope']) == 2
    for rope, prompt in zip(raw['mrope'], workload['mrope']):
        assert rope['prompt'] == prompt
        assert rope['positions']==[prompt]*3 and rope['delta']==len(prompt)
    assert len(raw['pooling'])==3
    for step, pool in enumerate(raw['pooling']):
        prescribed = workload['pooling'][step]
        assert pool['prompt'] == pool['batch_tokens'] == prescribed['prompt']
        assert pool['length']==pool['batch_length']==len(prescribed['prompt'])
        assert pool['pooling_state_present'] and pool['batch_pooling_state_present']
        assert pool['requires_tokens']==prescribed['requires_tokens'] and pool['rows']==['pooled']
    return EXPECTED_STAGES
