#!/usr/bin/env python3
"""Small real-syscall controls; not a candidate-facing interface or Pi mock."""
import json
import os
from pathlib import Path
import socket
import sys

root, layout, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
if mode == 'fault' and os.geteuid() == 0:
    os.setgid(60000)
    os.setuid(60000)
    # Match worker_exec: exec resets dumpability after the UID transition.
    os.execv(sys.executable, [sys.executable, *sys.argv])
queues = {}
workers = {}
for role in ['recipient', 'healthy']:
    queue = root / 'independent-layout' / role
    queue.mkdir(parents=True, exist_ok=True)
    queues[role] = queue
    r, w = os.pipe()
    a, b = os.pipe()
    if layout in {'tcp', 'ipc'}:
        if layout == 'ipc':
            tx, rx = socket.socketpair()
        else:
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            tx = socket.socket()
            tx.connect(listener.getsockname())
            rx, _ = listener.accept()
            listener.close()
    pid = os.fork()
    if pid == 0:
        os.close(w)
        os.close(a)
        if layout in {'tcp', 'ipc'}:
            tx.close()
        while True:
            request = os.read(r, 1)
            if request == b'Q':
                os._exit(0)
            if layout in {'tcp', 'ipc'}:
                body = rx.recv(4096)
            else:
                filename = 'spool.jsonl' if layout in {'spool', 'truncate'} else f'entry-{request.decode()}.json'
                path = queue / filename
                body = path.read_text()
                if layout == 'truncate':
                    with path.open('w') as stream:
                        pass
                else:
                    path.unlink()
            os.write(b, b'D')
    os.close(r)
    os.close(b)
    if layout in {'tcp', 'ipc'}:
        rx.close()
    workers[role] = {'pid': pid, 'request': w, 'reply': a, 'socket': tx if layout in {'tcp', 'ipc'} else None}
print(json.dumps({'sender': os.getpid(), **{role: worker['pid'] for role, worker in workers.items()}}), flush=True)
input()


def send(role, number, body, consume):
    queue, worker = queues[role], workers[role]
    if layout in {'tcp', 'ipc'}:
        worker['socket'].sendall(body.encode())
    else:
        filename = 'spool.jsonl' if layout in {'spool', 'truncate'} else f'entry-{number}.json'
        (queue / filename).write_text(json.dumps({'body': body}))
    if consume:
        os.write(worker['request'], str(number).encode())
        assert os.read(worker['reply'], 1) == b'D'


for role in workers:
    send(role, 1, f'warmup-{role}-231124-接口', True)
print('delivered', flush=True)
input()
failures = []
for role in workers:
    try:
        send(role, 2, f'pending-{role}-22142-接口', mode == 'fault' or layout in {'tcp', 'ipc'})
    except OSError as error:
        failures.append({'role': role, 'error': str(error)})
(root / 'ordinary-log').write_text(json.dumps({'body': 'pending-recipient-22142-接口'}))
if mode == 'clean' and layout not in {'tcp', 'ipc'}:
    for queue in queues.values():
        for path in queue.iterdir():
            path.unlink()
for worker in workers.values():
    os.write(worker['request'], b'Q')
    os.waitpid(worker['pid'], 0)
print(json.dumps({'failures': failures}), flush=True)
