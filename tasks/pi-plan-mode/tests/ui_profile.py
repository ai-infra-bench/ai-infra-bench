#!/usr/bin/env python3
"""Trusted, candidate-bound UI integration profile; never infer button semantics."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

CANDIDATE_ROOTS = ('packages/coding-agent/examples/extensions/plan-mode', 'packages/coding-agent/test')

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def inventory(root, paths, excluded=()):
    result = {}
    for name in paths:
        start = root / name
        entries = [start]
        if start.is_dir() and not start.is_symlink():
            entries += sorted(start.rglob('*'))
        for path in entries:
            relative = path.relative_to(root).as_posix()
            if any(part in excluded for part in path.relative_to(root).parts):
                continue
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                value = ['link', os.readlink(path)]
            elif stat.S_ISREG(mode):
                value = ['file', bool(mode & 0o111), digest(path.read_bytes())]
            elif stat.S_ISDIR(mode):
                value = ['directory']
            else:
                raise ValueError(f'Unsupported snapshot entry: {relative}')
            result[relative] = value
    return digest(json.dumps(result, sort_keys=True).encode())

def snapshot(workspace, tests):
    return {
        'candidate_sha256': inventory(workspace, CANDIDATE_ROOTS, ('__plan_verifier__',)),
        'verifier_sha256': inventory(tests, ['.'], ('ui-profile.json', 'ui-actions.json', '__pycache__')),
        'binding_sha256': digest((tests / 'ui-actions.json').read_bytes()),
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['create', 'check'])
    p.add_argument('--workspace', type=Path, default=Path('/workspace/pi'))
    p.add_argument('--tests', type=Path, required=True)
    p.add_argument('--image')
    p.add_argument('--profile-id')
    p.add_argument('--evidence', type=Path)
    p.add_argument('--scenario', type=Path)
    args = p.parse_args()
    try:
        path = args.tests / 'ui-profile.json'
        current = snapshot(args.workspace, args.tests)
        if args.mode == 'create':
            evidence = json.loads(args.evidence.read_text())
            scenario = json.loads(args.scenario.read_text())
            if not evidence or not scenario or not args.image or not args.profile_id:
                raise ValueError('Explicit reviewed binding, evidence, scenario and immutable image required')
            profile = dict(current, schema='pi-plan-ui-profile.v1', image=args.image,
                           profile_id=args.profile_id, evidence=evidence, scenario=scenario)
            path.write_text(json.dumps(profile, indent=2) + '\n')
        else:
            profile = json.loads(path.read_text())
            if profile.get('schema') != 'pi-plan-ui-profile.v1' or not profile.get('evidence') or not profile.get('scenario'):
                raise ValueError('Missing reviewed provenance')
            for key, value in current.items():
                if profile.get(key) != value:
                    raise ValueError(f'Stale reviewed UI profile: {key}')
        print(json.dumps({'status': 'reviewed', **current}))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({'status': 'integration_needed', 'reason': str(error)}))
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
