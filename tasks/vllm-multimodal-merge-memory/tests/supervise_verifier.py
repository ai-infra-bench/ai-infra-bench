#!/usr/bin/env python3
"""Root-owned scoring with authenticated, ordered completion checkpoints.

Stdout is diagnostic only. This is bounded protection against Python report
forgery and early exits, not an arbitrary native-memory adversary sandbox.
"""
from __future__ import annotations

import hmac
import importlib.util
import json
import os
from pathlib import Path
import pwd
import runpy
import secrets
import select
import signal
import socket
import stat
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
OUT = Path('/logs/verifier')


def trusted(path):
    info = path.stat()
    if info.st_uid != 0 or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022:
        raise RuntimeError(f'untrusted harness file: {path}')


def write_reward(value):
    for name, body in [('reward.txt', f'{value}\n'), ('reward.json', json.dumps({'reward': value}) + '\n')]:
        fd = os.open(OUT / name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
        try:
            os.fchown(fd, 0, 0)
            os.fchmod(fd, 0o644)
            os.write(fd, body.encode())
        finally:
            os.close(fd)


def run_group(cases, timeout):
    # All loaded files are root-owned staged harness inputs, not candidate code.
    extension = HERE / '_checkpoint.so'
    trusted(extension)
    spec = importlib.util.spec_from_file_location('_checkpoint', extension)
    checkpoint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checkpoint)
    suite = runpy.run_path(str(HERE / 'verify_multimodal_merge.py'))['run_suite']
    agent = pwd.getpwnam('agent')  # Never silently run candidate code as root.
    key = secrets.token_bytes(32)
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    log = open(OUT / 'verifier.log', 'wb', buffering=0)
    pid = os.fork()
    if pid == 0:
        try:
            parent.close()
            checkpoint.configure(key, child.fileno(), suite.__code__, json.dumps)
            del key
            os.setsid()
            os.dup2(log.fileno(), 1)
            os.dup2(log.fileno(), 2)
            log.close()
            with open(os.devnull, 'rb') as empty:
                os.dup2(empty.fileno(), 0)
            os.initgroups(agent.pw_name, agent.pw_gid)
            os.setgid(agent.pw_gid)
            os.setuid(agent.pw_uid)
            os.environ.update(HOME=agent.pw_dir, XDG_CACHE_HOME=agent.pw_dir + '/.cache',
                              HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
            Path(agent.pw_dir, '.cache').mkdir(exist_ok=True)
            os.chdir('/workspace/repo')
            suite(cases, checkpoint.emit)
            os._exit(0)
        except BaseException:
            import traceback
            traceback.print_exc()
            os._exit(1)
    child.close()
    log.close()
    deadline = time.monotonic() + timeout
    previous = b''
    records, errors = [], []
    status = None
    try:
        while len(records) < len(cases):
            if time.monotonic() >= deadline:
                errors.append('timeout before completing all checks')
                break
            readable, _, _ = select.select([parent], [], [], 0.2)
            if readable:
                packet = parent.recv(65536)
                signature, body = packet[:32], packet[32:]
                if not hmac.compare_digest(signature, hmac.digest(key, previous + body, 'sha256')):
                    errors.append('unauthenticated checkpoint')
                    break
                observed = json.loads(body)
                expected = cases[len(records)]
                if observed.get('index') != len(records) or observed.get('name') != expected['name']:
                    errors.append('missing, reordered or duplicate checkpoint')
                    break
                previous = signature
                value = observed.get('value', {})
                if value.get('passed') is not True:
                    errors.append('failed behavioral check')
                    break
                if expected['kind'] == 'merge':
                    ratios = value.get('peak_ratios', [])
                    if len(ratios) != 2 or any(not isinstance(r, (float, int)) or not 0 <= r < 4 for r in ratios):
                        errors.append('invalid or excessive allocation observation')
                        break
                records.append(observed)
            else:
                done, child_status = os.waitpid(pid, os.WNOHANG)
                if done:
                    status = child_status
                    errors.append(f'worker exited before complete checks: {len(records)}/{len(cases)}')
                    break
        while status is None and time.monotonic() < deadline:
            done, child_status = os.waitpid(pid, os.WNOHANG)
            if done:
                status = child_status
                break
            if errors:
                break
            time.sleep(0.05)
        if status != 0:
            errors.append(f'worker did not exit successfully: {status}')
    finally:
        parent.close()
        if status is None:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            os.waitpid(pid, 0)
    result = dict(completed=len(records), required=len(cases), records=records,
                  child_status=status, errors=errors)
    (OUT / 'completion.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(completed=len(records), required=len(cases), errors=errors)), flush=True)
    return not errors and len(records) == len(cases)


def main():
    if os.geteuid() != 0:
        raise RuntimeError('scoring parent must run as root')
    OUT.mkdir(parents=True, exist_ok=True)
    os.chown(OUT, 0, 0)
    OUT.chmod(0o755)
    write_reward(0)
    for name in ('supervise_verifier.py', 'verify_multimodal_merge.py', 'case_specs.py'):
        trusted(HERE / name)
    trusted(Path(sys.executable).resolve())
    # Parent-owned preflight executes no candidate source.
    subprocess.run([sys.executable, '-I', '-c', 'import torch; assert torch.cuda.is_available()'],
                   cwd=HERE, check=True, timeout=60)
    cases = runpy.run_path(str(HERE / 'case_specs.py'))['CASES']
    if run_group(cases, 780):
        write_reward(1)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
