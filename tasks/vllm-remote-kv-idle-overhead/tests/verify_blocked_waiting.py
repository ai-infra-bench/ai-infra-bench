#!/usr/bin/env python3
"""Behavioral and deterministic-work contract for remote-KV waiting."""

from __future__ import annotations

import copy
from concurrent.futures import Future
import json
import statistics
import sys
import tempfile
import time
import types
from pathlib import Path

import torch

REQUEST_COUNT = 24
IDLE_ROUNDS = 200
EXPECTED_CHECKPOINTS = (
    "idle-scaling",
    "mixed-idle-scaling",
    "completion-promotion",
    "abort",
    "abort-late-completion",
    "abort-ready-race",
    "staggered-completion",
    "mixed-fcfs",
    "streaming-resumption",
    "generation-lifecycle",
    "ready-backpressure",
    "no-connector-regression",
    "complete",
)
MODEL_CONFIG = {
    "_name_or_path": "facebook/opt-125m",
    "architectures": ["OPTForCausalLM"],
    "bos_token_id": 2,
    "eos_token_id": 2,
    "hidden_size": 768,
    "max_position_embeddings": 2048,
    "model_type": "opt",
    "num_attention_heads": 12,
    "num_hidden_layers": 12,
    "pad_token_id": 1,
    "vocab_size": 50272,
}


_CONNECTOR_MODULE = "_ai_infra_remote_kv_verifier"
_HASH_INITIALIZED = False
_CANDIDATE_LOADED = False


def load_candidate() -> None:
    """Import candidate code only after the trusted parent has forked."""
    global _CANDIDATE_LOADED
    if _CANDIDATE_LOADED:
        return
    sys.path.insert(0, "/app")

    from vllm.config import (
        CacheConfig,
        KVTransferConfig,
        ModelConfig,
        ParallelConfig,
        SchedulerConfig,
        VllmConfig,
    )
    from vllm.distributed.kv_transfer.kv_connector.v1 import (
        KVConnectorBase_V1,
        KVConnectorRole,
    )
    from vllm.sampling_params import SamplingParams, StructuredOutputsParams
    from vllm.utils.hashing import sha256
    from vllm.v1.core.kv_cache_utils import (
        get_request_block_hasher,
        init_none_hash,
    )
    from vllm.v1.core.sched.scheduler import Scheduler
    from vllm.v1.kv_cache_interface import (
        FullAttentionSpec,
        KVCacheConfig,
        KVCacheGroupSpec,
    )
    from vllm.v1.outputs import (
        EMPTY_MODEL_RUNNER_OUTPUT,
        KVConnectorOutput,
        ModelRunnerOutput,
    )
    from vllm.v1.request import Request, RequestStatus
    from vllm.v1.structured_output import StructuredOutputManager

    globals().update(
        {
            name: value
            for name, value in locals().items()
            if name not in {"name", "value"}
        }
    )

    class VerifierKVConnector(KVConnectorBase_V1):
        """Minimal asynchronous receive connector owned by the verifier."""

        def __init__(self, vllm_config, role, kv_cache_config=None) -> None:
            super().__init__(vllm_config, role, kv_cache_config)

        def get_num_new_matched_tokens(self, request, num_computed_tokens):
            return 8, True

        def update_state_after_alloc(self, request, blocks, num_external_tokens):
            return None

        def build_connector_meta(self, scheduler_output):
            return None

        def start_load_kv(self, forward_context, **kwargs):
            return None

        def wait_for_layer_load(self, layer_name):
            return None

        def save_kv_layer(self, layer_name, kv_layer, attn_metadata, **kwargs):
            return None

        def wait_for_save(self):
            return None

    module = types.ModuleType(_CONNECTOR_MODULE)
    module.VerifierKVConnector = VerifierKVConnector
    sys.modules[_CONNECTOR_MODULE] = module
    _CANDIDATE_LOADED = True


def create_requests(
    request_count: int,
    *,
    token_counts: list[int] | None = None,
    request_ids: list[str] | None = None,
    max_tokens: int = 16,
) -> list[Request]:
    global _HASH_INITIALIZED
    if not _HASH_INITIALIZED:
        init_none_hash(sha256)
        _HASH_INITIALIZED = True
    block_hasher = get_request_block_hasher(16, sha256)
    sampling_params = SamplingParams(max_tokens=max_tokens, ignore_eos=True)
    sampling_params.update_from_generation_config({}, 50256)
    if token_counts is None:
        token_counts = [10] * request_count
    if request_ids is None:
        request_ids = [str(index) for index in range(request_count)]
    assert len(token_counts) == request_count
    assert len(request_ids) == request_count
    return [
        Request(
            request_id=request_ids[index],
            prompt_token_ids=[index] * token_counts[index],
            sampling_params=sampling_params,
            pooling_params=None,
            block_hasher=block_hasher,
        )
        for index in range(request_count)
    ]


def create_scheduler(
    model_dir: str,
    request_count: int,
    *,
    max_num_batched_tokens: int | None = None,
    use_connector: bool = True,
) -> Scheduler:
    model_config = ModelConfig(
        model=model_dir,
        trust_remote_code=False,
        dtype="float16",
        seed=42,
        skip_tokenizer_init=True,
    )
    scheduler_config = SchedulerConfig(
        max_num_seqs=request_count,
        max_num_batched_tokens=(
            max_num_batched_tokens
            if max_num_batched_tokens is not None
            else max(8192, request_count * 16)
        ),
        max_model_len=2048,
        enable_chunked_prefill=True,
        is_encoder_decoder=model_config.is_encoder_decoder,
    )
    cache_config = CacheConfig(
        block_size=16,
        gpu_memory_utilization=0.9,
        cache_dtype="auto",
        enable_prefix_caching=False,
    )
    cache_config.num_gpu_blocks = 10000
    transfer_config = KVTransferConfig(
        kv_connector="VerifierKVConnector",
        kv_connector_module_path=_CONNECTOR_MODULE,
        kv_role="kv_both",
    )
    vllm_config = VllmConfig(
        scheduler_config=scheduler_config,
        model_config=model_config,
        cache_config=cache_config,
        parallel_config=ParallelConfig(),
        kv_transfer_config=transfer_config if use_connector else None,
    )
    kv_cache_config = KVCacheConfig(
        num_blocks=10000,
        kv_cache_tensors=[],
        kv_cache_groups=[
            KVCacheGroupSpec(
                ["layer"],
                FullAttentionSpec(
                    block_size=16,
                    num_kv_heads=1,
                    head_size=1,
                    dtype=torch.float32,
                ),
            )
        ],
    )
    return Scheduler(
        vllm_config=vllm_config,
        kv_cache_config=kv_cache_config,
        block_size=16,
        log_stats=False,
        structured_output_manager=StructuredOutputManager(vllm_config),
    )


def create_blocked_scheduler(model_dir: str, request_count: int):
    scheduler = create_scheduler(model_dir, request_count)
    requests = create_requests(request_count)
    for request in requests:
        scheduler.add_request(request)
    output = scheduler.schedule()
    assert not output.scheduled_new_reqs
    assert all(r.status == RequestStatus.WAITING_FOR_REMOTE_KVS for r in requests)
    assert scheduler.get_request_counts() == (0, request_count)
    return scheduler, requests, output


def measure_idle(model_dir: str, request_count: int) -> float:
    scheduler, _, _ = create_blocked_scheduler(model_dir, request_count)
    scheduler.schedule()
    samples = []
    for _ in range(5):
        started = time.perf_counter_ns()
        for _ in range(IDLE_ROUNDS):
            output = scheduler.schedule()
            assert not output.scheduled_new_reqs
        samples.append(time.perf_counter_ns() - started)
    assert scheduler.get_request_counts() == (0, request_count)
    return statistics.median(samples) / IDLE_ROUNDS


def start_stream_and_wait(scheduler, request_id="stream"):
    """Enter streaming wait by ending a real resumable output segment."""
    request = create_requests(
        1, request_ids=[request_id], token_counts=[1], max_tokens=1,
    )[0]
    request.resumable = True
    scheduler.add_request(request)
    scheduled = scheduler.schedule()
    if list(scheduled.num_scheduled_tokens) != [request_id]:
        raise AssertionError("runnable streaming segment stalled behind blocked work")
    outputs = scheduler.update_from_output(scheduled, ModelRunnerOutput(
        req_ids=[request_id], req_id_to_index={request_id: 0}, sampled_token_ids=[[42]],
    ))
    observed = [token for client in outputs.values() for output in client.outputs
                if output.request_id == request_id for token in output.new_token_ids]
    if observed != [42] or request.status != RequestStatus.WAITING_FOR_STREAMING_REQ:
        raise AssertionError("streaming segment failed to return output and await next input")
    return request


def deliver_stream_input(scheduler, request_id="stream"):
    update = create_requests(
        1, request_ids=[request_id], token_counts=[1], max_tokens=1,
    )[0]
    update.resumable = True
    scheduler.add_request(update)


def create_mixed_idle_scheduler(model_dir, request_count):
    scheduler, requests, _ = create_blocked_scheduler(model_dir, request_count)
    scheduler.connector.get_num_new_matched_tokens = lambda request, count: (
        (0, False) if request.request_id == "stream" else (8, True)
    )
    stream = start_stream_and_wait(scheduler)
    if scheduler.get_request_counts() != (0, request_count + 1):
        raise AssertionError("mixed waits lost request accounting")
    return scheduler, requests, stream


def measure_mixed_idle(model_dir, request_count):
    scheduler, _, _ = create_mixed_idle_scheduler(model_dir, request_count)
    scheduler.schedule()
    samples = []
    for _ in range(5):
        started = time.perf_counter_ns()
        for _ in range(IDLE_ROUNDS):
            if scheduler.schedule().num_scheduled_tokens:
                raise AssertionError("request ran before its pending input/transfer arrived")
        samples.append(time.perf_counter_ns() - started)
    if scheduler.get_request_counts() != (0, request_count + 1):
        raise AssertionError("idle ticks lost mixed waiting requests")
    return statistics.median(samples) / IDLE_ROUNDS


def check_streaming_resumption(model_dir):
    for request_count in (3, 37):
        scheduler, requests, stream = create_mixed_idle_scheduler(model_dir, request_count)
        for _ in range(3):
            if scheduler.schedule().num_scheduled_tokens:
                raise AssertionError("pending mixed requests unexpectedly ran")
        # A new streaming input is independent of every remote transfer. No
        # remote completion may be needed for it to become runnable again.
        for token in (43, 44):
            deliver_stream_input(scheduler)
            scheduled = scheduler.schedule()
            if list(scheduled.num_scheduled_tokens) != ["stream"]:
                raise AssertionError("streaming continuation stalled without a remote completion")
            outputs = scheduler.update_from_output(scheduled, ModelRunnerOutput(
                req_ids=["stream"], req_id_to_index={"stream": 0}, sampled_token_ids=[[token]],
            ))
            actual = [t for client in outputs.values() for output in client.outputs
                      if output.request_id == "stream" for t in output.new_token_ids]
            if actual != [token] or stream.status != RequestStatus.WAITING_FOR_STREAMING_REQ:
                raise AssertionError("resumed streaming output/lifecycle was corrupted")
        scheduler.finish_requests("stream", RequestStatus.FINISHED_ABORTED)
        if scheduler.get_request_counts() != (0, request_count):
            raise AssertionError("cancelling a streaming wait corrupted remote counts")


def check_mixed_blocked_fcfs(model_dir: str) -> None:
    """Real remote and streaming events preserve order with pending grammar."""
    scheduler = create_scheduler(model_dir, 5, max_num_batched_tokens=20)
    scheduler.connector.get_num_new_matched_tokens = lambda request, count: (
        (8, True) if request.request_id == "remote" else (0, False)
    )
    remote = create_requests(1, request_ids=["remote"], token_counts=[10])[0]
    params = SamplingParams(max_tokens=16, ignore_eos=True,
                            structured_outputs=StructuredOutputsParams(choice=["yes", "no"]))
    params.update_from_generation_config({}, 50256)
    fsm = Request(request_id="fsm", prompt_token_ids=[1], sampling_params=params,
                  pooling_params=None, block_hasher=get_request_block_hasher(16, sha256))
    # Grammar compilation is outside the scheduler boundary; a real Future
    # supplies the same completion event as the upstream grammar worker.
    grammar = Future()
    fsm.structured_output_request.grammar = grammar
    scheduler.add_request(fsm)
    scheduler.add_request(remote)
    start_stream_and_wait(scheduler)
    if remote.status != RequestStatus.WAITING_FOR_REMOTE_KVS:
        raise AssertionError("remote request did not enter asynchronous receive")
    regular, tail = create_requests(2, request_ids=["regular", "tail"], token_counts=[20, 1])
    scheduler.add_request(regular)
    scheduler.add_request(tail)
    first = scheduler.schedule()
    if list(first.num_scheduled_tokens) != ["regular"]:
        raise AssertionError("ordinary runnable request stalled behind mixed waits")
    scheduler.update_from_output(first, ModelRunnerOutput(
        req_ids=["regular"], req_id_to_index={"regular": 0}, sampled_token_ids=[[]],
        kv_connector_output=KVConnectorOutput(finished_recving={"remote"}),
    ))
    scheduler.finish_requests("regular", RequestStatus.FINISHED_ABORTED)
    grammar.set_result(object())
    deliver_stream_input(scheduler)
    second = scheduler.schedule()
    observed = list(second.num_scheduled_tokens)
    if observed != ["fsm", "remote", "stream", "tail"]:
        raise AssertionError(f"FCFS order changed across mixed waits: {observed}")


def check_abort_late_completion(model_dir: str) -> None:
    """A connector completion racing with cancellation must not revive it."""
    scheduler, requests, output = create_blocked_scheduler(model_dir, 4)
    victim = requests[1]
    survivor = requests[2]
    scheduler.finish_requests(victim.request_id, RequestStatus.FINISHED_ABORTED)

    finished = copy.deepcopy(EMPTY_MODEL_RUNNER_OUTPUT)
    finished.kv_connector_output = KVConnectorOutput(
        finished_recving={victim.request_id, survivor.request_id}
    )
    scheduler.update_from_output(output, finished)
    resumed = scheduler.schedule()
    resumed_ids = [request.req_id for request in resumed.scheduled_new_reqs]
    if resumed_ids != [survivor.request_id]:
        raise AssertionError(
            "late remote completion revived an aborted request or changed order: "
            f"{resumed_ids}"
        )
    if victim.status != RequestStatus.FINISHED_ABORTED:
        raise AssertionError(f"aborted request changed state: {victim.status}")
    running, waiting = scheduler.get_request_counts()
    if (running, waiting) != (1, 2):
        raise AssertionError(
            f"late completion corrupted request accounting: {(running, waiting)}"
        )


def check_abort_after_ready_event(model_dir: str) -> None:
    """Cancellation between connector completion and scheduling must win."""
    scheduler, requests, initial = create_blocked_scheduler(model_dir, 5)
    victim, survivor = requests[1], requests[3]
    event = copy.deepcopy(EMPTY_MODEL_RUNNER_OUTPUT)
    event.kv_connector_output = KVConnectorOutput(
        finished_recving={victim.request_id, survivor.request_id}
    )
    scheduler.update_from_output(initial, event)
    scheduler.finish_requests(victim.request_id, RequestStatus.FINISHED_ABORTED)

    resumed = scheduler.schedule()
    resumed_ids = [request.req_id for request in resumed.scheduled_new_reqs]
    if resumed_ids != [survivor.request_id]:
        raise AssertionError(
            "cancellation after remote completion revived the victim or "
            f"blocked its peer: {resumed_ids}"
        )
    if victim.status != RequestStatus.FINISHED_ABORTED:
        raise AssertionError(f"cancelled request changed state: {victim.status}")
    if scheduler.get_request_counts() != (1, 3):
        raise AssertionError(
            "completion/cancellation race corrupted request accounting: "
            f"{scheduler.get_request_counts()}"
        )

    # A later connector event must still promote older blocked requests in
    # arrival order, even when an earlier completion was cancelled.
    scheduler.finish_requests(survivor.request_id, RequestStatus.FINISHED_ABORTED)
    later = copy.deepcopy(EMPTY_MODEL_RUNNER_OUTPUT)
    later.kv_connector_output = KVConnectorOutput(
        finished_recving={requests[4].request_id, requests[0].request_id}
    )
    scheduler.update_from_output(resumed, later)
    promoted = scheduler.schedule()
    promoted_ids = [request.req_id for request in promoted.scheduled_new_reqs]
    expected = [requests[0].request_id, requests[4].request_id]
    if promoted_ids != expected:
        raise AssertionError(
            "later remote completion changed FCFS order after cancellation: "
            f"expected={expected} actual={promoted_ids}"
        )


def check_staggered_completion_and_arrival(model_dir: str) -> None:
    """Separate completion batches and a fresh arrival retain FCFS behavior."""
    scheduler, requests, initial = create_blocked_scheduler(model_dir, 4)

    first_ready = {requests[1].request_id, requests[3].request_id}
    first_event = copy.deepcopy(EMPTY_MODEL_RUNNER_OUTPUT)
    first_event.kv_connector_output = KVConnectorOutput(
        finished_recving=first_ready
    )
    scheduler.update_from_output(initial, first_event)
    first = scheduler.schedule()
    first_ids = [request.req_id for request in first.scheduled_new_reqs]
    if first_ids != [requests[1].request_id, requests[3].request_id]:
        raise AssertionError(f"first completion batch changed FCFS order: {first_ids}")

    # Complete the running work while a second connector event promotes the
    # older remote waiters.  A newly admitted ordinary request must follow them.
    completed = ModelRunnerOutput(
        req_ids=first_ids,
        req_id_to_index={request_id: i for i, request_id in enumerate(first_ids)},
        sampled_token_ids=[[] for _ in first_ids],
        kv_connector_output=KVConnectorOutput(
            finished_recving={requests[0].request_id, requests[2].request_id}
        ),
    )
    scheduler.update_from_output(first, completed)
    scheduler.finish_requests(first_ids, RequestStatus.FINISHED_ABORTED)

    scheduler.connector.get_num_new_matched_tokens = lambda request, count: (0, False)
    newcomer = create_requests(1, request_ids=["new-arrival"])[0]
    scheduler.add_request(newcomer)
    second = scheduler.schedule()
    second_ids = [request.req_id for request in second.scheduled_new_reqs]
    expected = [
        requests[0].request_id,
        requests[2].request_id,
        newcomer.request_id,
    ]
    if second_ids != expected:
        raise AssertionError(
            "staggered completion/new arrival changed FCFS order: "
            f"expected={expected} actual={second_ids}"
        )


class GenerationDriver:
    """Deterministic model results with real scheduler output/finish handling."""

    def __init__(self, scheduler, requests):
        self.scheduler = scheduler
        self.requests = {r.request_id: r for r in requests}
        self.expected = {
            r.request_id: [100 + index * 10 + n for n in range(3)]
            for index, r in enumerate(requests)
        }
        self.issued = {r.request_id: 0 for r in requests}
        self.observed = {r.request_id: [] for r in requests}
        self.finished = []
        self.admitted = []

    def tick(self, ready=()):
        scheduled = self.scheduler.schedule()
        self.admitted.extend(r.req_id for r in scheduled.scheduled_new_reqs)
        req_ids = list(scheduled.num_scheduled_tokens)
        sampled = []
        for req_id in req_ids:
            request = self.requests[req_id]
            if request.num_computed_tokens < request.num_prompt_tokens:
                sampled.append([])
                continue
            index = self.issued[req_id]
            if index >= 3:
                raise AssertionError(f"request scheduled after generation ended: {req_id}")
            sampled.append([self.expected[req_id][index]])
            self.issued[req_id] += 1
        outputs = self.scheduler.update_from_output(scheduled, ModelRunnerOutput(
            req_ids=req_ids,
            req_id_to_index={req_id: i for i, req_id in enumerate(req_ids)},
            sampled_token_ids=sampled,
            kv_connector_output=(
                KVConnectorOutput(finished_recving=set(ready)) if ready else None
            ),
        ))
        for client_output in outputs.values():
            for output in client_output.outputs:
                self.observed[output.request_id].extend(output.new_token_ids)
                if output.finish_reason is not None:
                    if output.request_id in self.finished:
                        raise AssertionError(f"duplicate terminal output: {output.request_id}")
                    self.finished.append(output.request_id)
        return scheduled

    def drain(self):
        for _ in range(40):
            if self.scheduler.get_request_counts() == (0, 0):
                break
            self.tick()
        if self.scheduler.get_request_counts() != (0, 0):
            raise AssertionError("finite ready workload failed to finish")
        if self.observed != self.expected:
            raise AssertionError(
                f"generated token streams lost or misrouted: "
                f"expected={self.expected} actual={self.observed}"
            )
        if set(self.finished) != set(self.expected):
            raise AssertionError(f"missing terminal outputs: {self.finished}")
        # Empty ticks after completion must not resurrect or duplicate work.
        if self.tick().num_scheduled_tokens:
            raise AssertionError("completed requests were scheduled again")


def check_generation_lifecycle(model_dir):
    """Local work progresses during remote waits; all streams then finish."""
    scheduler = create_scheduler(model_dir, 3, max_num_batched_tokens=12)
    remote_ids = {"remote-a", "remote-b"}
    scheduler.connector.get_num_new_matched_tokens = lambda request, count: (
        (16, True) if request.request_id in remote_ids else (0, False)
    )
    requests = create_requests(
        3, request_ids=["remote-a", "remote-b", "local-c"],
        token_counts=[21, 19, 25], max_tokens=3,
    )
    driver = GenerationDriver(scheduler, requests)
    for request in requests:
        scheduler.add_request(request)
    for _ in range(4):
        driver.tick()
    if not driver.observed["local-c"]:
        raise AssertionError("local request stalled behind pending remote transfers")
    if driver.observed["remote-a"] or driver.observed["remote-b"]:
        raise AssertionError("remote request ran before transfer completion")
    driver.tick(ready={"remote-b"})
    driver.tick()
    if not driver.observed["remote-b"] or driver.observed["remote-a"]:
        raise AssertionError("out-of-order readiness did not wake the correct request")
    driver.tick(ready={"remote-a"})
    driver.drain()


def check_ready_backpressure(model_dir, *, use_connector=True):
    """Ready requests survive a full running batch and admit a later arrival."""
    scheduler = create_scheduler(
        model_dir, 1, max_num_batched_tokens=32, use_connector=use_connector,
    )
    requests = create_requests(
        4, request_ids=["first", "second", "third", "later"],
        token_counts=[20, 23, 18, 7], max_tokens=3,
    )
    if use_connector:
        remote_ids = {r.request_id for r in requests[:3]}
        scheduler.connector.get_num_new_matched_tokens = lambda request, count: (
            (16, True) if request.request_id in remote_ids else (0, False)
        )
    driver = GenerationDriver(scheduler, requests)
    for request in requests[:3]:
        scheduler.add_request(request)
    driver.tick()
    if use_connector:
        if scheduler.get_request_counts() != (0, 3):
            raise AssertionError("pending transfers changed request accounting")
        driver.tick(ready={r.request_id for r in requests[:3]})
    driver.tick()
    scheduler.add_request(requests[3])
    driver.drain()
    expected_order = [r.request_id for r in requests]
    if driver.admitted != expected_order or driver.finished != expected_order:
        raise AssertionError(
            f"FCFS changed under capacity pressure: "
            f"admitted={driver.admitted} finished={driver.finished}"
        )


def run_suite(emit) -> None:
    load_candidate()
    with tempfile.TemporaryDirectory(prefix="remote-kv-model-") as tmp:
        model_dir = Path(tmp)
        (model_dir / "config.json").write_text(json.dumps(MODEL_CONFIG))

        small_ns = measure_idle(str(model_dir), REQUEST_COUNT)
        large_count = REQUEST_COUNT * 16
        large_ns = measure_idle(str(model_dir), large_count)
        ratio = large_ns / max(small_ns, 1.0)
        if ratio >= 6.0:
            raise AssertionError(
                "idle remote-KV tick still scales with blocked population: "
                f"small={small_ns:.0f}ns large={large_ns:.0f}ns ratio={ratio:.2f}"
            )
        emit("idle-scaling", True)

        mixed_small_ns = measure_mixed_idle(str(model_dir), REQUEST_COUNT)
        mixed_large_ns = measure_mixed_idle(str(model_dir), REQUEST_COUNT * 16)
        mixed_ratio = mixed_large_ns / max(mixed_small_ns, 1.0)
        if mixed_ratio >= 6.0:
            raise AssertionError(f"mixed idle remote-KV overhead still scales: ratio={mixed_ratio:.2f}")
        emit("mixed-idle-scaling", True)

        scheduler, requests, output = create_blocked_scheduler(
            str(model_dir), REQUEST_COUNT
        )
        ready_ids = {requests[i].request_id for i in (2, 7, 13)}
        finished = copy.deepcopy(EMPTY_MODEL_RUNNER_OUTPUT)
        finished.kv_connector_output = KVConnectorOutput(finished_recving=ready_ids)
        scheduler.update_from_output(output, finished)
        resumed = scheduler.schedule()
        resumed_ids = [request.req_id for request in resumed.scheduled_new_reqs]
        expected_ids = [r.request_id for r in requests if r.request_id in ready_ids]
        if resumed_ids != expected_ids:
            raise AssertionError(f"completion promotion/order changed: {resumed_ids}")
        running, waiting = scheduler.get_request_counts()
        assert running == len(ready_ids)
        assert waiting == REQUEST_COUNT - len(ready_ids)
        emit("completion-promotion", True)

        victim = requests[-1]
        scheduler.finish_requests(victim.request_id, RequestStatus.FINISHED_ABORTED)
        assert victim.status == RequestStatus.FINISHED_ABORTED
        emit("abort", True)

        check_abort_late_completion(str(model_dir))
        emit("abort-late-completion", True)

        check_abort_after_ready_event(str(model_dir))
        emit("abort-ready-race", True)

        check_staggered_completion_and_arrival(str(model_dir))
        emit("staggered-completion", True)

        check_mixed_blocked_fcfs(str(model_dir))
        emit("mixed-fcfs", True)

        check_streaming_resumption(str(model_dir))
        emit("streaming-resumption", True)

        check_generation_lifecycle(str(model_dir))
        emit("generation-lifecycle", True)
        check_ready_backpressure(str(model_dir))
        emit("ready-backpressure", True)
        check_ready_backpressure(str(model_dir), use_connector=False)
        emit("no-connector-regression", True)

        print(
            json.dumps(
                {
                "small_requests": REQUEST_COUNT,
                "large_requests": large_count,
                "idle_rounds": IDLE_ROUNDS,
                "small_tick_ns": small_ns,
                "large_tick_ns": large_ns,
                "scaling_ratio": ratio,
                "mixed_scaling_ratio": mixed_ratio,
                "resumed": resumed_ids,
            },
                sort_keys=True,
            )
        )
        print("PASS: remote-KV waiting idle overhead is bounded")
        emit("complete", True)


if __name__ == "__main__":
    run_suite(lambda name, value: print(f"checkpoint={name} value={value}"))
