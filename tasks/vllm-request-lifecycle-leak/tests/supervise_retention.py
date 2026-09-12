#!/usr/bin/env python3
"""Trusted owner of lifecycle cases, grading, and reward output."""

from __future__ import annotations

import json
import os
import pwd
import secrets
import stat
import subprocess
import sys
from pathlib import Path


REWARD = Path("/logs/verifier/reward.txt")
WORKER = Path(__file__).resolve().with_name("verify_retention.py")
RESULT_PREFIX = "AI_INFRA_OBSERVATION="



def write_reward(value: int, *, exclusive: bool = False) -> None:
    flags = os.O_WRONLY | os.O_NOFOLLOW | os.O_CREAT
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    descriptor = os.open(REWARD, flags, 0o644)
    try:
        os.fchown(descriptor, 0, 0)
        os.fchmod(descriptor, 0o644)
        os.write(descriptor, f"{value}\n".encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def prepare_reward() -> None:
    directory = REWARD.parent
    try:
        info = directory.lstat()
    except FileNotFoundError:
        directory.mkdir(parents=True, mode=0o755)
    else:
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            directory.unlink()
            directory.mkdir(parents=True, mode=0o755)
    os.chown(directory, 0, 0)
    # The host Harbor process must traverse/read outputs; only root may write.
    directory.chmod(0o755)
    try:
        REWARD.unlink()
    except FileNotFoundError:
        pass
    write_reward(0, exclusive=True)


def trusted_file(path: Path) -> bool:
    info = path.stat()
    return info.st_uid == 0 and stat.S_ISREG(info.st_mode) and not (
        info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    )


def run_worker(python_bin, agent):
    import queue
    import threading
    import time
    phases = ['baseline'] + [phase for i in range(4)
        for phase in (f'live-{i}', f'released-{i}')]
    command = ['/usr/bin/setpriv', f'--reuid={agent.pw_uid}',
        f'--regid={agent.pw_gid}', '--init-groups', '--no-new-privs',
        str(python_bin), '-I', str(WORKER)]
    process = subprocess.Popen(command, cwd='/workspace/repo',
        env={**os.environ, 'HOME': agent.pw_dir, 'PYTHONHASHSEED': '0',
             'OMP_NUM_THREADS': '1'}, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
    samples = []
    complete = False
    lines = queue.Queue(maxsize=4096)
    def read_lines():
        for line in process.stdout:
            lines.put(line)
        lines.put(None)
    threading.Thread(target=read_lines, daemon=True).start()
    deadline = time.monotonic() + 300
    try:
        process.stdin.write(json.dumps({'seed': secrets.randbits(32)}) + '\n')
        process.stdin.flush()
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=1)
            except queue.Empty:
                continue
            if line is None:
                break
            print(line.rstrip(), flush=True)
            if line.startswith('CHECKPOINT='):
                phase = line.strip().split('=', 1)[1]
                if len(samples) >= len(phases) or phase != phases[len(samples)]:
                    raise RuntimeError('unexpected checkpoint order')
                # Linux supplies this observation for the exact child we started.
                status = Path(f'/proc/{process.pid}/status').read_text()
                rss = next(int(row.split()[1]) for row in status.splitlines()
                           if row.startswith('VmRSS:'))
                samples.append({'phase': phase, 'rss_kib': rss})
                process.stdin.write('continue\n')
                process.stdin.flush()
            elif line.strip() == 'BEHAVIOR_COMPLETE':
                if complete:
                    raise RuntimeError('duplicate completion')
                complete = True
        process.wait(timeout=max(1, deadline - time.monotonic()))
        if process.returncode != 0 or not complete or len(samples) != len(phases):
            raise RuntimeError('worker did not complete all behavior and memory phases')
        baseline = samples[0]['rss_kib']
        live = [s['rss_kib'] for s in samples if s['phase'].startswith('live-')]
        released = [s['rss_kib'] for s in samples if s['phase'].startswith('released-')]
        if max(live) - baseline < 32 * 1024:
            raise RuntimeError('external observation did not see the live payload workload')
        # Do not require malloc to return pages to the OS. Test growth after warmup.
        if max(released[1:]) - released[0] > 16 * 1024:
            raise RuntimeError('post-warmup retained memory keeps growing')
        return samples
    finally:
        import signal
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        Path('/logs/verifier/memory-observations.json').write_text(
            json.dumps({'pid': process.pid, 'source': '/proc/PID/status',
                        'samples': samples}, indent=2))


def main():
    prepare_reward()
    python_bin = Path(sys.argv[1])
    for path in (python_bin.resolve(), Path(__file__).resolve(), WORKER):
        if not trusted_file(path):
            raise RuntimeError(f'untrusted harness file: {path}')
    try:
        samples = run_worker(python_bin, pwd.getpwnam('agent'))
    except Exception as exc:
        print(f'FAIL: {type(exc).__name__}: {exc}', flush=True)
        return 0
    write_reward(1)
    print(f'PASS: lifecycle, cache, GC checks and {len(samples)} OS observations')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
