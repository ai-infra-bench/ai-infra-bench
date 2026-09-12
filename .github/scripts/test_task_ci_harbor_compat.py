"""Regression checks for Harbor result summaries and control preparation."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('task_ci', Path(__file__).with_name('task_ci.py'))
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


class HarborResults(unittest.TestCase):
    def parse(self, stats):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'result.json'
            path.write_text(json.dumps({'stats': stats}))
            return ci.result_reward(path)

    def test_individual_rewards_override_aggregate_mean(self):
        stats = {'n_completed_trials': 2, 'n_errored_trials': 0,
                 'evals': {'eval': {'metrics': [{'reward': 0.5}],
                                    'reward_stats': {'reward': {'0': ['failed'], '1': ['passed']}}}}}
        self.assertEqual(self.parse(stats), (2, 0, [0.0, 1.0]))

    def test_empty_bucket_is_not_a_trial(self):
        stats = {'n_completed_trials': 1, 'n_errored_trials': 0,
                 'evals': {'eval': {'reward_stats': {'reward': {'0': [], '1': ['passed']}}}}}
        self.assertEqual(self.parse(stats), (1, 0, [1.0]))

    def test_duplicate_trial_and_incomplete_results_are_rejected(self):
        for buckets in [{'0': ['same'], '1': ['same']}, {'0': ['only-one']}]:
            with self.subTest(buckets=buckets), self.assertRaises(ci.ContractError):
                self.parse({'n_completed_trials': 2, 'n_errored_trials': 0,
                            'evals': {'eval': {'reward_stats': {'reward': buckets}}}})

    def test_invalid_reward_map_does_not_fall_back_to_mean(self):
        with self.assertRaises(ci.ContractError):
            self.parse({'n_completed_trials': 1, 'n_errored_trials': 0,
                        'evals': {'eval': {'metrics': [{'reward': 1}], 'reward_stats': {}}}})

    def test_legacy_summary_is_still_supported(self):
        self.assertEqual(self.parse({'n_completed_trials': 1, 'n_errored_trials': 0,
                                     'evals': {'eval': {'metrics': [{'reward': 0}]}}}),
                         (1, 0, [0.0]))

    def test_verifier_only_mode_is_preserved(self):
        self.assertEqual(ci.task_validation_mode(Path('unused'),
                         {'metadata': {'validation_mode': 'verifier_only'}}), 'verifier_only')


if __name__ == '__main__':
    unittest.main()
