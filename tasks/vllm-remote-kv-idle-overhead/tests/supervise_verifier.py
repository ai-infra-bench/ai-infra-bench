#!/usr/bin/env python3
"""Root-owned driver and scorer; candidate imports are confined to one child."""
import _hashlib
import ctypes
import hmac
import importlib.util
import json
import os
from pathlib import Path
import pwd
import runpy
import secrets
import signal
import socket
import struct
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parent
LOGS = Path('/logs/verifier')


class Peer:
    def __init__(self, channel, resource, pid, key, deadline):
        self.channel, self.resource, self.pid, self.key = channel, resource, pid, key
        self.deadline = deadline
        # Linux exposes another process's CPU clock. Values never come from the child.
        libc = ctypes.CDLL(None, use_errno=True)
        clock_id = ctypes.c_int()
        if libc.clock_getcpuclockid(pid, ctypes.byref(clock_id)) != 0:
            raise RuntimeError('candidate CPU clock unavailable')
        self.clock = clock_id.value

    def prepare(self, channel):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0: raise TimeoutError('verification deadline expired')
        channel.settimeout(min(90, remaining))

    def call(self, operation, **args):
        self.prepare(self.channel)
        self.channel.send(json.dumps({'op': operation, **args}, separators=(',', ':')).encode())
        raw = self.channel.recv(65536)
        if not raw: raise RuntimeError(f'candidate exited during {operation}')
        result = json.loads(raw)
        if not isinstance(result, dict): raise RuntimeError('invalid adapter response')
        return result

    def cpu_ns(self):
        return time.clock_gettime_ns(self.clock)

    def memory_bytes(self):
        nonce = secrets.token_bytes(16)
        self.prepare(self.resource)
        self.channel.send(json.dumps({'op': 'snapshot', 'nonce': nonce.hex()}).encode())
        packet = self.resource.recv(256)
        if len(packet) != 56 or packet[32:48] != nonce:
            raise RuntimeError('missing or replayed allocation observation')
        if not hmac.compare_digest(packet[:32], hmac.digest(self.key, packet[32:], 'sha256')):
            raise RuntimeError('unauthenticated allocation observation')
        return struct.unpack('>Q', packet[48:])[0]


def write_result(result):
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / 'reward.txt').write_text(str(result['reward']) + '\n')
    numeric = {name: result[name] for name in ('reward', 'completed', 'required')}
    numeric['failure_count'] = len(result.get('failures', []))
    (LOGS / 'reward.json').write_text(json.dumps(numeric) + '\n')
    (LOGS / 'verifier-details.json').write_text(json.dumps(result, sort_keys=True) + '\n')


def main():
    if os.geteuid() != 0: raise RuntimeError('supervisor requires root')
    LOGS.mkdir(parents=True, exist_ok=True)
    os.chown(LOGS, 0, 0)
    LOGS.chmod(0o755)
    write_result({'reward': 0, 'completed': 0, 'required': 14})
    spec = importlib.util.spec_from_file_location('_checkpoint', ROOT / '_checkpoint.so')
    meter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(meter)
    account = pwd.getpwnam('agent')
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    resource_parent, resource_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    key = secrets.token_bytes(32)
    child_log = open(LOGS / 'candidate.log', 'wb', buffering=0)
    pid = os.fork()
    if pid == 0:
        try:
            parent.close(); resource_parent.close()
            os.setsid()
            os.dup2(child_log.fileno(), 1); os.dup2(child_log.fileno(), 2)
            child_log.close()
            meter.configure(key, resource_child.fileno(), _hashlib.hmac_digest)
            del key
            os.initgroups(account.pw_name, account.pw_gid)
            os.setgid(account.pw_gid); os.setuid(account.pw_uid)
            os.environ.update(HOME=account.pw_dir, XDG_CACHE_HOME=account.pw_dir + '/.cache',
                              HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', VLLM_NO_USAGE_STATS='1',
                              TORCH_DEVICE_BACKEND_AUTOLOAD='0', VLLM_LOGGING_LEVEL='ERROR')
            # Site packages and candidate .pth code become reachable only after dropping root.
            import site
            site.main()
            # Scoring code is loaded only in the parent, after fork. In particular
            # no run_suite frame, expected results or timing functions exist here.
            runpy.run_path(str(ROOT / 'worker.py'), run_name='__main__',
                           init_globals={'_rpc_fd': child.detach(), '_meter': meter})
            os._exit(0)
        except BaseException:
            traceback.print_exc()
            os._exit(1)
    child.close(); resource_child.close(); child_log.close()
    deadline = time.monotonic() + int(sys.argv[1])
    completed = []
    result = {'reward': 0, 'completed': 0, 'required': 14, 'failures': []}
    status = None
    try:
        peer = Peer(parent, resource_parent, pid, key, deadline)
        peer.prepare(parent)
        greeting = parent.recv(65536)
        if not greeting:
            raise RuntimeError('candidate exited before required behavior checks')
        if json.loads(greeting) != {'ready': True}:
            raise RuntimeError('candidate did not initialize')
        # This module uses standard-library types only and never imports vLLM.
        suite = runpy.run_path(str(ROOT / 'verify_blocked_waiting.py'))
        required = tuple(suite['GROUPS'])
        result['required'] = len(required)

        def emit(name):
            if name != required[len(completed)]: raise RuntimeError('incorrect case completion order')
            completed.append(name)
            print(json.dumps({'completed_case': name}), flush=True)

        suite['run_suite'](peer, emit)
        parent.send(b'{"op":"quit"}')
        for _ in range(100):
            done, status = os.waitpid(pid, os.WNOHANG)
            if done: break
            status = None
            time.sleep(0.05)
        if status != 0: raise RuntimeError(f'candidate did not exit cleanly after all checks: {status}')
        result['reward'] = 1
    except BaseException as exc:
        result['failures'].append(f'{type(exc).__name__}: {exc}')
        traceback.print_exc()
    finally:
        parent.close(); resource_parent.close()
        if status is None:
            try: os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError: pass
            _, status = os.waitpid(pid, 0)
        result.update(completed=len(completed), completed_cases=completed, worker_exit_status=status)
        write_result(result)
        print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
