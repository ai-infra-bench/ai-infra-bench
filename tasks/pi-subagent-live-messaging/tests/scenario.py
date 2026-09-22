"""Curator-owned scenario adaptation, separate from public tool adaptation.

Default profile: reference file transport. Other transports require a reviewed
profile; missing adaptation is an integration error, never evidence of a feature
failure. No candidate module is imported here. Faults affect real OS resources.
"""
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
from profile import IntegrationNeeded


class Scenario:
    message_max_utf8_bytes = 1024 * 1024

    def size_payload(self, name, prefix, suffix):
        """Reference's documented UTF-8 limit, not a task-wide requirement.

        A reviewed profile overrides this method for other size units/policies.
        The actual candidate still accepts/rejects and transports the payload.
        """
        size = self.message_max_utf8_bytes + {'size_below': -1, 'size_at': 0, 'size_over': 1}[name]
        payload = prefix + '中' * ((size - len((prefix + suffix).encode())) // 3)
        payload += 'x' * (size - len((payload + suffix).encode())) + suffix
        assert len(payload.encode()) == size
        return payload

    def directory(self, case, group, role):
        hints = next((e["resourceHints"] for e in reversed(case.events)
                      if e["group"] == group and e["role"] == role and "resourceHints" in e), {})
        if "PI_TEAM_DIRECTORY" not in hints:
            raise IntegrationNeeded('Scenario integration required: this transport is not the reviewed file transport')
        path = Path(hints["PI_TEAM_DIRECTORY"])
        path.relative_to(case.scratch)  # no arbitrary privileged filesystem access
        if '..' in path.parts: raise RuntimeError('Unsafe resource path')
        return path

    def open_directory(self, case, path):
        parts = path.relative_to(case.scratch).parts
        fd = os.open(case.scratch, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            return fd
        except BaseException:
            os.close(fd)
            raise

    def observe_team(self, case, group, role):
        path = self.directory(case, group, role)
        fd = self.open_directory(case, path)
        os.close(fd)
        if path not in case.resources: case.resources.append(path)
        return path

    def block_recipient(self, case, group, role):
        directory = self.observe_team(case, group, role)
        mailbox = directory / hashlib.sha256(role.encode()).hexdigest()
        fd = self.open_directory(case, mailbox)
        mode = stat.S_IMODE(os.fstat(fd).st_mode)
        os.fchmod(fd, 0o500)  # recipient can read; sender's real write gets EACCES
        return fd, {'recipient': role, 'resource': str(mailbox), 'fault': 'write permission removed', 'original_mode': mode}

    def restore_fault(self, fault):
        fd, evidence = fault
        os.fchmod(fd, evidence['original_mode'])
        os.close(fd)

    def assert_cancelled_resources(self, case):
        assert case.resources, 'communication resources were not observed while active'
        # Ordinary logs and empty directories are allowed. Inspect only mailboxes
        # actually used by this dispatch for retained undelivered message content.
        for directory in case.resources:
            for role in case.roles:
                mailbox = directory / hashlib.sha256(role.encode()).hexdigest()
                try: fd = self.open_directory(case, mailbox)
                except FileNotFoundError: continue
                try:
                    for name in os.listdir(fd):
                        child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                        try:
                            info = os.fstat(child)
                            if stat.S_ISREG(info.st_mode):
                                raw = os.read(child, min(info.st_size, 4 * 1024 * 1024))
                                for payloads in case.payloads.values():
                                    for payload in payloads:
                                        assert payload.encode() not in raw, 'cancelled dispatch retained an undelivered finding in its communication mailbox'
                        finally: os.close(child)
                finally: os.close(fd)


def load_scenario(path):
    if path is None:
        raise IntegrationNeeded('An explicit reviewed scenario profile is required')
    try:
        spec = importlib.util.spec_from_file_location('reviewed_scenario', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Scenario()
    except IntegrationNeeded:
        raise
    except Exception as exc:
        # A broken curator adapter is an integration failure. Scenario methods
        # that inspect candidate behavior execute outside this loading guard.
        raise IntegrationNeeded(f'Cannot load reviewed scenario {path}: {type(exc).__name__}: {exc}') from exc
