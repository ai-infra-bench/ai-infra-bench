"""Curator-owned, content-bound adaptation gate; never executes candidate code.

The caller seals /tests before validation. A profile certifies the reviewed
adapter selection for one quiescent workspace, not correctness of that workspace.
Stop candidate processes before fingerprinting; this is not a filesystem snapshot
or a defense against modifications after validation. Symlink targets outside the
workspace are not read and must be controlled by the runtime's isolation policy.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile


SCHEMA = 'pi-reviewed-profile-v1'
SCOPE = {
    'algorithm': 'sha256-canonical-json-tree-v1',
    'root': '/workspace/pi',
    'include': 'all entries, including ignored files, node_modules and source',
    'exclude': 'entries named .git (repository metadata)',
    'symlinks': 'hash link text; never follow',
    'regular_files': 'hash bytes and executable permission bits',
    'special_files': 'reject without opening',
}
ADAPTERS = ('interface_binding.py', 'scenario_binding.py')
REQUIRED_SCORERS = {'grade.py', 'verify.py', 'binding.py', 'scenario.py',
                    'fixture.ts', 'worker_exec.py', 'test.sh', 'profile.py'}


class IntegrationNeeded(RuntimeError):
    """No current reviewed adaptation exists; do not assign a feature score."""


def _signature(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size,
            st.st_mtime_ns, st.st_ctime_ns)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    separators=(',', ':')).encode()).hexdigest()


def _read_regular(directory_fd, name, expected=None, digest_only=False):
    before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise IntegrationNeeded('Expected a regular file: ' + name)
    if expected is not None and _signature(before) != _signature(expected):
        raise IntegrationNeeded('File changed before reading: ' + name)
    # O_PATH obtains identity without opening a device/FIFO for I/O. Only after
    # fstat proves regular do we open this exact inode through our own proc fd.
    identity = os.open(name, os.O_PATH | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        bound = os.fstat(identity)
        if not stat.S_ISREG(bound.st_mode) or _signature(before) != _signature(bound):
            raise IntegrationNeeded('File replaced while binding: ' + name)
        fd = os.open('/proc/self/fd/' + str(identity), os.O_RDONLY | os.O_NONBLOCK)
    finally:
        os.close(identity)
    try:
        current = os.fstat(fd)
        if not stat.S_ISREG(current.st_mode) or _signature(before) != _signature(current):
            raise IntegrationNeeded('File replaced while opening: ' + name)
        chunks = []
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
            if not digest_only:
                chunks.append(chunk)
        if _signature(before) != _signature(os.fstat(fd)):
            raise IntegrationNeeded('File changed while reading: ' + name)
        if _signature(before) != _signature(os.stat(name, dir_fd=directory_fd, follow_symlinks=False)):
            raise IntegrationNeeded('File replaced while reading: ' + name)
        return (size, digest.hexdigest()) if digest_only else b''.join(chunks)
    finally:
        os.close(fd)


def _walk(fd, prefix, entries):
    before = os.fstat(fd)
    names = sorted(name for name in os.listdir(fd) if name != '.git')
    for name in names:
        path = prefix + name
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(name, dir_fd=fd)
            if _signature(info) != _signature(os.stat(name, dir_fd=fd, follow_symlinks=False)):
                raise IntegrationNeeded('Link changed: ' + path)
            entries.append([path, 'symlink', target])
        elif stat.S_ISREG(info.st_mode):
            size, digest = _read_regular(fd, name, info, digest_only=True)
            entries.append([path, 'file', info.st_mode & 0o111,
                            size, digest])
        elif stat.S_ISDIR(info.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                if _signature(info) != _signature(os.fstat(child)):
                    raise IntegrationNeeded('Directory replaced: ' + path)
                entries.append([path, 'directory'])
                _walk(child, path + '/', entries)
                if _signature(info) != _signature(os.stat(name, dir_fd=fd, follow_symlinks=False)):
                    raise IntegrationNeeded('Directory changed: ' + path)
            finally:
                os.close(child)
        else:
            raise IntegrationNeeded('Unsupported special workspace entry: ' + path)
    if (_signature(before) != _signature(os.fstat(fd)) or
            names != sorted(name for name in os.listdir(fd) if name != '.git')):
        raise IntegrationNeeded('Workspace directory changed during scan: ' + prefix)


def workspace_fingerprint(repo):
    """Hash two stable content walks without git, imports, hooks or link traversal."""
    try:
        fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            outputs = []
            for _ in range(2):
                entries = []
                _walk(fd, '', entries)
                outputs.append({'sha256': _digest(entries), 'entry_count': len(entries),
                                'scope': dict(SCOPE)})
            if outputs[0] != outputs[1]:
                raise IntegrationNeeded('Workspace changed between content scans')
            if _signature(os.fstat(fd)) != _signature(os.stat(repo, follow_symlinks=False)):
                raise IntegrationNeeded('Workspace root replaced during scan')
            return outputs[0]
        finally:
            os.close(fd)
    except OSError as exc:
        raise IntegrationNeeded('Cannot fingerprint workspace: ' + str(exc)) from exc


def _tests_files(tests, require_root):
    fd = os.open(tests, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        root = os.fstat(fd)
        if require_root and (root.st_uid != 0 or root.st_mode & 0o022):
            raise IntegrationNeeded('Harness directory is not root-owned and sealed')
        files = {}
        for name in sorted(os.listdir(fd)):
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise IntegrationNeeded('Harness entries must be top-level regular files: ' + name)
            if require_root and (info.st_uid != 0 or info.st_mode & 0o022):
                raise IntegrationNeeded('Harness file is not root-owned and sealed: ' + name)
            files[name] = _read_regular(fd, name, info)
        return files
    finally:
        os.close(fd)


def _scorer_hashes(files):
    if not REQUIRED_SCORERS <= files.keys():
        raise IntegrationNeeded('Incomplete scorer inventory')
    return {name: hashlib.sha256(content).hexdigest() for name, content in files.items()
            if name not in ('profile.json',) + ADAPTERS}


def _atomic_write(path, content):
    fd, temporary = tempfile.mkstemp(prefix='.profile-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def prepare_profile(repo, tests, profile_id, interface_path, scenario_path, review_evidence):
    """Prepare an isolated curator task copy; explicitly supplied adapters only.

    review_evidence is a nonempty JSON object identifying the human/agent review
    and its evidence. It is provenance, not an automatically verified verdict.
    The caller must not supply unreviewed candidate Python as an adapter.
    """
    if not isinstance(profile_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', profile_id):
        raise IntegrationNeeded('A stable, nonempty profile_id is required')
    if not isinstance(review_evidence, dict) or not review_evidence:
        raise IntegrationNeeded('Explicit review evidence is required')
    tests = Path(tests)
    _tests_files(tests, False)
    adapters = []
    for source in (interface_path, scenario_path):
        source = Path(source)
        if Path(repo).resolve() in (source.resolve(), *source.resolve().parents):
            raise IntegrationNeeded('Adapter must come from curator storage, not candidate workspace')
        fd = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            adapters.append(_read_regular(fd, source.name))
        finally:
            os.close(fd)
    workspace = workspace_fingerprint(repo)
    for name, content in zip(ADAPTERS, adapters):
        _atomic_write(tests / name, content)
    files = _tests_files(tests, False)
    manifest = {'schema': SCHEMA, 'profile_id': profile_id,
                'workspace': workspace,
                'interface': {'file': ADAPTERS[0], 'sha256': hashlib.sha256(adapters[0]).hexdigest()},
                'scenario': {'file': ADAPTERS[1], 'sha256': hashlib.sha256(adapters[1]).hexdigest()},
                'scorer_sha256': _scorer_hashes(files), 'review_evidence': review_evidence}
    _atomic_write(tests / 'profile.json', (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode())
    return manifest


def validate_profile(repo, tests):
    """Return reviewed adapter paths and metadata, or IntegrationNeeded; no fallback."""
    try:
        files = _tests_files(tests, True)
        if 'profile.json' not in files:
            raise IntegrationNeeded('No reviewed profile for this submission')
        manifest = json.loads(files['profile.json'])
        if manifest['schema'] != SCHEMA:
            raise IntegrationNeeded('Unsupported reviewed profile schema')
        if not isinstance(manifest['profile_id'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', manifest['profile_id']):
            raise IntegrationNeeded('Invalid reviewed profile identity')
        if not isinstance(manifest['review_evidence'], dict) or not manifest['review_evidence']:
            raise IntegrationNeeded('Missing adaptation review evidence')
        for key, name in zip(('interface', 'scenario'), ADAPTERS):
            if manifest[key] != {'file': name, 'sha256': hashlib.sha256(files[name]).hexdigest()}:
                raise IntegrationNeeded('Reviewed adapter changed or path is invalid: ' + key)
        if manifest['scorer_sha256'] != _scorer_hashes(files):
            raise IntegrationNeeded('Scorer changed; adaptation must be reviewed again')
        if manifest['workspace'] != workspace_fingerprint(repo):
            raise IntegrationNeeded('Workspace changed; adaptation must be reviewed again')
        return Path(tests) / ADAPTERS[0], Path(tests) / ADAPTERS[1], manifest
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise IntegrationNeeded('Reviewed profile is missing, invalid or unreadable: ' + str(exc)) from exc
