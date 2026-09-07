import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from task_ci import ContractError, command_check_result


class HarborResultTests(unittest.TestCase):
    def check(self, evaluation, expected=1, completed=1, errored=0):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text(json.dumps({"stats": {
                "n_completed_trials": completed, "n_errored_trials": errored,
                "evals": {"nop__adhoc": evaluation},
            }}))
            command_check_result(argparse.Namespace(result=str(path), expected_reward=expected))

    def test_harbor_022_trial_reward(self):
        self.check({"metrics": [{"mean": 1.0}], "reward_stats": {"reward": {"1.0": ["trial"]}}})

    def test_zero_reward_remains_valid_for_negative_cases(self):
        self.check({"reward_stats": {"reward": {"0.0": ["trial"]}}}, expected=0)

    def test_aggregate_mean_cannot_hide_missing_rewards(self):
        with self.assertRaises(ContractError):
            self.check({"metrics": [{"mean": 1.0}], "reward_stats": {}})

    def test_multiple_rewards_and_errors_are_rejected(self):
        with self.assertRaises(ContractError):
            self.check({"reward_stats": {"reward": {"1.0": ["a", "b"]}}})
        with self.assertRaises(ContractError):
            self.check({"reward_stats": {"reward": {"1.0": ["a"]}}}, errored=1)

    def test_legacy_metric_format(self):
        self.check({"metrics": [{"reward": 1.0}]})


if __name__ == "__main__":
    unittest.main()
