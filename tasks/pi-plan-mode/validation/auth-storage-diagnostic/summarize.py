"""Summarize all fixed diagnostic trials without recording host mount paths."""
import argparse
import gzip
import json
import statistics
from pathlib import Path
from xml.etree import ElementTree as ET


def summarize(root: Path) -> dict:
    results = root / 'results'
    probe = results / 'revision-probe.jsonl'
    if probe.exists():
        text = probe.read_text()
    else:
        with gzip.open(results / 'revision-probe.jsonl.gz', 'rt') as stream:
            text = stream.read()
    records = [json.loads(line) for line in text.splitlines()]
    design = dict(next(r for r in records if r['kind'] == 'design'))
    design.pop('mountinfo', None)
    summary = {'design': design, 'probe': {}, 'tests': []}
    consolidated = results / 'run-output.json'
    outputs = json.loads(consolidated.read_text()) if consolidated.exists() else {}
    for fs in ['overlay', 'tmpfs']:
        samples = [r for r in records if r['kind'] == 'sample' and r['filesystem'] == fs]
        positives = [int(r['mtimeDeltaNs']) for r in samples if int(r['mtimeDeltaNs']) > 0]
        summary['probe'][fs] = {
            'samples': len(samples),
            'revision_collisions': sum(r['collision'] for r in samples),
            'mtime_unchanged': sum(int(r['mtimeDeltaNs']) == 0 for r in samples),
            'ctime_unchanged': sum(int(r['ctimeDeltaNs']) == 0 for r in samples),
            'round_collisions': [r['collisions'] for r in records if r['kind'] == 'round' and r['filesystem'] == fs],
            'positive_mtime_delta_ns': {'min': min(positives), 'median': statistics.median(positives), 'max': max(positives)} if positives else None,
            'fs_type': samples[0]['fsType'],
            'median_write_stat_duration_ns': statistics.median(int(r['elapsedNs']) for r in samples),
        }
        for trial in range(1, 6):
            name = f'auth-storage-{fs}-{trial}'
            xml_path = results / f'{name}.xml'
            if not xml_path.exists():
                xml_path = root.parent / 'auth-storage-base-evidence' / f'{name}.xml'
            xml = ET.parse(xml_path).getroot()
            cases = list(xml.iter('testcase'))
            failures = []
            for case in cases:
                failed = case.find('failure')
                if failed is None:
                    failed = case.find('error')
                if failed is not None:
                    failures.append({'name': case.attrib.get('name'), 'classname': case.attrib.get('classname'), 'message': failed.attrib.get('message'), 'body': failed.text})
            output = outputs.get(name)
            if output is None:
                output = {'exit_code': int((results / f'{name}.exit').read_text()), 'log': (results / f'{name}.log').read_text()}
            summary['tests'].append({'filesystem': fs, 'trial': trial, 'exit_code': output['exit_code'], 'cases': len(cases), 'failures': failures, 'preload_uid_confirmed': 'VERIFIER_WORKER_UID=65534' in output['log']})
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Diagnostic output directory')
    parser.add_argument('--output', type=Path, help='Summary destination; defaults to DIRECTORY/summary.json')
    args = parser.parse_args()
    target = args.output or args.directory / 'summary.json'
    target.write_text(json.dumps(summarize(args.directory), indent=2) + '\n')
    print(target)


if __name__ == '__main__':
    main()
