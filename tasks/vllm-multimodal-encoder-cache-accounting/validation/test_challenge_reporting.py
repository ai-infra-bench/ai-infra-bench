"""Diagnostic infrastructure failures must not establish Base behavior failures."""
import importlib.util
import json
from pathlib import Path
import unittest

path = Path(__file__).resolve().parent / 'curator-tools/check_environment.py'
spec = importlib.util.spec_from_file_location('environment_diagnostic', path)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


class ChallengeReporting(unittest.TestCase):
    def test_original_index_error_is_not_expected_base_failure(self):
        with self.assertRaises(ValueError):
            diagnostic.challenge_result('Traceback ...\nIndexError: 2\n', 1)

    def test_missing_source_and_setup_errors_are_not_behavior(self):
        for kind in ('execution_error', 'setup_error'):
            report = {'status': kind, 'stage': 'setup', 'error': 'missing /tests'}
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                diagnostic.challenge_result('CHALLENGE_RESULT=' + json.dumps(report), 2)

    def test_completed_behavior_and_matching_exit_are_required(self):
        for status, code in [('pass', 0), ('behavior_mismatch', 1)]:
            report = {'status': status, 'stage': 'capacity_behavior'}
            text = 'CHALLENGE_RESULT=' + json.dumps(report)
            self.assertEqual(diagnostic.challenge_result(text, code), report)
            with self.assertRaises(ValueError):
                diagnostic.challenge_result(text, 1 - code)

    def test_missing_or_duplicate_completion_is_rejected(self):
        frame = 'CHALLENGE_RESULT={"status":"pass","stage":"model_inputs"}'
        for text in ('', frame + '\n' + frame):
            with self.subTest(text=text), self.assertRaises(ValueError):
                diagnostic.challenge_result(text, 0)


if __name__ == '__main__':
    unittest.main()
