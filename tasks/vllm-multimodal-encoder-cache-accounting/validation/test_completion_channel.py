"""Actual native transport regressions; no vLLM/GPU behavior is claimed here."""
from pathlib import Path
import importlib.util
import json
import os
import sys
import tempfile
import unittest

TESTS=Path(__file__).resolve().parents[1]/'tests'
sys.path.insert(0,str(TESTS))
from completion_channel import execute_suite


def honest(inputs,checkpoint):
    checkpoint({'sum':sum(inputs)})


def early_os(inputs,checkpoint):
    os._exit(0)


def early_system(inputs,checkpoint):
    raise SystemExit(0)


def forged_stdout(inputs,checkpoint):
    os.write(1,b'---WORKER-PAYLOAD-BEGIN---\n{"sum":6}\n---WORKER-PAYLOAD-END---\n')
    os._exit(0)


def direct_callback(inputs,checkpoint):
    def candidate():
        import _encoder_checkpoint
        _encoder_checkpoint.emit({'sum':6})
    candidate()


def hang_after_completion(inputs,checkpoint):
    checkpoint({'sum':6})
    import time
    time.sleep(10)


class CompletionTransport(unittest.TestCase):
    def run_case(self,fn,timeout=5):
        with tempfile.TemporaryDirectory() as tmp:
            return execute_suite(fn,[1,2,3],timeout=timeout,candidate_path=tmp,drop_user=None)

    def test_honest_suite(self):
        result=self.run_case(honest)
        self.assertNotIn('error',result)
        self.assertEqual(json.loads(result['payload']),{'sum':6})

    def test_stdout_and_early_exits_do_not_complete(self):
        for fn in [early_os,early_system,forged_stdout,direct_callback]:
            with self.subTest(fn=fn.__name__):
                result=self.run_case(fn)
                self.assertIn('error',result)
                if fn is direct_callback:
                    self.assertIn('completion caller is not the trusted suite',result['diagnostic'])

    def test_hang_after_completion_does_not_pass(self):
        result=self.run_case(hang_after_completion,timeout=0.2)
        self.assertEqual(result['error'],'worker_timeout')

    def test_dynamic_report_forgery_reaches_import_but_cannot_complete(self):
        # Use the actual assembled suite, not a mock grading result.
        spec=importlib.util.spec_from_file_location('encoder_verifier',TESTS/'verify_encoder_cache.py')
        verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'vllm').mkdir()
            (root/'torch.py').write_text('# Import-only stand-in: exit occurs before tensor use.\n')
            patch=(TESTS.parent/'validation/dynamic-report-forgery.patch').read_text()
            # The fixture copies precisely the added candidate import code.
            additions='\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
            additions=additions.replace("'/tests'",repr(str(TESTS)))
            (root/'vllm/__init__.py').write_text(additions)
            result=execute_suite(verifier.RUN_SUITE,verifier.workload(seed=42),
                                 candidate_path=tmp,drop_user=None)
            self.assertEqual(result['error'],'unauthenticated_completion')
            self.assertEqual(result['worker_status'],0)
            self.assertIn('---WORKER-PAYLOAD-BEGIN---',result['diagnostic'])
            self.assertIn('model_inputs_checked',result['diagnostic'])


if __name__=='__main__':unittest.main()
