"""Audit a fresh agent image without installing private tests in that image."""
import argparse
import json
from pathlib import Path
import re
import secrets
import subprocess

PROBE = r'''
import json,os
from pathlib import Path
forbidden = {'quality72', 'quality100', 'oracles.json', 'quality_witnesses.json',
             'check_quality_oracles.py', 'frozen-manifest.json'}
assert not any(Path(p).exists() for p in ['/tests', '/task-work', '/logs/verifier'])
violations=[]
for root in ['/workspace', '/opt/task-lock']:
    for parent, dirs, files in os.walk(root):
        if any(name in forbidden for name in dirs+files):
            violations.append(parent)
assert not violations, 'Private task files found in agent image'
assert Path('/workspace/sglang/python/sglang/__init__.py').is_file()
assert Path('/workspace/task/launch.py').is_file()
print(json.dumps({'private_task_files_absent':True,'native_source_present':True,
                  'launcher_present':True,'effective_uid':os.geteuid()}))
'''


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--image', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', a.image):
        raise ValueError('Use the exact built image ID')
    if a.output.exists():
        raise ValueError('Use a fresh audit path')
    name = 'native-task-visibility-' + secrets.token_hex(8)
    try:
        subprocess.run(['docker', 'create', '--name', name, '--network', 'none',
                        '--entrypoint', 'python3', a.image, '-I', '-c', PROBE],
                       check=True, stdout=subprocess.DEVNULL)
        config = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]
        if config['Mounts'] or config['HostConfig']['NetworkMode'] != 'none':
            raise ValueError('Visibility audit must have no host mounts or network')
        proc = subprocess.run(['docker', 'start', '-a', name], capture_output=True, text=True, timeout=120)
        state = json.loads(subprocess.check_output(['docker', 'inspect', name]))[0]['State']
        if proc.returncode or state['ExitCode']:
            raise RuntimeError('Agent image visibility check failed: ' + proc.stderr[-2000:])
        result = json.loads(proc.stdout)
        result.update(image_id=config['Image'], mounts=config['Mounts'], network='none',
                      scope='Fresh agent image. Private tests may be injected only after the agent exits.')
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
    finally:
        subprocess.run(['docker', 'rm', '-f', name], check=True, stdout=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
