"""Construction challenge: several transition requests and a late note update in one batch."""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'tasks/pi-context-management/tests/verify.py').exists())
spec = importlib.util.spec_from_file_location('behavior', ROOT/'tasks/pi-context-management/tests/verify.py')
behavior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(behavior)

def script(self, phase=0):
    body = yield
    self.initial(body)
    body = yield behavior.calls(behavior.call('evidence', key='old'))
    previous = 'superseded-' + self.nonce
    body = yield behavior.calls(behavior.call('notes_write', path='summary.md', text=previous))
    body = yield behavior.calls(behavior.call('new_context'), behavior.call('notes_write', path='summary.md', text=self.summary), behavior.call('new_context'))
    self.check_fresh(body)
    assert previous not in behavior.all_text(body)
    body = yield behavior.calls(behavior.call('notes_read', path='summary.md'))
    assert behavior.result(body)['text'] == self.summary
    self.done = True
    yield {'content': 'VERIFIED-' + self.nonce}

behavior.Scenario.script_main = script
parser = argparse.ArgumentParser()
parser.add_argument('repo', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
result = behavior.run_case('rollover', args.repo.resolve(), args.output.resolve())
print(json.dumps(result, ensure_ascii=False))
raise SystemExit(0 if result['passed'] else 1)
