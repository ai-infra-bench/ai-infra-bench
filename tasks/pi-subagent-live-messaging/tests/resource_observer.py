"""External syscall evidence for live-messaging resources.

This observer does not infer a queue from a filename or a payload alone. A
file queue is learned only after a known sender writes a complete controlled
message, its actual recipient reads that file, the file is unlinked or emptied, and the
message is observed in that recipient's model input. Only later unconsumed
messages in the same queue can fail cleanup. Persistent logs and unclassified
files remain diagnostics. This deliberately does not claim universal storage
classification or universal transport fault injection.

The caller must supply actor PIDs authenticated by RuntimeObserver, call
finish before harness cleanup, and route infrastructure_errors to scoring_error.
No candidate resource profile or source inspection is used.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import threading
import time

_QUOTED = re.compile(r'"(?:\\.|[^"\\])*"')
_CALL = re.compile(r'^(\d+\.\d+)\s+(\w+)\((.*)\)\s+=\s+(.+)$')
_FD = re.compile(r'^(-?\d+)(?:<(.+)>)?$')
_IO = {'read', 'readv', 'pread64', 'write', 'writev', 'pwrite64', 'sendto', 'recvfrom', 'sendmsg', 'recvmsg'}
_WRITE = {'write', 'writev', 'pwrite64', 'sendto', 'sendmsg'}
_TRACE = '%process,%file,read,readv,pread64,write,writev,pwrite64,close,connect,accept,accept4,bind,listen,shutdown,sendto,recvfrom,sendmsg,recvmsg,ftruncate,truncate,socket,socketpair,pipe,pipe2,dup,dup2,dup3'


def _string(value):
    """Decode strace C strings including octal UTF-8, without eval/code execution."""
    try:
        text = ast.literal_eval(value)
        if not isinstance(text, str):
            return ''
        try:
            return text.encode('latin1').decode('utf8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            return text
    except (SyntaxError, ValueError):
        return ''


def _has_body(text, body):
    # strace decodes a syscall buffer; a file may contain raw text or JSON.
    return body in text or json.dumps(body, ensure_ascii=False)[1:-1] in text or json.dumps(body, ensure_ascii=True)[1:-1] in text


def _slot(path):
    """Learn a conservative filename family; never treat every sibling as mail.

    Fixed spool paths are exact. UUID/numeric-generated entry names generalize
    only the generated token, preserving their prefix/suffix. Other naming
    schemes remain an observation limit, not a candidate failure.
    """
    name = Path(path).name
    uuid = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
    if uuid.search(name):
        return uuid.sub("{uuid}", name)
    if re.search(r"\d+", name):
        return re.sub(r"\d+", "{number}", name)
    return name


def _open_directory_nofollow(path):
    # Walk each component: O_NOFOLLOW on only the last component would let a
    # candidate swap an ancestor for a symlink before the privileged chmod.
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in Path(path).parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _identity(path):
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            return None
        return [info.st_dev, info.st_ino]
    except OSError:
        return None


class ResourceObserver:
    def __init__(self, repo, output_dir, coordinator_port, *, strace='/usr/bin/strace'):
        self.repo = Path(repo).resolve()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.trace_prefix = self.output_dir / 'syscalls'
        self.coordinator_port = int(coordinator_port)
        self.excluded_ports = {self.coordinator_port}
        self.strace = strace
        self.actors = {}  # OS-authenticated process ID -> public task ID
        self.messages = []
        self._body_markers = set()
        self._has_unmarked_body = False
        self.deliveries = set()
        self.delivery_order = []
        self.errors = []
        self.faults = []
        self.snapshots = []
        self.lock = threading.RLock()
        self.wrapped = False
        self.trace_limit = 256 * 1024 * 1024
        self._offsets = {}
        self._pending = {}
        self._records = []
        self._parents = {}
        self._threads = {}
        self._fds = {}
        self._cwd = {}
        self._exited = set()
        self._created_directories = set()

    def wrap_command(self, command):
        if not shutil.which(self.strace):
            raise RuntimeError('resource observer requires pinned strace; no resource score is available')
        self.wrapped = True
        # -yy resolves descriptor paths at the syscall boundary, even for files
        # deleted before a later /proc snapshot. -ff keeps trusted per-PID traces.
        # 4096 bytes is enough for the dedicated small warmup messages. Larger
        # truncated buffers do not qualify as full-body evidence.
        return [self.strace, '-ff', '-qq', '-ttt', '-yy', '-s', '4096', '-e', 'trace=' + _TRACE,
                '-o', str(self.trace_prefix), '--', *map(str, command)]

    def observe_event(self, event):
        with self.lock:
            kind = event.get('kind')
            if kind == 'actor':
                pid, task = event.get('pid'), event.get('task_id')
                if type(pid) is not int or pid < 2 or not isinstance(task, str):
                    raise ValueError('invalid authenticated actor event')
                if pid in self.actors and self.actors[pid] != task:
                    # A persistent parent may coordinate multiple dispatches;
                    # worker message addresses still require unambiguous PIDs.
                    raise ValueError('resource actor process claimed two task identities')
                self.actors[pid] = task
            elif kind == 'message':
                record = {key: event[key] for key in ('sender', 'recipient', 'body')}
                if not all(isinstance(value, str) and value for value in record.values()):
                    raise ValueError('invalid controlled message event')
                if record not in self.messages:
                    self.messages.append(record)
                    markers = re.findall(r'[A-Za-z0-9_-]{12,}', record['body'])
                    if markers:
                        self._body_markers.add(max(markers, key=len))
                    else:
                        self._has_unmarked_body = True
            elif kind == 'delivery':
                self.deliveries.add((event['recipient'], event['body']))
                self.delivery_order.append((event['recipient'], event['body']))
            elif kind == 'exclude_port':
                self.excluded_ports.add(int(event['port']))
            elif kind == 'snapshot':
                return self.snapshot(event.get('label', 'boundary'))

    def _excluded_endpoint(self, endpoint):
        return any(re.search(r':' + str(port) + r'(?!\d)', endpoint) for port in self.excluded_ports)

    def _actor(self, pid):
        seen = set()
        while pid not in seen:
            seen.add(pid)
            if pid in self.actors:
                return self.actors[pid]
            # Threads belong to a Pi actor. Ordinary helper children are not
            # automatically allowed to impersonate the recipient's file read.
            pid = self._threads.get(pid)
            if pid is None:
                return None
        return None

    def _fd_owner(self, pid):
        seen = set()
        while pid in self._threads and pid not in seen:
            seen.add(pid)
            pid = self._threads[pid]
        return pid

    def _path(self, token, pid, directory=None):
        text = _string(token)
        if not text:
            return None
        if text.startswith('/'):
            return os.path.normpath(text)
        base = None
        if directory:
            match = re.search(r'<(/[^>]+)>', directory)
            if match:
                base = match.group(1)
        base = base or self._cwd.get(pid)
        return os.path.normpath(os.path.join(base, text)) if base else None

    def _ingest(self):
        paths = list(self.output_dir.glob(self.trace_prefix.name + '.*'))
        if sum(path.stat().st_size for path in paths) > self.trace_limit:
            if 'syscall trace exceeds bounded observer input budget' not in self.errors:
                self.errors.append('syscall trace exceeds bounded observer input budget')
            return
        new = []
        for path in paths:
            try:
                pid = int(path.suffix[1:])
            except ValueError:
                continue
            offset = self._offsets.get(path, 0)
            with path.open(errors='replace') as stream:
                stream.seek(offset)
                while True:
                    position = stream.tell()
                    line = stream.readline()
                    if not line or not line.endswith('\n'):
                        stream.seek(position)
                        break
                    if '<unfinished ...>' in line:
                        self._pending[pid] = line.split('<unfinished ...>', 1)[0]
                        continue
                    resumed = re.match(r'^\d+\.\d+\s+<\.\.\. \w+ resumed>(.*)$', line)
                    if resumed:
                        before = self._pending.pop(pid, None)
                        if before is None:
                            continue
                        line = before + resumed.group(1)
                    match = _CALL.match(line.strip())
                    if match:
                        stamp, name, args, result = match.groups()
                        new.append((float(stamp), pid, name, args, result))
                self._offsets[path] = stream.tell()
        for record in sorted(new):
            self._parse(*record)

    def _parse(self, stamp, pid, name, args, result):
        number = re.match(r'(-?\d+)', result)
        success = bool(number and int(number.group(1)) >= 0)
        value = int(number.group(1)) if number else None
        # Module loading and inspector coverage carry large buffers. A raw
        # ASCII nonce filter only skips buffers that cannot contain any full
        # controlled message; bodies without such a marker keep full parsing.
        if name in _IO:
            if self._actor(pid) is None:
                return
            if not self._has_unmarked_body and not any(marker in args for marker in self._body_markers):
                return
        strings = list(_QUOTED.finditer(args))
        first_arg = args.split(',', 1)[0]
        if name in {'clone', 'clone3', 'fork', 'vfork'} and success and value:
            self._parents[value] = pid
            if 'CLONE_THREAD' in args:
                self._threads[value] = self._threads.get(pid, pid)
            else:
                inherited = {(value, fd): endpoint for (owner, fd), endpoint in self._fds.items() if owner == self._fd_owner(pid)}
                self._fds.update(inherited)
            if pid in self._cwd:
                self._cwd[value] = self._cwd[pid]
        if name in {'exit', 'exit_group'}:
            self._exited.add(pid)
        if name in {'mkdir', 'mkdirat'} and success and strings:
            path = self._path(strings[0].group(), pid, first_arg if name == 'mkdirat' else None)
            if path:
                self._created_directories.add(path)
        if name == 'chdir' and success and strings:
            self._cwd[pid] = self._path(strings[0].group(), pid)
        if name in {'pipe', 'pipe2', 'socketpair'} and success:
            pair = re.search(r'\[(\d+)(?:<[^>]*>)?,\s*(\d+)', args)
            if pair:
                endpoint = f'{name}:{pid}:{stamp}'
                for fd in map(int, pair.groups()):
                    self._fds[(self._fd_owner(pid), fd)] = endpoint
            return
        if name == 'connect' and (success or 'EINPROGRESS' in result):
            fd = re.match(r'\d+', first_arg)
            port = re.search(r'sin6?_port=htons\((\d+)\)', args)
            if fd:
                if port:
                    endpoint = 'TCP:' + (_string(strings[0].group()) if strings else '?') + ':' + port.group(1)
                    self._fds[(self._fd_owner(pid), int(fd.group()))] = endpoint
                elif 'AF_UNIX' in args and strings:
                    self._fds[(self._fd_owner(pid), int(fd.group()))] = 'UNIX:' + _string(strings[0].group())
            return
        if name in {'dup', 'dup2', 'dup3'} and success:
            original = re.match(r'\d+', first_arg)
            if original:
                source = self._fds.get((self._fd_owner(pid), int(original.group())))
                if source:
                    self._fds[(self._fd_owner(pid), value)] = source
            return
        if name in {'open', 'openat', 'openat2', 'creat'}:
            returned = re.search(r'^\d+<(/[^>]+)>', result)
            path = returned.group(1) if returned else self._path(strings[0].group(), pid, first_arg) if strings else None
            if path and success:
                self._fds[(self._fd_owner(pid), value)] = path
                if 'O_TRUNC' in args:
                    self._records.append({'time': stamp, 'pid': pid, 'kind': 'clear', 'path': path})
            if path and not success and re.search(r'\b(EACCES|EPERM|EROFS)\b', result):
                self._records.append({'time': stamp, 'pid': pid, 'kind': 'denied', 'path': path,
                                      'writable': any(flag in args for flag in ['O_WRONLY', 'O_RDWR', 'O_CREAT']), 'result': result})
            return
        if name in {'truncate', 'ftruncate'} and success and args.rsplit(',', 1)[-1].strip() == '0':
            if name == 'truncate' and strings:
                path = self._path(strings[0].group(), pid)
            else:
                fd = re.match(r'(\d+)(?:<(/[^>]+)>)?', first_arg)
                path = (fd.group(2) or self._fds.get((self._fd_owner(pid), int(fd.group(1))))) if fd else None
            if path:
                self._records.append({'time': stamp, 'pid': pid, 'kind': 'clear', 'path': path})
            return
        if name in {'unlink', 'unlinkat', 'rmdir'} and success and strings:
            path = self._path(strings[0].group(), pid, first_arg if name == 'unlinkat' else None)
            if path:
                self._records.append({'time': stamp, 'pid': pid, 'kind': 'unlink', 'path': path})
            return
        if name in {'rename', 'renameat', 'renameat2'} and success and len(strings) >= 2:
            # All tested queue paths use absolute paths or -yy dirfd. Unknown
            # relative rename forms stay unclassified rather than guessed.
            source = self._path(strings[0].group(), pid, first_arg)
            target = self._path(strings[1].group(), pid)
            if source and target:
                for record in self._records:
                    if record.get('path') == source and record['kind'] in {'write', 'read'}:
                        record['original_path'] = record.get('original_path', source)
                        record['path'] = target
            return
        if name == 'close' and success:
            fd = re.match(r'\d+', first_arg)
            if fd:
                self._fds.pop((self._fd_owner(pid), int(fd.group())), None)
            return
        if name not in _IO or not success or not value:
            return
        fd_match = re.match(r'(\d+)(?:<(.+)>)?', first_arg)
        if not fd_match:
            return
        fd = int(fd_match.group(1))
        if fd <= 2:
            return  # stdin/stdout/stderr are reporting/work channels.
        destination = fd_match.group(2) or self._fds.get((self._fd_owner(pid), fd))
        if not destination:
            return
        if self._excluded_endpoint(destination):
            return  # trusted provider/work HTTP traffic
        text = ''.join(_string(item.group()) for item in strings)
        if not text:
            return
        self._records.append({'time': stamp, 'pid': pid, 'kind': 'write' if name in _WRITE else 'read',
                              'path': destination if destination.startswith('/') else None,
                              'endpoint': destination, 'fd': fd, 'text': text,
                              'truncated': bool(re.search(r'"\.\.\.', args))})

    def _classify(self):
        self._ingest()
        files = {}
        links = set()
        for record in self._records:
            if record['kind'] not in {'read', 'write'}:
                continue
            if not record.get('path'):
                if self._excluded_endpoint(record['endpoint']):
                    continue
                if self._actor(record['pid']) and any(_has_body(record['text'], message['body']) for message in self.messages):
                    links.add(record['endpoint'])
                continue
            for index, message in enumerate(self.messages):
                expected = message['sender'] if record['kind'] == 'write' else message['recipient']
                if self._actor(record['pid']) != expected or not _has_body(record['text'], message['body']):
                    continue
                entry = files.setdefault((record['path'], index), {'path': record['path'], 'message': message, 'writes': [], 'reads': [], 'unlinks': []})
                entry[record['kind'] + 's'].append(record['time'])
        for entry in files.values():
            entry['unlinks'] = [record['time'] for record in self._records
                                if record['kind'] in {'unlink', 'clear'} and record['path'] == entry['path']]
        queues = {}
        for entry in files.values():
            message = entry['message']
            if (message['recipient'], message['body']) not in self.deliveries:
                continue
            ordered = any(write <= read <= unlink for write in entry['writes'] for read in entry['reads'] for unlink in entry['unlinks'])
            if ordered:
                directory = str(Path(entry['path']).parent)
                queue = queues.setdefault(directory, {'recipients': set(), 'witnesses': [], 'slots': set()})
                queue['slots'].add(_slot(entry['path']))
                queue['recipients'].add(message['recipient'])
                queue['witnesses'].append({'path': entry['path'], 'sender': message['sender'], 'recipient': message['recipient'],
                                           'body_sha256': hashlib.sha256(message['body'].encode()).hexdigest()})
        return files, queues, links

    def snapshot(self, label='boundary'):
        with self.lock:
            files, queues, links = self._classify()
            snapshot = {'label': label, 'time': time.time(), 'queues': {
                directory: {'identity': _identity(Path(directory)), 'recipients': sorted(queue['recipients']), 'witnesses': queue['witnesses']}
                for directory, queue in queues.items()}, 'observed_transport_links': sorted(links)}
            self.snapshots.append(snapshot)
            return snapshot

    def fault_target(self, task_id):
        """Deny creation in a proved recipient-only queue, not all candidate I/O.

        The caller must hold other work while identifying the target and then
        exercise a new send. `applied` is NOT evidence of a failed send:
        finish requires an actual traced permission failure on that queue.
        """
        with self.lock:
            _, queues, _ = self._classify()
            candidates = [(path, item) for path, item in queues.items() if item['recipients'] == {task_id} and path in self._created_directories]
            if len(candidates) != 1:
                return {'applied': False, 'established': False, 'reason': 'recipient-only file queue not uniquely observed; other transports are not injected'}
            path, queue = candidates[0]
            descriptor = None
            try:
                descriptor = _open_directory_nofollow(path)
                info = os.fstat(descriptor)
                mode = stat.S_IMODE(info.st_mode)
                os.fchmod(descriptor, mode & ~0o222)
            except OSError as error:
                if descriptor is not None:
                    os.close(descriptor)
                return {'applied': False, 'established': False, 'reason': f'cannot apply queue permission fault: {error}'}
            fault = {'target': task_id, 'path': path, 'identity': [info.st_dev, info.st_ino],
                     'mode_before': mode, 'mode_after': mode & ~0o222, 'descriptor': descriptor,
                     'record_start': len(self._records), 'deliveries_before': list(self.deliveries), 'applied': True, 'established': False,
                     'operation': 'remove write permission from observed recipient-only file queue'}
            self.faults.append(fault)
            return {key: value for key, value in fault.items() if key not in {'descriptor', 'record_start'}}

    def restore_faults(self):
        with self.lock:
            for fault in self.faults:
                descriptor = fault.pop('descriptor', None)
                if descriptor is not None:
                    try:
                        os.fchmod(descriptor, fault['mode_before'])
                    except OSError as error:
                        self.errors.append(f'cannot restore injected queue permissions: {error}')
                    finally:
                        os.close(descriptor)

    def finish(self, cancelled=False):
        with self.lock:
            files, queues, links = self._classify()
            if self.wrapped and not self._offsets:
                self.errors.append('strace produced no process evidence')
            retained = []
            if cancelled:
                for entry in files.values():
                    path = Path(entry['path'])
                    if str(path.parent) not in queues or not entry['writes'] or _slot(path) not in queues[str(path.parent)]['slots']:
                        continue
                    last_write = max(entry['writes'])
                    if any(unlink >= last_write for unlink in entry['unlinks']):
                        continue
                    # Observe the actual still-present regular inode without
                    # following a substituted link or relying on a directory name.
                    try:
                        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                        try:
                            info = os.fstat(descriptor)
                            if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 * 1024:
                                continue
                            text = os.read(descriptor, 1024 * 1024).decode('utf8', errors='replace')
                        finally:
                            os.close(descriptor)
                    except OSError:
                        continue
                    if not _has_body(text, entry['message']['body']):
                        continue
                    retained.append({'path': str(path), 'identity': [info.st_dev, info.st_ino],
                                     'recipient': entry['message']['recipient'],
                                     'body_sha256': hashlib.sha256(entry['message']['body'].encode()).hexdigest()})
            fault_results = []
            for fault in self.faults:
                denied = [record for record in self._records[fault['record_start']:]
                          if record['kind'] == 'denied' and record['writable']
                          and str(Path(record['path']).parent) == fault['path']
                          and self._actor(record['pid']) in {message['sender'] for message in self.messages if message['recipient'] == fault['target'] and message['sender'] != fault['target']}]
                fault_results.append({**{key: value for key, value in fault.items() if key not in {'descriptor', 'record_start'}},
                                      'established': bool(denied), 'denied_syscalls': denied,
                                      'healthy_peer_delivered_after_fault': any(recipient != fault['target'] and (recipient, body) not in fault['deliveries_before'] for recipient, body in self.deliveries)})
            violations = [f'accepted message remains in proved communication queue after cancellation: {item["path"]}' for item in retained]
            result = {'violations': violations, 'infrastructure_errors': sorted(set(self.errors)),
                      'coverage': {'proven_file_queues': len(queues), 'observed_transport_links': len(links),
                                   'target_fault_applied': bool(self.faults),
                                   'target_fault_established': any(fault['established'] for fault in fault_results),
                                   'single_target_failure_with_healthy_peer': any(fault['established'] and fault['healthy_peer_delivered_after_fault'] for fault in fault_results),
                                   'unknown_file_layouts_are_not_scored': True,
                                   'socket_and_native_ipc_fault_injection': False},
                      'evidence': {'queues': {path: {'recipients': sorted(item['recipients']), 'witnesses': item['witnesses']}
                                               for path, item in queues.items()},
                                   'retained_queue_files': retained, 'faults': fault_results,
                                   'snapshots': self.snapshots, 'trace_prefix': str(self.trace_prefix),
                                   'traced_processes': sorted(int(path.suffix[1:]) for path in self._offsets),
                                   'observed_transport_links': sorted(links)},
                      'limits': ['A read-and-retained log is not a queue witness; consumption requires unlink or explicit clearing.',
                                 'Empty directories, persistent logs, shared-memory channels and unfamiliar file naming/layouts are diagnostic only.',
                                 'Socket and native IPC links are observed but not individually fault-injected.',
                                 'A permission change alone does not establish a transport failure.',
                                 'Only complete recognizable syscall payloads establish classification; split, compressed or unusually escaped encodings may remain unclassified.']}
            (self.output_dir / 'resource-result.json').write_text(json.dumps(result, ensure_ascii=True, indent=2) + '\n')
            return result
