"""Independent declared workload through real schedule/execute/merge boundaries."""
from pathlib import Path
import json
import sys
import types

TESTS = Path(__file__).resolve().parents[2] / 'tests'
# Docker matrix mounts this directory alone at /challenge.
if not TESTS.is_dir():
    TESTS = Path('/tests')
namespace = types.ModuleType('_encoder_independent_challenge')
namespace.__file__ = str(TESTS / 'encoder_runtime.py')
sys.modules[namespace.__name__] = namespace
for name in ('encoder_runtime.py', 'encoder_scenarios.py'):
    exec(compile((TESTS / name).read_text(), str(TESTS / name), 'exec'), namespace.__dict__)

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
        pair = runtime.pair(dict(spec, offset=0), chunk=chunk, eagle=eagle)
        try:
            pair.add(dict(id='challenge', tokens=tokens, features=[spec]))
            actual = pair.finish()['challenge']
            assert actual == dict(positions=list(range(25)), rows=expected), actual
            if eagle:
                assert pair.draft_delivered['challenge'] == dict(
                    positions=list(range(1, 26)), rows=expected[1:] + [[17.] * 16])
            completed.append(dict(chunk=chunk, eagle=eagle, consumed=len(actual['rows'])))
        finally:
            pair.close()
print(json.dumps({'cases': completed, 'pass': len(completed) == 4}, indent=2))
print('CHALLENGE_ENCODER_CACHE=PASS')
