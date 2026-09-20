"""Independent declared workload through real schedule/execute/merge boundaries."""
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
        namespace = types.ModuleType('_encoder_independent_challenge')
        namespace.__file__ = str(tests / 'encoder_runtime.py')
        sys.modules[namespace.__name__] = namespace
        for name in ('encoder_runtime.py', 'encoder_scenarios.py'):
            exec(compile((tests / name).read_text(), str(tests / name), 'exec'), namespace.__dict__)
        rows = [[float(601 + i * 7 + j) for j in range(16)] for i in range(4)]
        spec = dict(offset=3, length=19, indices=[1, 6, 12, 17], rows=rows)
        tokens = [31] * 25
        for index in spec['indices']:
            tokens[spec['offset'] + index] = 250
        expected = [[float(value)] * 16 for value in tokens]
        for index, row in zip(spec['indices'], rows):
            expected[spec['offset'] + index] = row
        completed = []
        with namespace.Runtime() as runtime:
            for chunk, eagle in [(1, False), (4, False), (1, True), (4, True)]:
                stage = 'setup'
                pair = runtime.pair(dict(spec, offset=0), chunk=chunk, eagle=eagle)
                try:
                    pair.add(dict(id='challenge', tokens=tokens, features=[spec]))
                    stage = 'model_inputs'
                    actual = pair.finish()['challenge']
                    assert actual == dict(positions=list(range(25)), rows=expected), actual
                    if eagle:
                        assert pair.draft_delivered['challenge'] == dict(
                            positions=list(range(1, 26)), rows=expected[1:] + [[17.] * 16])
                    completed.append(dict(chunk=chunk, eagle=eagle, consumed=len(actual['rows'])))
                finally:
                    pair.close()
        result = {'status': 'pass', 'stage': stage, 'cases': completed}
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
