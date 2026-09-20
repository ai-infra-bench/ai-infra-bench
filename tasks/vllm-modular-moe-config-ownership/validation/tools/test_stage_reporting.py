"""Reporting-only regression tests; full scoring is validated separately on GPU."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))
import check_behavior


class StageReportingTests(unittest.TestCase):
    def setUp(self):
        self.raw = {
            'warnings': [], 'numerics': [], 'flashinfer_pipeline': [],
            'dp_workspace_bytes': 32768, 'ordinary_workspace_bytes': 2,
            'dp_consumer_workspace_bytes': 32768, 'ordinary_consumer_workspace_bytes': 2,
            'lora_dp_workspace_bytes': 32768, 'lora_ordinary_workspace_bytes': 2,
            'functional_workspace_bytes': 2,
        }
        self.workload = {'numerics': [{'x': [[0]], 'w1': [[[0]]], 'ids': [[0]]}],
                         'flashinfer_pipeline': []}

    def test_success_yields_every_stage_once(self):
        with patch.object(check_behavior, 'check_numerics'):
            self.assertEqual(check_behavior.check(self.raw, self.workload),
                             check_behavior.EXPECTED_STAGES)

    def test_failure_retains_only_completed_stages(self):
        mutations = [
            ('warnings', ['Current vLLM config is not set']),
            ('dp_workspace_bytes', 1),
            ('numerics', None),
            ('dp_consumer_workspace_bytes', 1),
            ('lora_dp_workspace_bytes', 1),
            ('functional_workspace_bytes', 3),
            ('flashinfer_pipeline', [{}]),
        ]
        for index, (field, value) in enumerate(mutations):
            with self.subTest(stage=check_behavior.EXPECTED_STAGES[index]):
                raw = copy.deepcopy(self.raw)
                raw[field] = value
                passed = []
                with patch.object(check_behavior, 'check_numerics',
                                  side_effect=AssertionError('numerical failure') if index == 2 else None):
                    with self.assertRaises(AssertionError):
                        for stage in check_behavior.check_stages(raw, self.workload):
                            passed.append(stage)
                self.assertEqual(passed, check_behavior.EXPECTED_STAGES[:index])

    def test_missing_observation_does_not_mark_stage_passed(self):
        del self.raw['lora_dp_workspace_bytes']
        passed = []
        with patch.object(check_behavior, 'check_numerics'):
            with self.assertRaises(KeyError):
                for stage in check_behavior.check_stages(self.raw, self.workload):
                    passed.append(stage)
        self.assertEqual(passed, check_behavior.EXPECTED_STAGES[:4])


if __name__ == '__main__':
    unittest.main()
