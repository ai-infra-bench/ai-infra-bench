#!/usr/bin/env python3
"""Exercise vLLM result boundaries over a real Ray compiled-DAG channel."""

from __future__ import annotations

import os
from types import SimpleNamespace

import numpy as np
import ray
from ray.dag import InputNode
from ray.util.scheduling_strategies import NodeAffinitySchedulingStrategy

from vllm.v1.executor import ray_executor, ray_utils
from vllm.v1.outputs import LogprobsLists, ModelRunnerOutput


@ray.remote(num_cpus=1)
class _Stage:
    def node_id(self) -> str:
        return ray.get_runtime_context().get_node_id()

    def make_output(self, value: int) -> ModelRunnerOutput:
        token_ids = np.array([[value, value + 1]], dtype=np.int32)
        logprobs = np.array([[value / 10, value / 20]], dtype=np.float32)
        ranks = np.array([value], dtype=np.int16)
        return ModelRunnerOutput(
            req_ids=[f"req-{value}"],
            req_id_to_index={f"req-{value}": 0},
            logprobs=LogprobsLists(token_ids, logprobs, ranks, [0, 1]),
        )

    def forward(self, output: ModelRunnerOutput) -> ModelRunnerOutput:
        return output


def _check_output(output: ModelRunnerOutput, value: int) -> bool:
    assert output.logprobs is not None
    token_ids, logprobs, ranks, cu_tokens = output.logprobs
    np.testing.assert_array_equal(token_ids, [[value, value + 1]])
    np.testing.assert_allclose(logprobs, [[value / 10, value / 20]])
    np.testing.assert_array_equal(ranks, [value])
    assert cu_tokens == [0, 1]
    return all(array.flags.writeable for array in (token_ids, logprobs, ranks))


def main() -> int:
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
                node_id=node["NodeID"],
                soft=False,
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

    held_outputs = []
    detached_results = []
    try:
        first = ray_utils.FutureWrapper(compiled.execute(10)).result(timeout=5)
        detached_results.append(_check_output(first, 10))
        held_outputs.append(first)

        class _DagAdapter:
            def execute(self, args):
                return [compiled.execute(args[0])]

        executor = SimpleNamespace(forward_dag=_DagAdapter(), has_connector=False)
        for value in (20, 30):
            output = ray_executor.RayDistributedExecutor._execute_dag(
                executor,
                value,
                None,
                non_block=False,
            )
            detached_results.append(_check_output(output, value))
            held_outputs.append(output)
        assert detached_results == [True, True, True]
        print(
            {
                "results": len(held_outputs),
                "all_logprob_arrays_detached": all(detached_results),
                "values": [10, 20, 30],
                "ray_nodes": [node["NodeManagerAddress"] for node in nodes],
                "actor_node_ids": actor_node_ids,
            },
            flush=True,
        )
        return 0
    except Exception as exc:
        lines = str(exc).splitlines()
        print(
            {
                "error": type(exc).__name__,
                "message": lines[0] if lines else "no exception message",
            },
            flush=True,
        )
        return 1


if __name__ == "__main__":
    exit_code = main()
    os._exit(exit_code)
