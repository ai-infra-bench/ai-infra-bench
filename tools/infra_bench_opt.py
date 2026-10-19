#!/usr/bin/env python3
"""Trusted-controller bookkeeping for the independent infra-bench-opt track."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
import re
import statistics
from pathlib import Path
import time
import uuid

SCHEMA = 'infra-bench-opt.result.v1'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate(result):
    if result.get('schema_version') != SCHEMA or result.get('benchmark') != 'infra-bench-opt':
        raise ValueError('Not an optimization-track result')
    if not isinstance(result.get('task_id'), str) or not result['task_id']:
        raise ValueError('Missing task identity')
    if result.get('kind') not in ('baseline', 'candidate', 'smoke'):
        raise ValueError('Unknown result kind')
    if not finite(result.get('completed_at')) or result['completed_at'] <= 0:
        raise ValueError('Invalid completion timestamp')
    if type(result.get('valid')) is not bool:
        raise ValueError('Explicit validity is required')
    if result['valid']:
        if result['kind'] == 'smoke' or result.get('status') not in ('VALID', 'BASELINE_VALIDATED'):
            raise ValueError('Invalid scored status')
        score = result.get('score')
        if not finite(score) or score <= 0:
            raise ValueError('A valid score must be a positive finite number')
        if not finite(result.get('improvement_pct')) or not math.isclose(result['improvement_pct'], (score - 1) * 100, abs_tol=1e-9):
            raise ValueError('Improvement percentage disagrees with score')
        if result['kind'] == 'baseline' and (result['status'] != 'BASELINE_VALIDATED' or score != 1):
            raise ValueError('Baseline must have score 1')
        if result['kind'] == 'candidate' and result['status'] != 'VALID':
            raise ValueError('Candidate status must be VALID')
    elif result.get('score') is not None or result.get('improvement_pct') is not None:
        raise ValueError('Invalid results must not carry numeric scores')
    elif result.get('status') not in ('INVALID', 'ERROR', 'LATE', 'SMOKE_PASSED'):
        raise ValueError('Unknown invalid/diagnostic status')
    return result


def write(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())
    temporary.replace(path)


@contextmanager
def locked(root):
    with (root / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def start(root, task, baseline, budget=28800, method=None):
    if not isinstance(method,str) or not method.strip():raise ValueError('A frozen method/version ID is required')
    value = validate(json.loads(baseline.read_text()))
    if value['kind'] != 'baseline' or not value['valid'] or value['task_id'] != task:
        raise ValueError('A validated baseline for this task is required')
    if type(budget) is not int or budget <= 0:
        raise ValueError('Budget must be positive integer seconds')
    now = time.time()
    if value['completed_at'] > now:raise ValueError('Baseline completion lies in the future')
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    (root / 'baseline.json').write_bytes(baseline.read_bytes())
    now = time.time()
    state = {'schema_version': 'infra-bench-opt.campaign.v1', 'campaign_id': uuid.uuid4().hex,
             'task_id': task, 'method_id':method, 'baseline_sha256': digest(root / 'baseline.json'),
             'started_at': now, 'deadline': now + budget, 'budget_seconds': budget}
    write(root / 'campaign.json', state)
    (root / 'events.jsonl').touch()
    return state



def begin(root, source_sha256):
    if not re.fullmatch(r'[0-9a-f]{64}', source_sha256):
        raise ValueError('A frozen source/configuration SHA-256 is required')
    with locked(root):
        state = json.loads((root / 'campaign.json').read_text())
        now = time.time()
        if now >= state['deadline']:
            raise ValueError('Campaign budget exhausted')
        trial = {'schema_version':'infra-bench-opt.trial.v1', 'trial_id':uuid.uuid4().hex,
                 'campaign_id':state['campaign_id'], 'task_id':state['task_id'],
                 'baseline_sha256':state['baseline_sha256'], 'source_sha256':source_sha256,
                 'started_at':now, 'campaign_started_at':state['started_at'], 'budget_seconds':state['budget_seconds'], 'deadline':state['deadline']}
        directory = root / 'trials';directory.mkdir(exist_ok=True)
        path = directory / (trial['trial_id']+'.json');write(path,trial)
        return {**trial, 'receipt_path':str(path.resolve())}

def record(root, path):
    # Both this command and result creation belong to the trusted controller.
    payload = path.read_bytes()
    value = validate(json.loads(payload))
    identity = hashlib.sha256(payload).hexdigest()
    with locked(root):
        state = json.loads((root / 'campaign.json').read_text())
        if digest(root / 'baseline.json') != state['baseline_sha256']:
            raise ValueError('Frozen baseline changed')
        if value.get('campaign_id') != state['campaign_id']:
            raise ValueError('Different campaign')
        if value['kind'] != 'candidate' or value['task_id'] != state['task_id']:
            raise ValueError('Wrong task or result kind')
        if value.get('baseline_sha256') != state['baseline_sha256']:
            raise ValueError('Different baseline')
        if value.get('timed') is not True or value.get('deadline') != state['deadline']:
            raise ValueError('Result is not bound to this campaign deadline')
        trial_id = value.get('trial_id')
        if not isinstance(trial_id,str) or not re.fullmatch(r'[0-9a-f]{32}',trial_id):
            raise ValueError('A registered measurement trial is required')
        trial = json.loads((root/'trials'/(trial_id+'.json')).read_text())
        if any(trial.get(key) != state[key] for key in
               ('campaign_id', 'task_id', 'baseline_sha256', 'deadline', 'budget_seconds')):
            raise ValueError('Trial receipt does not match campaign')
        if trial['source_sha256'] != value.get('source_sha256'):
            raise ValueError('Result does not match the registered candidate snapshot')
        if value['completed_at'] < trial['started_at']:
            raise ValueError('Result predates campaign')
        events = [json.loads(line) for line in (root / 'events.jsonl').read_text().splitlines()]
        if any(e['result_sha256'] == identity or e['trial_id'] == trial_id for e in events):
            raise ValueError('Result already recorded')
        received = time.time()
        if value['completed_at'] > received:
            raise ValueError('Completion lies in the future')
        late = received > state['deadline'] or value['completed_at'] > state['deadline']
        event = {'trial_id':trial_id, 'result_sha256': identity, 'received_at': received, 'completed_at': value['completed_at'],
                 'source_sha256': value.get('source_sha256'),
                 'status': 'LATE' if late else value['status'],
                 'valid': value['valid'] and not late, 'score': value['score'] if value['valid'] and not late else None}
        snapshot = root / (identity + '.json')
        temporary = snapshot.with_suffix('.tmp');temporary.write_bytes(payload);temporary.replace(snapshot)
        with (root / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps(event, allow_nan=False) + '\n');stream.flush();os.fsync(stream.fileno())
    return event


def summarize(root):
    with locked(root):
        state = json.loads((root / 'campaign.json').read_text())
        if digest(root / 'baseline.json') != state['baseline_sha256']:
            raise ValueError('Frozen baseline changed')
        events = [json.loads(line) for line in (root / 'events.jsonl').read_text().splitlines()]
        for event in events:
            stored = root / (event['result_sha256'] + '.json')
            if digest(stored) != event['result_sha256']:
                raise ValueError('Stored result changed')
            value = validate(json.loads(stored.read_text()))
            late = event['received_at'] > state['deadline'] or value['completed_at'] > state['deadline']
            expected_score = value['score'] if value['valid'] and not late else None
            if (event['valid'] != (value['valid'] and not late) or event['score'] != expected_score
                    or event['status'] != ('LATE' if late else value['status'])
                    or event['trial_id'] != value['trial_id']):
                raise ValueError('Ledger disagrees with its stored result')
        baseline = json.loads((root/'baseline.json').read_text())
        best = {'score': 1.0, 'kind': 'baseline', 'source_sha256': baseline.get('source_sha256'), 'result_sha256': state['baseline_sha256']}
        curve = []
        for event in events:
            if event['valid'] and event['score'] > best['score']:
                best = {k: event[k] for k in ('score', 'source_sha256', 'result_sha256')};best['kind'] = 'candidate'
                curve.append({'elapsed_seconds': event['received_at'] - state['started_at'], 'score': best['score']})
        return {**state, 'best': best, 'improvement_pct': (best['score'] - 1) * 100,
                'baseline_fallback': best['kind'] == 'baseline', 'improvement_curve': curve,
                'unfinished_trials':len(list((root/'trials').glob('*.json')))-len(events),
                'counts': {key: sum(e['status'] == key for e in events) for key in ('VALID', 'INVALID', 'LATE', 'ERROR')}}



def leaderboard(roots):
    summaries=[summarize(root) for root in roots]
    identities={(s['task_id'],s['baseline_sha256'],s['budget_seconds']) for s in summaries}
    if len(identities)!=1:raise ValueError('Use separate leaderboards for different tasks, baselines or budgets')
    if len({s['campaign_id'] for s in summaries})!=len(summaries):raise ValueError('Duplicate campaign')
    if any(time.time()<s['deadline'] for s in summaries):raise ValueError('Campaign still has budget remaining; use summarize for provisional results')
    grouped={}
    for s in summaries:grouped.setdefault(s['method_id'],[]).append(s)
    rows=[]
    for method,runs in grouped.items():
        values=[s['best']['score'] for s in runs]
        rows.append({'method_id':method,'campaigns':len(runs),'median_score':statistics.median(values),
                     'min_score':min(values),'max_score':max(values),
                     'baseline_fallbacks':sum(s['baseline_fallback'] for s in runs),
                     'unfinished_trials':sum(s['unfinished_trials'] for s in runs),
                     'campaign_ids':[s['campaign_id'] for s in runs]})
    return {'benchmark':'infra-bench-opt','task_id':summaries[0]['task_id'],
            'baseline_sha256':summaries[0]['baseline_sha256'],'budget_seconds':summaries[0]['budget_seconds'],
            'ranking':sorted(rows,key=lambda row:(-row['median_score'],row['method_id']))}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['start', 'info', 'begin', 'record', 'summarize', 'leaderboard'])
    parser.add_argument('--campaign', type=Path, nargs='+', required=True)
    parser.add_argument('--method')
    parser.add_argument('--task')
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--budget-seconds', type=int, default=28800)
    parser.add_argument('--result', type=Path)
    parser.add_argument('--source-sha256')
    args = parser.parse_args()
    if args.command == 'leaderboard':
        print(json.dumps(leaderboard(args.campaign),indent=2,allow_nan=False));return
    if len(args.campaign)!=1:parser.error('This command requires one campaign')
    root=args.campaign[0]
    if args.command == 'start':
        if not args.task or not args.baseline or not args.method:parser.error('start requires --task, --method and --baseline')
        result = start(root, args.task, args.baseline, args.budget_seconds,args.method)
    elif args.command == 'info':result = json.loads((root / 'campaign.json').read_text())
    elif args.command == 'begin':
        if not args.source_sha256:parser.error('begin requires --source-sha256')
        result = begin(root, args.source_sha256)
    elif args.command == 'record':
        if not args.result:parser.error('record requires --result')
        result = record(root, args.result)
    else:result = summarize(root)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':main()
