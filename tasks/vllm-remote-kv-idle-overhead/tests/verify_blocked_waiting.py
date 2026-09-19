#!/usr/bin/env python3
"""Trusted behavioral assertions. This process never imports candidate vLLM."""
import hashlib
import json
import random
import secrets
import statistics


MEMORY_BUDGET = 32 * 1024 * 1024
MEMORY_REQUESTS = 1_310_720
GROUPS = ('idle-scaling', 'mixed-idle-scaling', 'engine-lifecycle',
          'cancellation-races', 'mixed-fcfs', 'streaming-resumption',
          'ready-backpressure', 'no-connector-regression',
          'preemption-backlog-local', 'preemption-backlog-remote',
          'kv-pressure', 'nixl-prefix-lifecycle', 'retained-memory-local', 'retained-memory-remote')


def require(value, message):
    if not value:
        raise AssertionError(message)


def empty(peer):
    row = peer.call('tick')
    require(not row['scheduled'] and not row['outputs'], f'finished work reappeared: {row}')
    require(row['counts'] == [0, 0] and row['unfinished'] == 0 and not row['has_requests'],
            f'finished state incorrect: {row}')


def drain(peer, identities, *, prefix=None, expected_admission=None):
    observed = {identity: [] for identity in identities}
    if prefix:
        for identity, tokens in prefix.items(): observed[identity].extend(tokens)
    ended = {key for key, values in observed.items() if len(values) == 3}
    admitted = []
    for step in range(64):
        tokens = {identity: 103 + index * 131 + len(observed[identity])
                  for index, identity in enumerate(identities)}
        row = peer.call('tick', tokens=tokens)
        admitted.extend(row['admitted'])
        for identity, values, terminal in row['outputs']:
            require(identity in observed, f'unexpected output identity: {identity}')
            require(identity not in ended, f'duplicate output after terminal: {identity}')
            observed[identity].extend(values)
            if terminal: ended.add(identity)
        if len(ended) == len(identities): break
    wanted = {identity: [103 + index * 131 + n for n in range(3)]
              for index, identity in enumerate(identities)}
    require(observed == wanted and ended == set(identities),
            f'token/terminal lifecycle mismatch: {observed}, terminal={ended}, expected={wanted}')
    if expected_admission is not None:
        require(admitted == expected_admission, f'admission order changed: {admitted}')
    empty(peer)
    return admitted


def idle_scaling(peer, mixed):
    rows = []
    for count in (64, 1024, 8192):
        peer.call('reset', capacity=count + 1, budget=max(8192, count * 16))
        # Keep packets bounded; individual IDs and creation order vary per run.
        salt = secrets.token_hex(5)
        for first in range(0, count, 256):
            peer.call('add', items=[{'id': f'{salt}-{i}', 'remote': True}
                                   for i in range(first, min(first + 256, count))])
        initial = peer.call('tick')
        require(initial['counts'] == [0, count] and initial['unfinished'] == count,
                f'waiting requests lost: {initial}')
        require(not initial['scheduled'], 'remote work ran before readiness')
        if mixed:
            peer.call('add', items=[{'id': 'stream', 'prompt': 1, 'max_tokens': 1, 'stream': True}])
            first = peer.call('tick', tokens={'stream': 47})
            require(any(r[:2] == ['stream', [47]] for r in first['outputs']), 'stream segment output missing')
        peer.call('idle', rounds=128)
        costs = []
        rounds = 512
        for _ in range(5):
            before = peer.cpu_ns()
            observed = peer.call('idle', rounds=rounds)
            elapsed = peer.cpu_ns() - before
            require(observed['rounds'] == rounds and observed['scheduled_tokens'] == 0 and observed['admitted'] == 0,
                    f'idle round produced work: {observed}')
            require(observed['counts'] == [0, count + int(mixed)], f'idle counts changed: {observed}')
            costs.append(elapsed / rounds)
        rows.append({'requests': count, 'cpu_ns_per_tick': statistics.median(costs)})
    ratio = rows[-1]['cpu_ns_per_tick'] / max(rows[0]['cpu_ns_per_tick'], 1)
    print(json.dumps({'observation': 'idle', 'mixed': mixed, 'rows': rows, 'ratio': ratio}), flush=True)
    require(ratio < 2.7, f'idle work grows with blocked population: mixed={mixed}, ratio={ratio:.2f}')


def engine_lifecycle(peer):
    peer.call('reset', capacity=3, budget=12)
    peer.call('add', items=[{'id': 'a', 'prompt': 21, 'remote': True, 'cached': 16},
                           {'id': 'b', 'prompt': 19, 'remote': True, 'cached': 16},
                           {'id': 'c', 'prompt': 25}])
    got = {key: [] for key in 'abc'}
    ended = set()
    for step in range(32):
        ready = ['b'] if step == 5 else ['a'] if step == 9 else []
        tokens = {key: 701 + i * 71 + len(got[key]) for i, key in enumerate('abc')}
        row = peer.call('tick', ready=ready, tokens=tokens)
        require(row['executor_calls'] == 1, f'EngineCore stopped with live work: {row}')
        if step < 5:
            require('a' not in row['scheduled'] and 'b' not in row['scheduled'], 'premature remote execution')
        if step == 4:
            require(got['c'], 'local request stalled behind transfers')
        if step == 8:
            require(got['b'] and not got['a'], 'staggered readiness woke wrong request')
        for key, values, terminal in row['outputs']:
            require(key in got and key not in ended, f'unknown or repeated output: {key}')
            got[key].extend(values)
            if terminal: ended.add(key)
        if len(ended) == 3: break
    require(got == {key: [701 + i * 71 + n for n in range(3)] for i, key in enumerate('abc')},
            f'engine token lifecycle mismatch: {got}')
    require(ended == set('abc'), f'engine did not finish: {ended}')
    empty(peer)
    peer.call('add', items=[{'id': 'fresh', 'prompt': 7}])
    drain(peer, ['fresh'], expected_admission=['fresh'])


def cancellation(peer):
    for event_first in (False, True):
        peer.call('reset', capacity=4)
        identities = ['oldest', 'victim', 'survivor', 'last']
        peer.call('add', items=[{'id': i, 'remote': True} for i in identities])
        row = peer.call('tick')
        require(row['unfinished'] == 4, f'remote unfinished count wrong: {row}')
        if event_first: peer.call('tick', ready=['victim', 'survivor'])
        peer.call('abort', ids=['victim'])
        if not event_first: peer.call('tick', ready=['victim', 'survivor'])
        first = peer.call('tick', tokens={'survivor': 911})
        require(first['admitted'] == ['survivor'], f'cancelled request revived: {first}')
        require(all(x[0] != 'victim' for x in first['outputs']), f'cancelled request output: {first}')
        peer.call('abort', ids=['survivor'])
        peer.call('tick', ready=['last', 'oldest'])
        peer.call('add', items=[{'id': 'new', 'prompt': 1}])
        row = peer.call('tick')
        require(row['admitted'] == ['oldest', 'last', 'new'], f'completion/admission order changed: {row}')
        require(row['counts'] == [3, 0] and row['unfinished'] == 3, f'live request accounting wrong: {row}')
        peer.call('abort', ids=['oldest', 'last', 'new'])
        empty(peer)


def mixed_fcfs(peer):
    peer.call('reset', capacity=1, budget=20)
    peer.call('add', items=[{'id': 'fsm', 'prompt': 1, 'grammar': True},
                           {'id': 'remote', 'remote': True},
                           {'id': 'stream', 'prompt': 1, 'max_tokens': 1, 'stream': True}])
    row = peer.call('tick', tokens={'stream': 59})
    require(row['admitted'] == ['stream'], f'mixed waits blocked runnable stream: {row}')
    peer.call('add', items=[{'id': 'regular', 'prompt': 20}, {'id': 'tail', 'prompt': 1}])
    row = peer.call('tick', ready=['remote'])
    require(row['admitted'] == ['regular'], f'mixed waits blocked runnable request: {row}')
    peer.call('abort', ids=['regular'])
    peer.call('grammar', id='fsm')
    peer.call('add', items=[{'id': 'stream', 'prompt': 1, 'max_tokens': 1, 'stream': True}])
    # Capacity one makes FCFS an observable admission decision; map order is irrelevant.
    for identity in ('fsm', 'remote', 'stream', 'tail'):
        row = peer.call('plan')
        require(row['admitted'] == [identity] and set(row['scheduled']) == {identity},
                f'FCFS admission changed across blocked reasons: expected={identity}, actual={row}')
        peer.call('abort', ids=[identity])
    empty(peer)


def streaming(peer):
    for count in (3, 37):
        peer.call('reset', capacity=count + 1)
        ids = [f'waiting-{i}' for i in range(count)]
        peer.call('add', items=[{'id': i, 'remote': True} for i in ids])
        peer.call('tick')
        for token in (211, 223, 239):
            peer.call('add', items=[{'id': 'stream', 'prompt': 1, 'max_tokens': 1, 'stream': True}])
            row = peer.call('tick', tokens={'stream': token})
            require(set(row['scheduled']) == {'stream'}, f'stream did not resume: {row}')
            require(any(x[:2] == ['stream', [token]] for x in row['outputs']), f'stream token missing: {row}')
            idle = peer.call('tick')
            require(not idle['scheduled'] and not idle['outputs'], f'stream advanced without input: {idle}')
        peer.call('abort', ids=['stream'])
        require(peer.call('state')['counts'] == [0, count], 'stream abort lost remote waiters')


def backpressure(peer, remote):
    peer.call('reset', capacity=1, budget=32, connector=remote)
    identities = ['first', 'second', 'third', 'later']
    peer.call('add', items=[{'id': name, 'prompt': 20 + i, 'remote': remote, 'cached': 16}
                           for i, name in enumerate(identities[:3])])
    if remote:
        row = peer.call('tick')
        require(row['counts'] == [0, 3] and row['unfinished'] == 3 and row['has_requests'],
                f'pending transfers absent from engine accounting: {row}')
        row = peer.call('tick', ready=identities[:3])
        require(row['executor_calls'] == 1, 'engine failed to receive KV completion while all requests waited')
    peer.call('add', items=[{'id': 'later', 'prompt': 7}])
    drain(peer, identities, expected_admission=identities)


def preemption(peer, remote):
    for waiting_count in (3, 11):
        peer.call('reset', capacity=1, connector=remote)
        peer.call('add', items=[{'id': 'active', 'prompt': 19, 'remote': remote, 'cached': 16}])
        if remote:
            peer.call('tick')
            peer.call('tick', ready=['active'])
            peer.call('local', ids=['active'])
        first = peer.call('tick', tokens={'active': 103})
        require(any(x[:2] == ['active', [103]] for x in first['outputs']), 'active request failed to generate')
        ids = ['active'] + [f'queued-{i}' for i in range(waiting_count)]
        peer.call('add', items=[{'id': i, 'prompt': 2} for i in ids[1:]])
        for token in (104, 105):
            row = peer.call('preempt')
            require(row['reset'] and row['counts'] == [0, len(ids)], f'preemption lost requests: {row}')
            row = peer.call('tick', tokens={'active': token})
            require(set(row['scheduled']) == {'active'}, f'preempted stream lost FCFS position: {row}')
        drain(peer, ids, prefix={'active': [103, 104, 105]})



def kv_pressure(peer):
    # Every request fits by itself. Each tuple varies prefix coverage, prompt,
    # cache size and decode growth; no admission algorithm is prescribed.
    for blocks, prompts, prefixes, budgets in (
        (6, [64], [32], [1]),
        (6, [64, 64], [32, 32], [1, 1]),
        (10, [64, 64], [32, 32], [1, 1]),
        (6, [64, 64], [32, 32], [3, 3]),
        (8, [80, 64, 48], [48, 32, 16], [2, 3, 2]),
        (6, [17, 64], [0, 32], [33, 2]),
    ):
        peer.call('reset', capacity=4, budget=256, blocks=blocks)
        identities = [f'pressure-{i}' for i in range(len(prompts))]
        peer.call('add', items=[{'id': rid, 'prompt': prompt, 'remote': bool(cached),
                                 'cached': cached, 'max_tokens': budget}
                                for rid, prompt, cached, budget in zip(identities, prompts, prefixes, budgets)])
        observed = {rid: [] for rid in identities}
        ended = set()
        for step in range(96):
            tokens = {rid: 401 + 19*i + len(observed[rid]) for i, rid in enumerate(identities)}
            row = peer.call('tick', tokens=tokens, auto_ready=True)
            for rid, values, terminal in row['outputs']:
                require(rid in observed and rid not in ended, f'pressure duplicated an output: {row}')
                observed[rid].extend(values)
                if terminal: ended.add(rid)
            if len(ended) == len(identities): break
        expected = {rid: [401 + 19*i + n for n in range(budgets[i])]
                    for i, rid in enumerate(identities)}
        require(observed == expected and ended == set(identities),
                f'KV pressure prevented completion: blocks={blocks}, outputs={observed}, finished={ended}')
        empty(peer)
        peer.call('add', items=[{'id': 'after-pressure', 'prompt': 7}])
        drain(peer, ['after-pressure'], expected_admission=['after-pressure'])

    for finish_before_abort in (False, True):
        peer.call('reset', capacity=2, budget=128, blocks=6)
        peer.call('add', items=[{'id': name, 'prompt': 64, 'remote': True,
                                 'cached': 32, 'max_tokens': 3}
                                for name in ('cancel-pressure', 'survivor')])
        peer.call('tick', auto_ready=finish_before_abort)
        peer.call('abort', ids=['cancel-pressure'])
        observed = []
        terminals = 0
        for step in range(64):
            row = peer.call('tick', auto_ready=True, tokens={'survivor': 821 + len(observed)})
            for identity, tokens, terminal in row['outputs']:
                require(identity == 'survivor', f'cancelled work returned under pressure: {row}')
                observed.extend(tokens)
                terminals += bool(terminal)
            if terminals: break
        require(observed == [821, 822, 823] and terminals == 1,
                f'cancellation failed to release usable KV capacity: {observed}')
        empty(peer)



def nixl_prefix_lifecycle(peer):
    rows = peer.call('nixl')['observations']
    expected = [('prime', None), ('full-hit', False), ('cancel', False),
                ('full-hit', True), ('cancel', True), ('read', None)]
    require([(r['kind'], r.get('notification_fails')) for r in rows] == expected,
            'NIXL lifecycle scenarios did not complete')
    for row in rows:
        require(row['counts'] == [0, 0], f'NIXL request remained live: {row}')
        if row['kind'] == 'prime':
            wanted = [['nixl-prime', [299], True]]
        elif row['kind'] == 'full-hit':
            wanted = [['nixl-hit-' + str(row['notification_fails']), [301], True]]
        elif row['kind'] == 'cancel':
            wanted = [['nixl-after-cancel-' + str(row['notification_fails']), [307], True]]
        else:
            wanted = [['nixl-read', [311], True]]
        require(row['outputs'] == wanted, f'NIXL output/cleanup changed: {row}')
    print(json.dumps({'observation': 'nixl-prefix-lifecycle', 'rows': rows}), flush=True)


def retained_memory(peer, remote):
    peer.call('reset', capacity=1, connector=remote)
    salt = secrets.randbelow(1 << 30)
    total = 0
    baseline = None
    observations = []
    for end in (256, 4096, 16384, 65536, 327680, MEMORY_REQUESTS):
        while total < end:
            count = min(8192, end - total)
            row = peer.call('churn', start=total, count=count, salt=salt, remote=remote)
            expected = hashlib.sha256()
            for i in range(total, total + count):
                out = [f'{salt}-{i}', [100 + (i * 17 + salt) % 49000], True]
                expected.update(json.dumps(out, separators=(',', ':')).encode() + b'\n')
            require(row['digest'] == expected.hexdigest() and row['tokens'] == count and row['terminals'] == count,
                    f'churn client outputs changed: {row}')
            require(row['counts'] == [0, 0] and row['unfinished'] == 0 and not row['has_requests'],
                    f'completed workload remained live: {row}')
            total += count
        current = peer.memory_bytes()
        if baseline is None: baseline = current
        growth = max(0, current - baseline)
        observation = {'completed': total, 'live_python_bytes': current, 'growth_bytes': growth}
        observations.append(observation)
        print(json.dumps({'observation': 'retained-memory', 'remote': remote, **observation}), flush=True)
        require(growth <= MEMORY_BUDGET, f'retained Python memory exceeds 32 MiB: remote={remote}, {observation}')
    empty(peer)


def run_suite(peer, emit):
    cases = [(GROUPS[0], lambda: idle_scaling(peer, False)),
             (GROUPS[1], lambda: idle_scaling(peer, True)),
             (GROUPS[2], lambda: engine_lifecycle(peer)),
             (GROUPS[3], lambda: cancellation(peer)),
             (GROUPS[4], lambda: mixed_fcfs(peer)),
             (GROUPS[5], lambda: streaming(peer)),
             (GROUPS[6], lambda: backpressure(peer, True)),
             (GROUPS[7], lambda: backpressure(peer, False)),
             (GROUPS[8], lambda: preemption(peer, False)),
             (GROUPS[9], lambda: preemption(peer, True)),
             (GROUPS[10], lambda: kv_pressure(peer)),
             (GROUPS[11], lambda: nixl_prefix_lifecycle(peer)),
             (GROUPS[12], lambda: retained_memory(peer, False)),
             (GROUPS[13], lambda: retained_memory(peer, True))]
    for name, case in cases:
        case()
        emit(name)
