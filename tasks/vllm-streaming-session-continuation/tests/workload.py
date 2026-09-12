"""Generate continuation records in the grading parent, independent of vLLM."""
import json
import os
import random


def load_workload():
    with open(os.environ['AIB_WORKLOAD']) as stream:
        return json.load(stream)


def make_workload(seed):
    rng = random.Random(seed)
    ids = [f'session-{rng.getrandbits(96):024x}' for _ in range(3)]
    tokens = lambda n: [rng.randrange(1, 31000) for _ in range(n)]
    first, second = tokens(3), tokens(2)
    out_first, out_second = tokens(3), tokens(1)
    initial = {ids[0]: {'prompt': first, 'outputs': out_first},
               ids[1]: {'prompt': second, 'outputs': out_second}}
    embeds = [[rng.randrange(-128, 128) / 16 for _ in range(6)] for _ in range(5)]
    updates = []
    for step, (rid, prompt, embedding) in enumerate([
        (ids[0], first + out_first[:1], None),
        (ids[1], second + out_second + tokens(1), None),
        (ids[0], None, embeds),
        (ids[0], first + out_first[:1] + tokens(2), None),
        (ids[2], tokens(3), None),
        (ids[1], second + tokens(2), None),
    ]):
        updates.append({'id':rid, 'prompt':prompt, 'embeds':embedding,
                        'mm':[f'mm-{rng.getrandbits(64):016x}'],
                        'temperature':0.2+step/10, 'seed':rng.randrange(1, 2**31),
                        'prompt_logprobs':2 if step%2 == 0 else None,
                        'blocks':[[rng.randrange(1, 100), rng.randrange(100, 200)]],
                        'computed':len(prompt if prompt is not None else embedding)-1})
    return {'initial':initial, 'updates':updates, 'rope_id':ids[1],
            'mrope':[tokens(7), tokens(9)],
            'pooling':[{'prompt':tokens(4+step), 'requires_tokens':bool(step%2),
                        'blocks':[[rng.randrange(1, 100)]]} for step in range(3)]}
