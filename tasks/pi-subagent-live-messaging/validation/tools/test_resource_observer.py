#!/usr/bin/env python3
"""Regression controls for the implementation-independent syscall observer."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[2] / 'tests/resource_observer.py'
spec = importlib.util.spec_from_file_location('resource_observer', MODULE)
resource = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resource)


class ObserverControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.queue = self.root / 'arbitrary-layout' / 'recipient'
        self.queue.mkdir(parents=True)
        self.observer = resource.ResourceObserver(self.root, self.root / 'evidence', 43125)
        self.observer.observe_event({'kind': 'actor', 'pid': 101, 'task_id': 'sender'})
        self.observer.observe_event({'kind': 'actor', 'pid': 202, 'task_id': 'recipient'})
        self.body = '接口\nrandom-19cda1 "complete"'
        self.next_body = 'queued\nrandom-008832'
        for body in [self.body, self.next_body]:
            self.observer.observe_event({'kind': 'message', 'sender': 'sender', 'recipient': 'recipient', 'body': body})
        self.lines = {101: [f'0.010000 mkdir(\"{self.queue}\", 0700) = 0\n'], 202: []}

    def tearDown(self):
        self.observer.restore_faults()
        self.tmp.cleanup()

    def line(self, pid, time, call):
        self.lines[pid].append(f'{time:.6f} {call}\n')

    def io(self, pid, time, direction, path, body):
        envelope = json.dumps({'body': body}, ensure_ascii=False)
        self.line(pid, time, f'{direction}(9<{path}>, {json.dumps(envelope)}, {len(envelope)}) = {len(envelope)}')

    def flush(self):
        for pid, lines in self.lines.items():
            Path(str(self.observer.trace_prefix) + f'.{pid}').write_text(''.join(lines))

    def warmup(self, path=None, consume=True, deliver=True):
        path = path or self.queue / 'item-1.json'
        self.io(101, 1.0, 'write', path, self.body)
        self.io(202, 2.0, 'read', path, self.body)
        if consume:
            self.line(202, 3.0, f'unlink({json.dumps(str(path))}) = 0')
        if deliver:
            self.observer.observe_event({'kind': 'delivery', 'recipient': 'recipient', 'body': self.body})
        return path

    def pending(self):
        path = self.queue / 'item-2.json'
        path.write_text(json.dumps({'body': self.next_body}))
        self.io(101, 4.0, 'write', path, self.next_body)
        return path

    def test_known_queue_leak_is_rejected(self):
        self.warmup()
        pending = self.pending()
        self.flush()
        result = self.observer.finish(cancelled=True)
        self.assertTrue(result['violations'], result)
        self.assertEqual(result['evidence']['retained_queue_files'][0]['path'], str(pending))

    def test_cleaned_queue_is_accepted(self):
        self.warmup()
        pending = self.pending()
        pending.unlink()
        self.line(202, 5.0, f'unlink({json.dumps(str(pending))}) = 0')
        self.flush()
        self.assertEqual(self.observer.finish(cancelled=True)['violations'], [])

    def test_persistent_log_read_by_peer_is_not_a_queue(self):
        log = self.queue / 'audit.log'
        self.warmup(log, consume=False)
        log.write_text(json.dumps({'body': self.body}))
        self.flush()
        result = self.observer.finish(cancelled=True)
        self.assertEqual(result['violations'], [])
        self.assertEqual(result['coverage']['proven_file_queues'], 0)

    def test_writer_readback_is_not_peer_delivery(self):
        self.io(101, 1, 'write', self.queue / 'item-1.json', self.body)
        self.io(101, 2, 'read', self.queue / 'item-1.json', self.body)
        self.line(101, 3, f'unlink({json.dumps(str(self.queue / "warm"))}) = 0')
        self.pending()
        self.flush()
        self.assertEqual(self.observer.finish(cancelled=True)['violations'], [])

    def test_missing_context_delivery_does_not_classify_log(self):
        self.warmup(deliver=False)
        self.pending()
        self.flush()
        self.assertEqual(self.observer.finish(cancelled=True)['violations'], [])

    def test_same_directory_audit_file_is_not_pending_message(self):
        self.warmup()
        (self.queue / 'audit').write_text(self.next_body)
        self.io(101, 4, 'write', self.queue / 'audit', self.next_body)
        self.flush()
        self.assertEqual(self.observer.finish(cancelled=True)['violations'], [])

    def test_already_consumed_file_name_reused_by_log_is_not_leak(self):
        path = self.warmup()
        path.write_text('ordinary log')
        self.flush()
        self.assertEqual(self.observer.finish(cancelled=True)['violations'], [])

    def test_observer_does_not_follow_symlink_to_retained_payload(self):
        self.warmup()
        path = self.pending()
        destination = self.root / 'unrelated'
        path.rename(destination)
        path.symlink_to(destination)
        self.flush()
        self.assertEqual(self.observer.finish(cancelled=True)['violations'], [])

    def test_shared_queue_cannot_be_targeted(self):
        self.warmup()
        self.observer.observe_event({'kind': 'actor', 'pid': 303, 'task_id': 'other'})
        self.observer.observe_event({'kind': 'message', 'sender': 'sender', 'recipient': 'other', 'body': 'second-random'})
        self.observer.observe_event({'kind': 'delivery', 'recipient': 'other', 'body': 'second-random'})
        path = self.queue / 'other'
        self.io(101, 4, 'write', path, 'second-random')
        self.lines[303] = [f'5.000000 read(9<{path}>, "second-random", 13) = 13\n', f'6.000000 unlink("{path}") = 0\n']
        self.flush()
        result = self.observer.fault_target('recipient')
        self.assertFalse(result['established'], result)
        self.assertEqual(self.queue.stat().st_mode & 0o777, 0o755)

    def test_fault_application_is_not_claimed_as_actual_failure(self):
        self.warmup()
        self.flush()
        result = self.observer.fault_target('recipient')
        self.assertTrue(result['applied'], result)
        self.assertFalse(result['established'], result)
        self.assertFalse(self.observer.finish()['coverage']['target_fault_established'])

    def test_real_eacces_establishes_target_failure(self):
        self.warmup()
        self.flush()
        self.observer.fault_target('recipient')
        self.line(101, 9, f'openat(AT_FDCWD, "{self.queue}/blocked", O_WRONLY|O_CREAT, 0666) = -1 EACCES (Permission denied)')
        self.flush()
        self.assertTrue(self.observer.finish()['coverage']['target_fault_established'])

    def test_late_registered_inspector_port_is_excluded(self):
        self.line(101, 1, 'write(8<TCP:[127.0.0.1:5522->127.0.0.1:44331]>, ' + json.dumps(self.body) + ', 128) = 128')
        self.flush()
        self.observer.snapshot('before-inspector-registration')
        self.observer.observe_event({'kind': 'exclude_port', 'port': 44331})
        self.assertEqual(self.observer.finish()['coverage']['observed_transport_links'], 0)

    def test_provider_socket_excluded(self):
        self.line(101, 1, 'write(8<TCP:[127.0.0.1:5522->127.0.0.1:43125]>, "secret", 6) = 6')
        self.flush()
        self.assertEqual(self.observer.finish()['coverage']['observed_transport_links'], 0)


@unittest.skipUnless(shutil.which('strace') and hasattr(os, 'fork'), 'requires Linux strace')
class RealSyscallControls(unittest.TestCase):
    def exercise(self, layout, mode):
        with tempfile.TemporaryDirectory(prefix='resource-controls-') as temp:
            root = Path(temp)
            fixture = Path(__file__).with_name('resource_fixture.py')
            if mode == 'fault':
                root.chmod(0o755)
                os.chown(root, 60000, 60000)
            observer = resource.ResourceObserver(root, root / 'evidence', 45001)
            # Evidence must remain separate from writable candidate state.
            (root / 'evidence').chmod(0o700)
            process = subprocess.Popen(observer.wrap_command([sys.executable, str(fixture), str(root), layout, mode]),
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                identities = json.loads(process.stdout.readline())
                for role, pid in identities.items():
                    observer.observe_event({'kind': 'actor', 'pid': pid, 'task_id': role})
                for role in ['recipient', 'healthy']:
                    for prefix in ['warmup', 'pending']:
                        body = f'{prefix}-{role}-' + ('231124' if prefix == 'warmup' else '22142') + '-接口'
                        observer.observe_event({'kind': 'message', 'sender': 'sender', 'recipient': role, 'body': body})
                process.stdin.write('\n'); process.stdin.flush()
                self.assertEqual(process.stdout.readline().strip(), 'delivered')
                for role in ['recipient', 'healthy']:
                    observer.observe_event({'kind': 'delivery', 'recipient': role, 'body': f'warmup-{role}-231124-接口'})
                observer.snapshot('warmup-delivered')
                if mode == 'fault':
                    fault = observer.fault_target('recipient')
                    self.assertTrue(fault['applied'], fault)
                    self.assertFalse(fault['established'], fault)
                process.stdin.write('\n'); process.stdin.flush()
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, stderr)
                outcome = json.loads(stdout)
                if mode == 'fault':
                    self.assertEqual([entry['role'] for entry in outcome['failures']], ['recipient'])
                    observer.observe_event({'kind': 'delivery', 'recipient': 'healthy', 'body': 'pending-healthy-22142-接口'})
                result = observer.finish(cancelled=mode != 'fault')
                self.assertEqual(result['infrastructure_errors'], [], result)
                self.assertEqual(bool(result['violations']), mode == 'leak', result)
                if layout in {'tcp', 'ipc'}:
                    self.assertEqual(result['coverage']['proven_file_queues'], 0, result)
                    self.assertGreater(result['coverage']['observed_transport_links'], 0, result)
                else:
                    self.assertEqual(result['coverage']['proven_file_queues'], 2, result)
                if mode == 'fault':
                    self.assertTrue(result['coverage']['single_target_failure_with_healthy_peer'], result)
                observer.restore_faults()
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
                observer.restore_faults()

    def test_actual_per_entry_queue_cleanup_and_leak(self):
        for mode in ['clean', 'leak']:
            with self.subTest(mode=mode): self.exercise('entries', mode)

    def test_actual_fixed_spool_cleanup_and_leak(self):
        for mode in ['clean', 'leak']:
            with self.subTest(mode=mode): self.exercise('spool', mode)

    def test_actual_truncated_spool_cleanup_and_leak(self):
        for mode in ['clean', 'leak']:
            with self.subTest(mode=mode): self.exercise('truncate', mode)

    def test_actual_tcp_is_not_misclassified_as_files(self):
        self.exercise('tcp', 'clean')

    def test_actual_native_socketpair_is_not_misclassified_as_files(self):
        self.exercise('ipc', 'clean')

    @unittest.skipUnless(os.geteuid() == 0, 'permission injection control drops to UID 60000')
    def test_actual_single_target_eacces_keeps_peer_healthy(self):
        self.exercise('entries', 'fault')


if __name__ == '__main__':
    unittest.main()
