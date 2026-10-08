#!/usr/bin/env python3
"""Exercise the real Node inspector and OS child discovery, not mocked reports."""
import importlib.util
import sys
sys.dont_write_bytecode = True
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

TESTS = Path(__file__).resolve().parents[2] / 'tests'
spec = importlib.util.spec_from_file_location('messaging_runtime_observer', TESTS / 'runtime_observer.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


@unittest.skipUnless(os.geteuid() == 0 and shutil.which('node'), 'requires root and the real Node runtime')
class RuntimeObservation(unittest.TestCase):
    def run_node(self, source, child_actor=False):
        with tempfile.TemporaryDirectory(prefix='native-observation-test-') as temporary:
            output = Path(temporary)
            command = ['/usr/bin/python3', '-I', str(TESTS / 'worker_exec.py'), shutil.which('node'), '-e', source]
            process = subprocess.Popen(command, env={'PATH': '/usr/local/bin:/usr/bin:/bin',
                'NODE_OPTIONS': '--inspect-brk=127.0.0.1:0'}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            observer = runtime.RuntimeObserver(process.pid, output, output, 1).start()
            try:
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, stderr)
                pid = int(stdout.strip()) if child_actor else process.pid
                report = observer.finish({'one/worker' if child_actor else 'one/ROOT': pid})
                self.assertFalse(report['infrastructure_errors'], report)
                self.assertTrue(any(record['pid'] == pid and record['completed'] for record in report['inspections']), report)
                return report
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
                observer.finish({})

    def test_successful_node_exit_does_not_prove_pi_execution(self):
        report = self.run_node('process.stdout.write("done")')
        self.assertFalse(report['passed'])
        self.assertIn('no Pi session executed', report['violations'][0])

    def test_worker_is_observed_independently_of_parent_claims(self):
        source = ('const cp=require("node:child_process"); '
                  'const child=cp.spawn(process.execPath,["-e","setTimeout(()=>{},100)"],{stdio:"ignore"}); '
                  'console.log(child.pid);')
        report = self.run_node(source, child_actor=True)
        self.assertFalse(report['passed'])
        self.assertIn('one/worker: no Pi session executed', report['violations'][0])
        self.assertGreaterEqual(len(report['inspections']), 2)

    def test_provider_observation_binds_payload_and_process(self):
        with tempfile.TemporaryDirectory(prefix='native-provider-test-') as temporary:
            source = ('import(' + json.dumps((TESTS / 'trusted_faux.mjs').as_uri()) + ').then(m=>'
                      'console.log(m.observeProviderRequest({messages:[{role:"user",content:"original"}]})))')
            process = subprocess.Popen(['/usr/bin/python3', '-I', str(TESTS / 'worker_exec.py'),
                                        shutil.which('node'), '-e', source],
                env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'NODE_OPTIONS': '--inspect-brk=127.0.0.1:0'},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            observer = runtime.RuntimeObserver(process.pid, Path(temporary), Path(temporary), 1).start()
            try:
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, stderr)
                original = stdout.strip().encode()
                with self.assertRaises(AssertionError):
                    observer.consume_provider_request(process.pid, original.replace(b'original', b'forged'))
                with self.assertRaises(AssertionError):
                    observer.consume_provider_request(process.pid + 100000, original)
                observer.consume_provider_request(process.pid, original)
                with self.assertRaises(AssertionError):
                    observer.consume_provider_request(process.pid, original)
                report = observer.finish({})
                self.assertEqual(len(report['provider_observations']), 1, report)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
                observer.finish({})

    def test_child_endpoints_are_never_inherited_parent_endpoint(self):
        source = ('const cp=require("node:child_process"); '
                  'for(let i=0;i<6;i++) cp.spawn(process.execPath,["-e","setTimeout(()=>{},100)"],{stdio:"ignore"});')
        report = self.run_node(source)
        self.assertGreaterEqual(len(report['inspections']), 7)
        ports = [item['port'] for item in report['inspections']]
        self.assertEqual(len(ports), len(set(ports)))

    def test_forced_shutdown_does_not_erase_execution_failure_or_old_errors(self):
        with tempfile.TemporaryDirectory(prefix='native-shutdown-test-') as temporary:
            process = subprocess.Popen(['/usr/bin/python3', '-I', str(TESTS / 'worker_exec.py'),
                                        shutil.which('node'), '-e', 'setInterval(()=>{},1000)'],
                env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'NODE_OPTIONS': '--inspect-brk=127.0.0.1:0'},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            observer = runtime.RuntimeObserver(process.pid, Path(temporary), Path(temporary), 1).start()
            try:
                deadline = time.monotonic() + 5
                while not observer.inspections.get(process.pid, {}).get('resumed') and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(observer.inspections.get(process.pid, {}).get('resumed'))
                observer.inspections[process.pid]['errors'].append('prior observation failure')
                observer.mark_forced_stop()
                process.kill()
                process.communicate(timeout=5)
                report = observer.finish({'one/ROOT': process.pid}, cancelled=True)
                self.assertFalse(report['passed'])
                self.assertTrue(any('prior observation failure' in item for item in report['infrastructure_errors']))
                self.assertFalse(any('EOFError' in item for item in report['infrastructure_errors']))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
                observer.finish({})

    def test_missing_trusted_provider_is_setup_error(self):
        with tempfile.TemporaryDirectory(prefix='missing-provider-test-') as temporary:
            directory = Path(temporary)
            directory.chmod(0o755)
            for name in ('fixture.ts', 'worker_exec.py'):
                (directory / name).write_text('placeholder')
            with self.assertRaisesRegex(runtime.InspectorError, 'trusted_faux.mjs'):
                runtime.preflight_harness(directory)


if __name__ == '__main__':
    unittest.main()
