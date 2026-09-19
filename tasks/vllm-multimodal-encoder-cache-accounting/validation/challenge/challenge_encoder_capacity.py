"""Independent capacity geometry and runtime/profile storage challenge."""
from pathlib import Path
import json
import sys
import types

TESTS = Path(__file__).resolve().parents[2] / 'tests'
if not TESTS.is_dir():
    TESTS = Path('/tests')
namespace = types.ModuleType('_encoder_independent_capacity')
namespace.__file__ = str(TESTS / 'encoder_runtime.py')
sys.modules[namespace.__name__] = namespace
for name in ('encoder_runtime.py', 'encoder_storage.py', 'encoder_capacity_worker.py', 'encoder_scenarios.py'):
    exec(compile((TESTS / name).read_text(), str(TESTS / name), 'exec'), namespace.__dict__)
observed = []
with namespace.Runtime() as runtime:
    for length, indices in [(137, [3, 9, 23, 37, 52, 66, 81, 104, 129]),
                            (53, [4, 13, 27, 39, 48]), (11, None), (17, []), (0, [])]:
        spec = namespace.specification(length, indices)
        pair = runtime.pair(spec, chunk=2)
        try:
            count = len(spec['rows'])
            allowed = (max(2, count),) if count else (0, 2)
            budgets = [int(pair.scheduler.max_num_encoder_input_tokens),
                       int(pair.scheduler.encoder_cache_manager.cache_size)]
            runner_budget = int(pair.runner.mm_budget.get_encoder_budget())
            assert all(b in allowed for b in budgets) and runner_budget == min(budgets)
            observed.append(dict(span=length, rows=count, scheduler=budgets, runner=runner_budget))
        finally:
            pair.close()
    for count in (32, 80):
        spec, processor = namespace.video_processor(runtime, count, frames=4, prefix=7)
        actual = namespace.capacity_for(runtime, spec, processor)
        assert actual == {'scheduler': [count, count], 'runner': count}, actual
        observed.append(dict(video_rows=count, **actual))
    rows = [[float(301 + i + j) for j in range(16)] for i in range(6)]
    storage = [namespace.observe_storage(runtime, n, rows) for n in (17, 113, 2053)]
    baseline = storage[0]['payload_bytes']
    assert all(s['payload_bytes'] <= baseline + max(256, baseline // 2) for s in storage[1:]), storage
print(json.dumps({'cases': observed, 'storage': storage, 'pass': True}, indent=2))
