#!/usr/bin/env python3
"""Grade outcomes distinguish product failure from missing/invalid observation."""
import importlib.util
import sys
sys.dont_write_bytecode = True
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[2] / 'tests' / 'grade.py'
spec = importlib.util.spec_from_file_location('messaging_grade', path)
grade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grade)


def summary(passed=True, **fields):
    result = {'name': 'direct', 'passed': passed, 'runtime_observation': {'passed': True}, **fields}
    return {'results': [result], 'case_count': 1, 'passed': int(passed)}


class GradingCompletion(unittest.TestCase):
    def test_complete_observed_behavior_scores(self):
        self.assertEqual(grade.score_completed_results(summary(), ['direct'], 0), 1)

    def test_explicit_product_failure_still_scores_zero(self):
        self.assertEqual(grade.score_completed_results(summary(False, errors=['wrong recipient']), ['direct'], 1), 0)

    def test_all_pass_flags_cannot_replace_native_execution(self):
        with self.assertRaises(grade.ScoringError):
            grade.score_completed_results(summary(runtime_observation={}), ['direct'], 0)

    def test_unknown_representation_is_not_product_zero(self):
        with self.assertRaisesRegex(grade.ScoringError, 'unsupported representation'):
            grade.score_completed_results(summary(False, infrastructure_errors=['unsupported representation']), ['direct'], 1)

    def test_zero_exit_cannot_replace_missing_cases(self):
        with self.assertRaises(grade.ScoringError):
            grade.score_completed_results(summary(), ['direct', 'ordered'], 0)

    def test_corrupt_pass_count_is_not_accepted(self):
        data = summary(False)
        data['passed'] = 1
        with self.assertRaises(grade.ScoringError):
            grade.score_completed_results(data, ['direct'], 0)

    def test_post_check_runner_failure_is_unscored(self):
        with self.assertRaises(grade.ScoringError):
            grade.score_completed_results(summary(), ['direct'], 1)


if __name__ == '__main__':
    unittest.main()
