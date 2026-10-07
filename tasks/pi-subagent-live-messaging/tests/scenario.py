"""Transport-agnostic scenario helpers. No candidate module is imported here.

The size limit is the one pinned by instruction.md. Cleanup is checked by
scanning every location the untrusted worker UID can write for retained
message bytes, without knowing where or how the candidate stores messages.
"""
import os
from pathlib import Path
import stat

WORKER_UID = 60000
# World-writable locations outside the per-case scratch tree (which holds the
# workers' HOME, TMPDIR, agent directory and working directory).
SHARED_WRITABLE = [Path('/tmp'), Path('/var/tmp'), Path('/dev/shm'), Path('/run/lock')]


class Scenario:
    message_max_utf8_bytes = 1024 * 1024

    def size_payload(self, name, prefix, suffix):
        size = self.message_max_utf8_bytes + {'size_below': -1, 'size_at': 0, 'size_over': 1}[name]
        payload = prefix + '中' * ((size - len((prefix + suffix).encode())) // 3)
        payload += 'x' * (size - len((payload + suffix).encode())) + suffix
        assert len(payload.encode()) == size
        return payload

    @staticmethod
    def _file_contains(dir_fd, name, needles):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
        except OSError:
            return False
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return False
            overlap = max(len(n) for n in needles) - 1
            tail = b''
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    return False
                window = tail + chunk
                if any(n in window for n in needles):
                    return True
                tail = window[-overlap:] if overlap else b''
        finally:
            os.close(fd)

    def _scan(self, root, needles, only_worker_owned, hits, skip):
        # fd-relative walk that never follows symlinks, so a planted link cannot
        # redirect this root-owned scan outside the worker-writable tree.
        try:
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            return
        self._scan_fd(fd, root, needles, only_worker_owned, hits, skip, 0)

    def _scan_fd(self, fd, path, needles, only_worker_owned, hits, skip, depth):
        try:
            if depth > 64:
                hits.append(str(path) + ' (directory nesting too deep to inspect)')
                return
            for name in os.listdir(fd):
                child = path / name
                if child in skip:
                    continue
                try:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except OSError:
                    continue
                if stat.S_ISDIR(info.st_mode):
                    try:
                        child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    except OSError:
                        continue
                    self._scan_fd(child_fd, child, needles, only_worker_owned, hits, skip, depth + 1)
                elif stat.S_ISREG(info.st_mode):
                    if only_worker_owned and info.st_uid != WORKER_UID:
                        continue
                    if self._file_contains(fd, name, needles):
                        hits.append(str(child))
        finally:
            os.close(fd)

    def retained_message_files(self, case, needles):
        """Files anywhere the worker UID can write that still contain a needle."""
        hits = []
        self._scan(case.scratch, needles, False, hits, set())
        for root in SHARED_WRITABLE:
            self._scan(root, needles, True, hits, {case.scratch})
        return hits

    def assert_cancelled_resources(self, case):
        # The unique hex tail of each finding is ASCII, so it survives UTF-8,
        # JSON (including \\u escapes of the CJK prefix) and similar encodings.
        needles = [p[-32:].encode() for payloads in case.payloads.values() for p in payloads]
        hits = self.retained_message_files(case, needles)
        assert not hits, f'cancelled dispatch retained undelivered message content in {hits}'
