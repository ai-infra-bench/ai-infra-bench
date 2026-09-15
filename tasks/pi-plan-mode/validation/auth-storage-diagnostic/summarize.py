import json
import statistics
from pathlib import Path
from xml.etree import ElementTree as ET
root = Path('/tmp/pi-authstorage-fs-diagnostic-20260915-infra')
results = root / 'results'
records = [json.loads(line) for line in (results/'revision-probe.jsonl').read_text().splitlines()]
summary = {'design': next(r for r in records if r['kind']=='design'), 'probe': {}, 'tests': []}
for fs in ['overlay','tmpfs']:
    samples = [r for r in records if r['kind']=='sample' and r['filesystem']==fs]
    positives = [int(r['mtimeDeltaNs']) for r in samples if int(r['mtimeDeltaNs']) > 0]
    summary['probe'][fs] = {
        'samples': len(samples),
        'revision_collisions': sum(r['collision'] for r in samples),
        'mtime_unchanged': sum(int(r['mtimeDeltaNs'])==0 for r in samples),
        'ctime_unchanged': sum(int(r['ctimeDeltaNs'])==0 for r in samples),
        'round_collisions': [r['collisions'] for r in records if r['kind']=='round' and r['filesystem']==fs],
        'positive_mtime_delta_ns': {'min':min(positives), 'median':statistics.median(positives), 'max':max(positives)} if positives else None,
        'fs_type': samples[0]['fsType'],
        'median_write_stat_duration_ns': statistics.median(int(r['elapsedNs']) for r in samples),
    }
    for trial in range(1,6):
        name = f'auth-storage-{fs}-{trial}'
        xml = ET.parse(results/f'{name}.xml').getroot()
        cases = list(xml.iter('testcase'))
        failures=[]
        for case in cases:
            failed = case.find('failure')
            if failed is None: failed=case.find('error')
            if failed is not None:
                failures.append({'name':case.attrib.get('name'), 'classname':case.attrib.get('classname'), 'message': failed.attrib.get('message'), 'body':failed.text})
        summary['tests'].append({'filesystem':fs,'trial':trial,'exit_code':int((results/f'{name}.exit').read_text()), 'cases':len(cases), 'failures':failures, 'preload_uid_confirmed':'VERIFIER_WORKER_UID=65534' in (results/f'{name}.log').read_text()})
(root/'summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
