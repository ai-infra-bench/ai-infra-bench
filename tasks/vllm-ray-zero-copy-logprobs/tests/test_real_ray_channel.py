#!/usr/bin/env python3
"""Exercise the PP-style vLLM result boundary over a real Ray SHM channel."""

from __future__ import annotations

import os
from types import SimpleNamespace

import numpy as np
import ray
import torch
from ray.dag import InputNode
from ray.util.scheduling_strategies import NodeAffinitySchedulingStrategy

from vllm.v1.executor.ray_executor import RayDistributedExecutor
from vllm.v1.executor.ray_utils import RayWorkerWrapper
from vllm.v1.outputs import LogprobsTensors, ModelRunnerOutput


class _OutputModelRunner:
    supports_mm_inputs = False

    def __init__(self, output):
        self.output = output

    def execute_model(self, _scheduler_output, _intermediate_tensors):
        return self.output


class _HarnessRayWorker(RayWorkerWrapper):
    def setup_device_if_necessary(self):
        return None

    def _is_last_rank(self) -> bool:
        return True


def _through_worker_boundary(output):
    wrapper = _HarnessRayWorker()
    wrapper.worker = SimpleNamespace(model_runner=_OutputModelRunner(output))
    return wrapper.execute_model_ray((None, None))


@ray.remote(num_cpus=1)
class _Stage:
    def node_id(self) -> str:
        return ray.get_runtime_context().get_node_id()

    def make_output(self, case_id: int) -> object:
        if case_id == 50:
            output = ModelRunnerOutput(
                req_ids=["no-logprobs"],
                req_id_to_index={"no-logprobs": 0},
                sampled_token_ids=[[case_id]],
                logprobs=None,
            )
        else:
            rows, cols = {
                10: (1, 2),
                20: (3, 5),
                30: (64, 32),
                40: (2, 1),
                60: (7, 11),
                70: (4, 17),
            }[case_id]
            token_ids = (
                torch.arange(rows * cols, dtype=torch.int32).reshape(rows, cols)
                + case_id
            )
            logprobs = torch.linspace(
                -case_id / 10,
                -0.001,
                rows * cols,
                dtype=torch.float32,
            ).reshape(rows, cols)
            ranks = torch.arange(rows, dtype=torch.int16) + case_id
            sampled_token_ids = [
                [case_id + index * cols] for index in range(rows)
            ]
            output = ModelRunnerOutput(
                req_ids=[f"req-{case_id}-{index}" for index in range(rows)],
                req_id_to_index={
                    f"req-{case_id}-{index}": index for index in range(rows)
                },
                sampled_token_ids=sampled_token_ids,
                logprobs=LogprobsTensors(
                    token_ids,
                    logprobs,
                    ranks,
                    list(range(rows + 1)),
                ).tolists(),
            )
        return _through_worker_boundary(output)

    def forward(self, output: ModelRunnerOutput) -> ModelRunnerOutput:
        return output


def _check_output(output: ModelRunnerOutput, case_id: int) -> dict[str, object]:
    if case_id == 50:
        assert output.logprobs is None
        assert output.sampled_token_ids == [[case_id]]
        return {"case": case_id, "logprobs": False}

    rows, cols = {
        10: (1, 2),
        20: (3, 5),
        30: (64, 32),
        40: (2, 1),
        60: (7, 11),
        70: (4, 17),
    }[case_id]
    assert output.logprobs is not None
    token_ids, logprobs, ranks, cu_tokens = output.logprobs
    token_ids_array = np.asarray(token_ids)
    logprobs_array = np.asarray(logprobs)
    ranks_array = np.asarray(ranks)
    expected_ids = (
        np.arange(rows * cols, dtype=np.int32).reshape(rows, cols) + case_id
    )
    expected_logprobs = np.linspace(
        -case_id / 10,
        -0.001,
        rows * cols,
        dtype=np.float32,
    ).reshape(rows, cols)
    np.testing.assert_array_equal(token_ids_array, expected_ids)
    np.testing.assert_allclose(
        logprobs_array,
        expected_logprobs,
        rtol=1e-6,
        atol=1e-7,
    )
    np.testing.assert_array_equal(
        ranks_array,
        np.arange(rows, dtype=np.int16) + case_id,
    )
    expected_sampled_token_ids = [
        [int(token_id)] for token_id in expected_ids[:, 0]
    ]
    assert output.sampled_token_ids == expected_sampled_token_ids
    assert cu_tokens == list(range(rows + 1))
    return {
        "case": case_id,
        "logprobs": True,
        "shape": list(token_ids_array.shape),
        "sampled_token_count": len(expected_sampled_token_ids),
        "representation": type(token_ids).__name__,
    }


def test_required_ray_executor_channel() -> None:
    ray.init(address="127.0.0.1:6379", log_to_driver=False)
    nodes = sorted(
        (node for node in ray.nodes() if node["Alive"]),
        key=lambda node: node["NodeManagerAddress"],
    )
    assert len(nodes) == 2
    assert len({node["NodeID"] for node in nodes}) == 2
    assert len({node["NodeManagerAddress"] for node in nodes}) == 2

    def actor_on(node):
        return _Stage.options(
            scheduling_strategy=NodeAffinitySchedulingStrategy(
                node_id=node["NodeID"], soft=False
            )
        ).remote()

    producer = actor_on(nodes[0])
    consumer = actor_on(nodes[1])
    actor_node_ids = ray.get([producer.node_id.remote(), consumer.node_id.remote()])
    assert actor_node_ids == [nodes[0]["NodeID"], nodes[1]["NodeID"]]
    with InputNode() as dag_input:
        dag = consumer.forward.bind(producer.make_output.bind(dag_input))
    compiled = dag.experimental_compile(
        _max_inflight_executions=1,
        _max_buffered_results=1,
    )

    class _CompiledDagAdapter:
        def execute(self, args):
            case_id, _grammar_output = args
            return [compiled.execute(case_id)]

        def teardown(self):
            compiled.teardown()

    executor = object.__new__(RayDistributedExecutor)
    executor.forward_dag = _CompiledDagAdapter()
    executor.has_connector = False
    executor.workers = []

    held_outputs = []
    observations = []
    cases = [10, 20, 30, 40, 50, 60, 70]
    for case_id in cases:
        output = executor._execute_dag(
            case_id,
            None,
            non_block=True,
        ).result(timeout=5)
        observations.append(_check_output(output, case_id))
        held_outputs.append(output)
    print(
        {
            "result_boundary": (
                "RayWorkerWrapper.execute_model_ray -> "
                "RayDistributedExecutor._execute_dag"
            ),
            "results_held_concurrently": len(held_outputs),
            "cases": observations,
            "ray_nodes": [node["NodeManagerAddress"] for node in nodes],
            "actor_node_ids": actor_node_ids,
            "channel_buffer_slots": 1,
        },
        flush=True,
    )
    executor.forward_dag = None


def main() -> int:
    import pytest

    return pytest.main([
        "--noconftest", "-c", "/dev/null", "--rootdir=/workspace/vllm",
        "-p", "no:cacheprovider", "-v", "-s",
        "--junitxml=/logs/verifier/ray-channel-junit.xml", __file__,
    ])


if __name__ == "__main__":
    exit_code = main()
    os._exit(exit_code)
