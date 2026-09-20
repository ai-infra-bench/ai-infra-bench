"""Trusted parent/child transport. Never use candidate stdout as completion.

The native capability blocks dynamic stdout forgery and calls made from other
Python code objects. It does not sandbox arbitrary native memory access or
arbitrary in-process instrumentation. Behavioral expectations remain in the
parent; this module authenticates completion, not product correctness.
"""
from __future__ import annotations

import hmac
import importlib.util
import json
import os
from pathlib import Path
import pwd
import secrets
import select
import shutil
import signal
import socket
import subprocess
import sys
import sysconfig
import tempfile
import time
import traceback


def build_checkpoint(directory: Path) -> Path:
    """Offline build using the image's compiler and active Python headers."""
    source = Path(__file__).with_name('checkpoint.c')
    extension = directory / ('_encoder_checkpoint' + sysconfig.get_config_var('EXT_SUFFIX'))
    compiler = shutil.which('cc', path='/usr/bin:/usr/local/bin:/bin')
    if not compiler:
        raise RuntimeError('the pinned environment needs a C compiler for completion authentication')
    flags = ['-shared', '-fPIC', '-O2']
    if sys.platform == 'darwin':
        flags += ['-undefined', 'dynamic_lookup']
    subprocess.run([compiler, *flags, '-I' + sysconfig.get_path('include'),
                    str(source), '-o', str(extension)], check=True, timeout=60,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return extension


def execute_suite(suite, inputs, *, timeout=300, candidate_path='/workspace/vllm',
                  drop_user='nobody'):
    """Run a preloaded suite; return only authenticated completion and diagnostics.

    drop_user=None is for the transport's local regression test only. The task
    entrypoint uses nobody and requires a root scoring parent.
    """
    if drop_user is not None and os.geteuid() != 0:
        raise RuntimeError('privilege-separated scoring requires root')
    with tempfile.TemporaryDirectory(prefix='encoder-verifier-') as tmp:
        directory = Path(tmp)
        extension = build_checkpoint(directory)
        account = pwd.getpwnam(drop_user) if drop_user else None
        parent, child = socket.socketpair()
        with tempfile.TemporaryFile() as log:
            pid = os.fork()
            if pid == 0:
                try:
                    parent.close()
                    os.setsid()
                    os.dup2(log.fileno(), 1)
                    os.dup2(log.fileno(), 2)
                    # Preserve stdin workload availability for adversarial
                    # controls. It provides no completion capability.
                    with tempfile.TemporaryFile() as stream:
                        stream.write(json.dumps(inputs).encode()); stream.seek(0)
                        os.dup2(stream.fileno(), 0)
                    spec = importlib.util.spec_from_file_location('_encoder_checkpoint', extension)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules['_encoder_checkpoint'] = module
                    spec.loader.exec_module(module)
                    module.configure(child.fileno(), suite.__code__, json.dumps)
                    if account:
                        os.setgroups([])
                        os.setgid(account.pw_gid)
                        os.setuid(account.pw_uid)
                    # Equivalent to the previous image's source .pth, but no
                    # candidate Python code runs before privilege dropping.
                    sys.path.insert(0, str(candidate_path))
                    os.chdir(candidate_path)
                    suite(inputs, module.emit)
                    child.close()
                    os._exit(0)
                except BaseException:
                    traceback.print_exc()
                    sys.stderr.flush()
                    os._exit(1)
            child.close()
            # Created only in the parent, after fork: no Python-level secret in
            # the child heap, closure or inherited frame.
            secret = secrets.token_bytes(32)
            data = bytearray()
            deadline = time.monotonic() + timeout
            status = None
            error = None
            try:
                parent.sendall(secret)
                parent.shutdown(socket.SHUT_WR)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        error = 'worker_timeout'; break
                    readable, _, _ = select.select([parent], [], [], min(0.1, remaining))
                    if readable:
                        chunk = parent.recv(65536)
                        if not chunk:
                            break
                        data.extend(chunk)
                        if len(data) > 1000032:
                            error = 'completion_report_too_large'; break
                    if status is None:
                        done, value = os.waitpid(pid, os.WNOHANG)
                        if done:
                            status = value
                while status is None and time.monotonic() < deadline:
                    done, value = os.waitpid(pid, os.WNOHANG)
                    if done:
                        status = value; break
                    time.sleep(0.02)
                if status is None:
                    error = error or 'worker_timeout'
            finally:
                parent.close()
                # Also remove descendants after successful or failed trials.
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if status is None:
                    _, status = os.waitpid(pid, 0)
            log.seek(0)
            diagnostic = log.read(16000).decode(errors='replace')
            if error:
                return {'error': error, 'worker_status': status, 'diagnostic': diagnostic}
            if status != 0:
                return {'error': 'worker_failed', 'worker_status': status, 'diagnostic': diagnostic}
            if len(data) <= 32 or not hmac.compare_digest(bytes(data[:32]), secret):
                return {'error': 'unauthenticated_completion', 'worker_status': status,
                        'diagnostic': diagnostic}
            return {'payload': bytes(data[32:]).decode(), 'worker_status': status,
                    'diagnostic': diagnostic}
