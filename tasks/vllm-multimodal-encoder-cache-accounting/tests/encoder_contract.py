"""Independent prompt/embedding contract; no candidate imports in the scorer."""
import random
import secrets


def workload(seed=None):
    rng = random.Random(secrets.randbits(128) if seed is None else seed)
    first = sorted(rng.sample(range(2, 13), rng.randrange(3, 7)))
    specs = [(0, 15, first), (16, 3, None), (20, 4, []),
             (25, 11, sorted(rng.sample(range(1, 10), 3))), (36, 0, [])]
    features = []
    for offset, length, indices in specs:
        count = length if indices is None else len(indices)
        features.append(dict(offset=offset, length=length, indices=indices,
                             rows=[[rng.randrange(-100000, 100000) for _ in range(4)]
                                   for _ in range(count)]))
    windows = [[a, b] for a, b in zip(range(37), range(1, 38))]
    return dict(features=features, windows=windows,
                cached_windows=[[a, b] for a, b in [sorted(rng.sample(range(38), 2)) for _ in range(12)]])


def selected(feature):
    indices = feature['indices']
    return list(range(feature['length'])) if indices is None else indices


def payload(features, start, end):
    positions = {f['offset'] + p: row for f in features
                 for p, row in zip(selected(f), f['rows'])}
    return dict(mask=[p in positions for p in range(start, end)],
                rows=[positions[p] for p in range(start, end) if p in positions])


def expected(inputs):
    features = inputs['features']
    counts = [len(f['rows']) for f in features]
    capacity = sum(counts)
    allocations = [dict(admit=True, free=0, short_admit=False if n else None) for n in counts]
    n = counts[0]
    empty_end = selected(features[0])[0]
    budgets = [(0,n), (n-1,n), (n,0), (n,n-1), (n,n)]
    empty = [[[],empty_end,b,[]] for c,b in budgets]
    nonempty = [[([0] if c>=n and b>=n else []), (1 if c>=n and b>=n else 0),
                 (b-n if c>=n and b>=n else b), []] for c,b in budgets]
    seen=set();chain=[]
    for a,b in inputs['windows']:
        ids=[i for i,f in enumerate(features) if i not in seen
             and any(a <= f['offset']+p < b for p in selected(f))]
        seen.update(ids)
        chain.append(dict(schedule=[ids,b-a,capacity-sum(counts[i] for i in ids),[]],
                          free=capacity-sum(counts[i] for i in seen), **payload(features,a,b)))
    # Main-model tokens and EAGLE's shifted tokens both need encoder outputs.
    lookahead = [[[0], 2, 0, []], [[], 1, n, []], [[], 1, 0, []],
                 [[], 1, n-1, []], [[], 2, 0, []], [[0], 1, 0, []]]
    return dict(lookahead=lookahead, allocations=allocations, empty=empty, nonempty=nonempty,
                profile={'scheduler':[max(1,n),max(1,n)], 'runner':max(1,n)}, eviction=dict(free=0, freed=['fresh-0-item-0']),
                chain=chain, cached=[payload(features,a,b) for a,b in inputs['cached_windows']])
