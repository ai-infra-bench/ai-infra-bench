"""Re-analyze saved live traces without calling models or changing old evidence."""
import argparse
import json
from pathlib import Path
from metrics import behavior_metrics, infrastructure_metrics, phase_completion, recovery_preconditions


def analyze(directory):
    events = [json.loads(line) for line in (directory/'events.jsonl').read_text().splitlines()]
    capture = directory/'capture/router_trace.jsonl'
    records = [json.loads(line) for line in capture.read_text().splitlines()] if capture.exists() else []
    log = directory/'router-console.log'
    recovery = directory/'recovery.json'
    original = json.loads((directory/'result.json').read_text())
    scenario = json.loads((directory/'scenario.json').read_text())
    return {
        'source': str(directory.resolve()),
        'original_status': original['status'],
        'operator_recovery': recovery.exists() or original.get('operator_interruption_recovered', False),
        'efficiency': behavior_metrics(events),
        'completion': phase_completion(events),
        'recovery_preconditions': recovery_preconditions(events, scenario['data']),
        'infrastructure': infrastructure_metrics(records, log.read_text() if log.exists() else ''),
        'model_calls_made_by_replay': 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sources', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = [analyze(directory) for directory in args.sources]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as output:
        json.dump(results, output, ensure_ascii=False, indent=2)
        output.write('\n')
    for r in results:
        print(json.dumps({'source':r['source'],'extra_resets':r['efficiency']['extra_phase0_reset_calls'],
                          'completion':r['completion'],'operator_recovery':r['operator_recovery']},ensure_ascii=False))


if __name__ == '__main__': main()
