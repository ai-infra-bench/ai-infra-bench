import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from task_ci import ContractError, command_check_result
import task_ci
import tomllib


class CandidateTransferTests(unittest.TestCase):
    def test_separate_verifier_keeps_declared_candidate_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "task"
            task.mkdir()
            for mode in ("separate", "shared"):
                with self.subTest(mode=mode):
                    (task / "task.toml").write_text(
                        'artifacts = ["/workspace/repo"]\n'
                        '[environment]\nworkdir = "/workspace/repo"\n'
                        f'[verifier]\nenvironment_mode = "{mode}"\n'
                    )
                    output = root / mode
                    self.assertEqual(task_ci.prepare_case(task, "example-image", "base", output), "nop")
                    config = tomllib.loads((output / "task.toml").read_text())
                    self.assertEqual(config["artifacts"], ["/workspace/repo"] if mode == "separate" else [])


class TaskHardwareTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tasks_dir = Path(directory.name)
        self.task = self.tasks_dir / "example"
        (self.task / "validation").mkdir(parents=True)
        (self.task / "validation/ci-cases.json").write_text(json.dumps({
            "schema_version": "ai_infra_bench_validation_cases.v1", "cases": [],
        }))

    def configure(self, **environment):
        values = {"workdir": "/workspace/repo", **environment}
        (self.task / "task.toml").write_text(
            "[environment]\n" + "".join(
                f"{key} = {json.dumps(value)}\n" for key, value in values.items()
            )
        )

    def hardware_check(self, names):
        output = io.StringIO()
        with (
            patch.object(task_ci, "TASKS_DIR", self.tasks_dir),
            patch.object(task_ci.platform, "machine", return_value="x86_64"),
            patch.object(task_ci.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 0, stdout="\n".join(names),
            )) as query,
            redirect_stdout(output),
        ):
            task_ci.command_hardware_check(argparse.Namespace(task="example"))
        return json.loads(output.getvalue()), query

    def test_cpu_explicit_and_default_do_not_probe_gpus(self):
        for environment in ({}, {"gpus": 0}):
            with self.subTest(environment=environment):
                self.configure(**environment)
                entry = task_ci.matrix_entry(self.task, "pr")
                self.assertEqual(entry["gpus"], 0)
                self.assertEqual(entry["runs_on"], ["ubuntu-24.04"])
                self.assertEqual(entry["approval_environment"], "automatic-task-validation")
                result, query = self.hardware_check([])
                self.assertEqual(result["gpus"], 0)
                query.assert_not_called()

    def test_gpu_counts_models_and_alternatives_select_a100_runner(self):
        for count in (1, 2, 4):
            for gpu_types in (None, ["A100"], ["NVIDIA A100-SXM4-40GB"], ["H100", "A100"]):
                with self.subTest(count=count, gpu_types=gpu_types):
                    environment = {"gpus": count}
                    if gpu_types is not None:
                        environment["gpu_types"] = gpu_types
                    self.configure(**environment)
                    entry = task_ci.matrix_entry(self.task, "pr")
                    self.assertEqual(entry["gpus"], count)
                    self.assertEqual(entry["gpu_types"], gpu_types or [])
                    self.assertIn("a100", entry["runs_on"])
                    self.assertEqual(entry["approval_environment"], "task-validation")
                    self.assertEqual(entry["data_proxy_url"], "http://127.0.0.1:7892")
                    self.assertEqual(task_ci.matrix_entry(self.task, "manual")["approval_environment"], "manual-task-validation")

    def test_invalid_or_unsupported_gpu_requests_fail_before_routing(self):
        invalid = [
            {"gpus": value} for value in (-1, True, False, 1.5, "1", 3, 8)
        ] + [
            {"gpus": 1, "gpu_types": value}
            for value in ("A100", [""], [1], ["H100"], ["NotA100"], ["A1000"])
        ] + [{"gpus": 0, "gpu_types": ["A100"]}]
        for environment in invalid:
            with self.subTest(environment=environment):
                self.configure(**environment)
                with self.assertRaises(ContractError):
                    task_ci.task_contract(self.task)

    def test_custom_hardware_fields_are_rejected(self):
        for environment in ({"accelerator": "CPU"}, {"gpus": 1, "topology": 1}):
            with self.subTest(environment=environment):
                self.configure(**environment)
                with self.assertRaisesRegex(ContractError, "use .*gpus and gpu_types"):
                    task_ci.task_contract(self.task)
        self.configure(gpus=1)
        with (self.task / "task.toml").open("a") as stream:
            stream.write('\n[metadata]\nenvironment_profile = "gpu"\n')
        with self.assertRaisesRegex(ContractError, "use .*gpus and gpu_types"):
            task_ci.task_contract(self.task)

    def test_gpu_model_constraints_and_count_are_checked_on_host(self):
        for gpu_types in (["A100"], ["A100-40GB"], ["NVIDIA A100-SXM4-40GB"], ["H100", "A100"]):
            with self.subTest(gpu_types=gpu_types):
                self.configure(gpus=2, gpu_types=gpu_types)
                result, _ = self.hardware_check(["NVIDIA A100-SXM4-40GB"] * 2)
                self.assertEqual(result["gpus"], 2)
                self.assertEqual(result["gpu_types"], gpu_types)
        for gpu_types, names in (
            (["A100"], ["NVIDIA A100-SXM4-40GB"]),
            (["A100"], ["NVIDIA H100"] * 2),
            (["A100-80GB"], ["NVIDIA A100-SXM4-40GB"] * 2),
        ):
            with self.subTest(gpu_types=gpu_types, names=names):
                self.configure(gpus=2, gpu_types=gpu_types)
                with self.assertRaisesRegex(ContractError, "requires 2 GPUs"):
                    self.hardware_check(names)


class HarborResultTests(unittest.TestCase):
    def test_oracle_execution_failure_cannot_pass_matching_feature_reward(self):
        # Harbor 0.22 writes this sidecar on Oracle failure, but can still
        # report a completed trial with no exception and the expected reward.
        for expected in (0, 1):
            for status in ("1", "128\n", "not-an-exit-code", ""):
                with self.subTest(expected=expected, status=status), tempfile.TemporaryDirectory() as directory:
                    job = Path(directory)
                    agent = job / "trial/agent"
                    agent.mkdir(parents=True)
                    (agent / "exit-code.txt").write_text(status)
                    result = job / "result.json"
                    result.write_text(json.dumps({"stats": {
                        "n_completed_trials": 1, "n_errored_trials": 0,
                        "evals": {"oracle": {"reward_stats": {"reward": {str(expected): ["trial"]}}}},
                    }}))
                    with self.assertRaisesRegex(ContractError, "Oracle"):
                        command_check_result(argparse.Namespace(result=str(result), expected_reward=expected))

    def test_oracle_exit_status_does_not_follow_symlinks(self):
        for linked_part in ("exit-code.txt", "agent", "trial"):
            with self.subTest(linked_part=linked_part), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                job = root / "job"
                agent = job / "trial/agent"
                agent.mkdir(parents=True)
                (agent / "exit-code.txt").write_text("0")
                linked = {"exit-code.txt": agent / "exit-code.txt", "agent": agent, "trial": agent.parent}[linked_part]
                target = root / "outside"
                linked.rename(target)
                linked.symlink_to(target)
                result = job / "result.json"
                result.write_text(json.dumps({"stats": {
                    "n_completed_trials": 1, "n_errored_trials": 0,
                    "evals": {"oracle": {"reward_stats": {"reward": {"1": ["trial"]}}}},
                }}))
                with self.assertRaisesRegex(ContractError, "Oracle"):
                    command_check_result(argparse.Namespace(result=str(result), expected_reward=1))

    def test_failed_reward_prints_bounded_verifier_output_without_following_links(self):
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory) / "job"
            log = job / "trial/verifier/test-stdout.txt"
            log.parent.mkdir(parents=True)
            log.write_text("omitted-prefix" + "x" * 70000 + "\nstartup timeout traceback\n")
            outside = Path(directory) / "outside.txt"
            outside.write_text("must-not-print-outside-content")
            linked = job / "other/verifier/test-stdout.txt"
            linked.parent.mkdir(parents=True)
            linked.symlink_to(outside)
            result = job / "result.json"
            result.write_text(json.dumps({"stats": {
                "n_completed_trials": 1, "n_errored_trials": 0,
                "evals": {"oracle": {"reward_stats": {"reward": {"0": ["trial"]}}}},
            }}))
            output = io.StringIO()
            with redirect_stdout(output), self.assertRaises(ContractError):
                command_check_result(argparse.Namespace(result=str(result), expected_reward=1))
            self.assertIn("startup timeout traceback", output.getvalue())
            self.assertNotIn("omitted-prefix", output.getvalue())
            self.assertNotIn("must-not-print-outside-content", output.getvalue())

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
