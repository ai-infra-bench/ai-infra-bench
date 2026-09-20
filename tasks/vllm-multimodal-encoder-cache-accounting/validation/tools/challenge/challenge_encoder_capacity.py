"""Independent capacity geometry and runtime/profile storage challenge."""
from pathlib import Path
import json
import sys
import traceback
import types


def main():
    stage = 'setup'
    try:
        tests = next((parent / 'tests' for parent in Path(__file__).resolve().parents
                      if (parent / 'tests/encoder_runtime.py').is_file()), Path('/tests'))
        namespace = types.ModuleType('_encoder_independent_capacity')
        namespace.__file__ = str(tests / 'encoder_runtime.py')
        sys.modules[namespace.__name__] = namespace
        for name in ('encoder_runtime.py', 'encoder_storage.py', 'encoder_capacity_worker.py',
                     'encoder_scenarios.py'):
            exec(compile((tests / name).read_text(), str(tests / name), 'exec'), namespace.__dict__)
        observed = []
        with namespace.Runtime() as runtime:
            stage = 'capacity_behavior'
            for length, indices in [(137, [3, 9, 23, 37, 52, 66, 81, 104, 129]),
                                    (53, [4, 13, 27, 39, 48]), (11, None), (17, []), (0, [])]:
                spec = namespace.specification(length, indices)
                observed.append(dict(span=length, **namespace.capacity_for(runtime, spec)))
            stage = 'video_capacity_behavior'
            for count in (32, 80):
                spec, processor = namespace.video_processor(runtime, count, frames=4, prefix=7)
                observed.append(dict(video_rows=count, **namespace.capacity_for(runtime, spec, processor)))
            stage = 'storage_behavior'
            rows = [[float(301 + i + j) for j in range(16)] for i in range(6)]
            storage = [namespace.observe_storage(runtime, n, rows) for n in (17, 113, 2053)]
            baseline = storage[0]['payload_bytes']
            assert all(s['payload_bytes'] <= baseline + max(256, baseline // 2)
                       for s in storage[1:]), storage
        result = {'status': 'pass', 'stage': stage, 'cases': observed, 'storage': storage}
        code = 0
    except AssertionError as exc:
        code = 1 if stage != 'setup' else 2
        result = {'status': 'behavior_mismatch' if code == 1 else 'setup_error',
                  'stage': stage, 'error': str(exc), 'traceback': traceback.format_exc()}
    except Exception as exc:
        code = 2
        result = {'status': 'execution_error', 'stage': stage,
                  'error': repr(exc), 'traceback': traceback.format_exc()}
    print('CHALLENGE_RESULT=' + json.dumps(result, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
