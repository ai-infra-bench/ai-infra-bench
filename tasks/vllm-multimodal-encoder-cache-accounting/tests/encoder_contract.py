"""Parent-owned values and expected model inputs; no candidate imports."""
import random
import secrets


def workload(seed=None):
    rng = random.Random(secrets.randbits(128) if seed is None else seed)
    specifications = [
        (38, [(1, 15, sorted(rng.sample(range(1, 14), 5))),
              (17, 0, []), (18, 3, None), (23, 4, []), (29, 7, [0, 3, 6])]),
        (24, [(3, 12, [0, 5, 10]), (17, 4, []), (22, 0, None)]),
        (12, [(2, 4, None)]),
    ]
    requests = []
    for request_index, (length, items) in enumerate(specifications):
        tokens = [20 + request_index * 50 + p % 40 for p in range(length)]
        features = []
        for offset, span, indices in items:
            chosen = range(span) if indices is None else indices
            rows = [[rng.randrange(-1000, -10) for _ in range(16)] for _ in chosen]
            for p in chosen:
                tokens[offset + p] = 250
            features.append(dict(offset=offset, length=span, indices=indices, rows=rows))
        requests.append(dict(id=f'fresh-{request_index}', tokens=tokens, features=features))
    return {'requests': requests}


def expected(inputs):
    plain, shifted = {}, {}
    for request in inputs['requests']:
        payload = {f['offset'] + p: row for f in request['features']
                   for p, row in zip(range(f['length']) if f['indices'] is None
                                     else f['indices'], f['rows'])}
        tokens = request['tokens']
        for shift, result in [(0, plain), (1, shifted)]:
            positions = list(range(shift, len(tokens) + shift))
            result[request['id']] = {
                'positions': positions,
                'rows': [payload[p] if p in payload else
                         [tokens[p] if p < len(tokens) else 17] * 16 for p in positions],
            }
    return {'main': plain, 'eagle_main': plain, 'eagle_shifted': shifted}
