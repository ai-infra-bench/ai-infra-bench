from types import SimpleNamespace

import numpy as np
import pytest
from vllm.v1.executor import ray_executor, ray_utils
from vllm.v1.outputs import LogprobsLists, LogprobsTensors, ModelRunnerOutput


def _output(readonly=(True, True, True)) -> ModelRunnerOutput:
    token_ids = np.array([[1, 2], [3, 4]], dtype=np.int32)
    logprobs = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
    ranks = np.array([1, 2], dtype=np.int16)
    arrays = (token_ids, logprobs, ranks)
    for array, make_readonly in zip(arrays, readonly):
        if make_readonly:
            array.setflags(write=False)

    return ModelRunnerOutput(
        req_ids=["req-0"],
        req_id_to_index={"req-0": 0},
        logprobs=LogprobsLists(*arrays, [0, 2]),
        prompt_logprobs_dict={"req-0": LogprobsTensors.empty_cpu(1, 2)},
    )


def _assert_detached(
    output: ModelRunnerOutput,
    original: LogprobsLists,
    readonly=(True, True, True),
) -> None:
    detached = output.logprobs
    assert detached is not None
    for actual, before, was_readonly in zip(detached[:3], original[:3], readonly):
        if was_readonly:
            assert actual is not before
            assert actual.flags.writeable
        else:
            assert actual is before
        np.testing.assert_array_equal(actual, before)
    assert detached.cu_num_generated_tokens is original.cu_num_generated_tokens


class _Ref:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _Dag:
    def __init__(self, refs):
        self.refs = refs

    def execute(self, _inputs):
        return self.refs


class _FakeRay:
    @staticmethod
    def get(refs, timeout=None):
        del timeout
        if isinstance(refs, list):
            return [ref.value for ref in refs]
        return refs.value


class _Aggregator:
    def __init__(self, output_rank=0):
        self.output_rank = output_rank
        self.outputs = None

    def aggregate(self, outputs, output_rank=0):
        self.outputs = outputs
        rank = self.output_rank if output_rank == 0 else output_rank
        return outputs[rank]


def test_blocking_executor_detaches_direct_result():
    output = _output()
    original = output.logprobs
    executor = SimpleNamespace(forward_dag=_Dag([_Ref(output)]), has_connector=False)

    result = ray_executor.RayDistributedExecutor._execute_dag(
        executor, object(), None, non_block=False
    )

    assert result is output
    assert original is not None
    _assert_detached(output, original)


def test_nonblocking_future_detaches_direct_result(monkeypatch):
    output = _output()
    original = output.logprobs
    monkeypatch.setattr(ray_utils, "ray", _FakeRay)

    result = ray_utils.FutureWrapper(_Ref(output)).result()

    assert result is output
    assert original is not None
    _assert_detached(output, original)


def test_blocking_connector_detaches_every_worker(monkeypatch):
    outputs = [_output(), _output()]
    originals = [output.logprobs for output in outputs]
    aggregator = _Aggregator(output_rank=1)
    executor = SimpleNamespace(
        forward_dag=_Dag([_Ref(output) for output in outputs]),
        has_connector=True,
        kv_output_aggregator=aggregator,
    )
    monkeypatch.setattr(ray_executor, "ray", _FakeRay)

    result = ray_executor.RayDistributedExecutor._execute_dag(
        executor, object(), None, non_block=False
    )

    assert result is outputs[1]
    assert aggregator.outputs is not None
    assert all(actual is expected for actual, expected in zip(aggregator.outputs, outputs))
    for output, original in zip(outputs, originals):
        assert original is not None
        _assert_detached(output, original)


def test_nonblocking_connector_detaches_every_worker(monkeypatch):
    outputs = [_output(), _output()]
    originals = [output.logprobs for output in outputs]
    aggregator = _Aggregator()
    monkeypatch.setattr(ray_utils, "ray", _FakeRay)

    result = ray_utils.FutureWrapper(
        [_Ref(output) for output in outputs], aggregator
    ).result()

    assert result is outputs[0]
    assert aggregator.outputs is not None
    assert all(actual is expected for actual, expected in zip(aggregator.outputs, outputs))
    for output, original in zip(outputs, originals):
        assert original is not None
        _assert_detached(output, original)


@pytest.mark.parametrize(
    "readonly",
    [
        (True, False, False),
        (False, True, False),
        (False, False, True),
        (False, False, False),
    ],
)
def test_only_readonly_numpy_arrays_are_detached(monkeypatch, readonly):
    output = _output(readonly=readonly)
    original = output.logprobs
    original_prompt = output.prompt_logprobs_dict["req-0"]
    monkeypatch.setattr(ray_utils, "ray", _FakeRay)

    result = ray_utils.FutureWrapper(_Ref(output)).result()

    assert result is output
    assert original is not None
    _assert_detached(output, original, readonly)
    assert output.prompt_logprobs_dict["req-0"] is original_prompt


def test_none_logprobs_remain_none_through_future(monkeypatch):
    output = _output()
    output.logprobs = None
    original_prompt = output.prompt_logprobs_dict["req-0"]
    monkeypatch.setattr(ray_utils, "ray", _FakeRay)

    result = ray_utils.FutureWrapper(_Ref(output)).result()

    assert result is output
    assert result.logprobs is None
    assert result.prompt_logprobs_dict["req-0"] is original_prompt


def test_none_logprobs_remain_none_through_blocking_executor():
    output = _output()
    output.logprobs = None
    executor = SimpleNamespace(forward_dag=_Dag([_Ref(output)]), has_connector=False)

    result = ray_executor.RayDistributedExecutor._execute_dag(
        executor, object(), None, non_block=False
    )

    assert result is output
    assert result.logprobs is None
