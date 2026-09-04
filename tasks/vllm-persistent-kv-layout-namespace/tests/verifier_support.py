"""Verifier-owned persistent filesystem tier fixtures and legacy artifacts."""

from __future__ import annotations

import hashlib
import json
import mmap
import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import torch

from vllm.config import KVTransferConfig, ParallelConfig
from vllm.distributed.kv_transfer.kv_connector.v1.offloading.config import (
    build_offloading_config,
)
from vllm.platforms import current_platform
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
)
from vllm.v1.kv_offload.base import (
    LookupResult,
    OffloadingSpec,
    ReqContext,
    ScheduleEndContext,
    get_offload_block_hash,
    get_offload_group_idx,
    make_offload_key,
)
from vllm.v1.kv_offload.config import (
    OffloadingCacheConfig,
    OffloadingConfig,
    OffloadingGroupConfig,
    OffloadingModelConfig,
    OffloadingParallelConfig,
)
from vllm.v1.kv_offload.tiering.base import JobMetadata
from vllm.v1.kv_offload.tiering.fs.manager import FileSystemTierManager


BLOCK_ELEMENTS = 16 * mmap.PAGESIZE
CONTEXT = ReqContext(req_id="persistent-verifier")


@dataclass(frozen=True)
class LayoutCase:
    name: str
    model_name: str = "layout-compatible-model"
    dtype: str = "float32"
    tokens_per_hash: int = 16
    blocks_per_chunk: int = 1
    groups: tuple[tuple[int, tuple[str, ...]], ...] = (
        (16, ("layer0",)),
    )


DEFAULT_CASE = LayoutCase("default")
LAYOUT_CASES = [
    DEFAULT_CASE,
    LayoutCase("bf16-config", dtype="bfloat16"),
    LayoutCase("larger-files", tokens_per_hash=32, blocks_per_chunk=4),
    LayoutCase("two-layers", groups=((16, ("layer0", "layer1")),)),
]


@dataclass(frozen=True)
class RunnerCase:
    name: str
    model_name: str
    dtype: torch.dtype


PUBLIC_RUNNER_CASE = RunnerCase(
    name="public-opt",
    model_name="facebook/opt-125m",
    dtype=torch.float16,
)
HIDDEN_RUNNER_CASE = RunnerCase(
    name="hidden-model",
    model_name="org/namespace-hidden-model",
    dtype=torch.bfloat16,
)
RUNNER_CASES = (PUBLIC_RUNNER_CASE, HIDDEN_RUNNER_CASE)


class FixtureOffloadingSpec(OffloadingSpec):
    def get_manager(self):
        raise NotImplementedError

    def get_worker(self, kv_caches):
        raise NotImplementedError


def make_spec(
    case: LayoutCase,
    *,
    portable: bool,
    tp_size=1,
    pp_size=1,
    pcp_size=1,
    dcp_size=1,
    rank=0,
):
    world_size = tp_size * pp_size * pcp_size
    groups = tuple(
        OffloadingGroupConfig(tokens_per_block=tokens, layer_names=layers)
        for tokens, layers in case.groups
    )
    config = OffloadingConfig(
        groups=groups,
        worker_kv_bytes_per_block=0,
        enable_kv_cache_events=False,
        extra_config={},
        engine_id="persistent-layout-verifier",
        model=OffloadingModelConfig(name=case.model_name, dtype=case.dtype),
        cache=OffloadingCacheConfig(
            tokens_per_hash=case.tokens_per_hash,
            blocks_per_chunk=case.blocks_per_chunk,
        ),
        parallel=OffloadingParallelConfig(
            rank=rank,
            world_size=world_size,
            tp_size=tp_size,
            pp_size=pp_size,
            pcp_size=pcp_size,
            dcp_size=dcp_size,
            data_parallel_index=0,
            is_parallelism_agnostic=portable,
        ),
    )
    return FixtureOffloadingSpec(config)


def make_runner_spec(case: RunnerCase, runner: str) -> FixtureOffloadingSpec:
    """Build the normalized offloading spec through vLLM's real config path."""
    if runner not in {"v1", "v2"}:
        raise ValueError(f"unsupported runner: {runner}")

    vllm_config = MagicMock()
    vllm_config.cache_config.block_size = 16
    vllm_config.cache_config.enable_prefix_caching = True
    vllm_config.cache_config.prefix_match_unit = None
    vllm_config.cache_config.cache_dtype = case.dtype
    vllm_config.model_config.model = case.model_name
    with patch.object(current_platform, "device_count", return_value=1):
        vllm_config.parallel_config = ParallelConfig(
            tensor_parallel_size=1,
            pipeline_parallel_size=1,
            prefill_context_parallel_size=1,
            decode_context_parallel_size=1,
        )
    vllm_config.kv_events_config = None
    vllm_config.use_v2_model_runner = runner == "v2"
    vllm_config.kv_transfer_config = KVTransferConfig(
        kv_connector="OffloadingConnector",
        kv_role="kv_both",
        kv_connector_extra_config={"spec_name": "TieringOffloadingSpec"},
    )
    kv_cache_config = KVCacheConfig(
        num_blocks=0,
        kv_cache_tensors=[],
        kv_cache_groups=[
            KVCacheGroupSpec(
                ["layer0", "layer1"],
                FullAttentionSpec(
                    block_size=16,
                    num_kv_heads=12,
                    head_size=64,
                    dtype=case.dtype,
                ),
            )
        ],
    )
    return FixtureOffloadingSpec(
        build_offloading_config(vllm_config, kv_cache_config)
    )


def aligned_tensor(num_blocks: int):
    dtype = torch.float32
    item_size = torch.tensor([], dtype=dtype).element_size()
    num_bytes = num_blocks * BLOCK_ELEMENTS * item_size
    raw = torch.zeros(num_bytes + mmap.PAGESIZE, dtype=torch.uint8)
    shift = mmap.PAGESIZE - (raw.data_ptr() % mmap.PAGESIZE)
    return raw[shift : shift + num_bytes].view(dtype).view(num_blocks, BLOCK_ELEMENTS)


def tier(root: str, tensor: torch.Tensor, spec: OffloadingSpec):
    return FileSystemTierManager(
        offloading_spec=spec,
        primary_kv_view=memoryview(tensor.numpy()),
        tier_type="fs",
        root_dir=root,
        n_read_threads=2,
        n_write_threads=2,
    )


def key(number: int, group=0):
    return make_offload_key(number.to_bytes(8, "big"), group)


def job(job_id, keys, block_ids, *, load=False):
    return JobMetadata(
        job_id=job_id,
        keys=list(keys),
        block_ids=np.array(block_ids, dtype=np.int64),
        is_promotion=load,
        req_context=CONTEXT,
    )


def drain(manager):
    manager.drain_jobs()
    results = list(manager.get_finished_jobs())
    assert results and all(result.success for result in results)
    return results


def lookup(manager, keys, timeout=2.0):
    for item in keys:
        manager.lookup(item, CONTEXT)
    manager.on_schedule_end(
        ScheduleEndContext(new_req_ids=[], preempted_req_ids=())
    )
    deadline = time.monotonic() + timeout
    results = [LookupResult.RETRY] * len(keys)
    while time.monotonic() < deadline:
        # Each scheduler step marks the async lookup manager ready to drain
        # results produced after the previous step's flush.
        manager.on_schedule_end(
            ScheduleEndContext(new_req_ids=[], preempted_req_ids=())
        )
        results = [manager.lookup(item, CONTEXT) for item in keys]
        if all(result is not LookupResult.RETRY for result in results):
            return results
        time.sleep(0.01)
    return results


def write_blocks(manager, tensor, keys, values, *, job_id=1):
    for index, value in enumerate(values):
        tensor[index].fill_(value)
    manager.submit_store(job(job_id, keys, range(len(keys))))
    drain(manager)


def load_blocks(manager, tensor, keys, dest_ids, *, job_id=2):
    for block_id in dest_ids:
        tensor[block_id].zero_()
    manager.submit_load(job(job_id, keys, dest_ids, load=True))
    drain(manager)


def assert_blocks(tensor, block_ids, values):
    for block_id, value in zip(block_ids, values, strict=True):
        assert torch.all(tensor[block_id] == value)


def runner_keys(key_seed: int):
    return [key(key_seed + offset) for offset in range(3)]


def store_runner_cache(
    root: str,
    case: RunnerCase,
    runner: str,
    values,
    *,
    key_seed: int,
    job_id: int = 1,
):
    keys = runner_keys(key_seed)
    tensor = aligned_tensor(6)
    manager = tier(root, tensor, make_runner_spec(case, runner))
    try:
        write_blocks(manager, tensor, keys, values, job_id=job_id)
    finally:
        manager.shutdown()


def assert_runner_cache(
    root: str,
    case: RunnerCase,
    runner: str,
    expected_values,
    *,
    key_seed: int,
    job_id: int = 2,
):
    keys = runner_keys(key_seed)
    tensor = aligned_tensor(6)
    manager = tier(root, tensor, make_runner_spec(case, runner))
    try:
        expected_lookup = (
            [LookupResult.MISS] * len(keys)
            if expected_values is None
            else [LookupResult.HIT] * len(keys)
        )
        assert lookup(manager, keys) == expected_lookup
        if expected_values is not None:
            load_blocks(manager, tensor, keys, [3, 4, 5], job_id=job_id)
            assert_blocks(tensor, [3, 4, 5], expected_values)
    finally:
        manager.shutdown()


def runner_transition_lifecycle(
    root: str,
    case: RunnerCase,
    writer_runner: str,
    reader_runner: str,
):
    writer_values = [101, 102, 103]
    reader_values = [201, 202, 203]
    key_seed = 600
    store_runner_cache(
        root, case, writer_runner, writer_values, key_seed=key_seed
    )
    assert_runner_cache(
        root, case, reader_runner, None, key_seed=key_seed
    )
    store_runner_cache(
        root,
        case,
        reader_runner,
        reader_values,
        key_seed=key_seed,
        job_id=3,
    )
    assert_runner_cache(
        root,
        case,
        writer_runner,
        writer_values,
        key_seed=key_seed,
        job_id=4,
    )
    assert_runner_cache(
        root,
        case,
        reader_runner,
        reader_values,
        key_seed=key_seed,
        job_id=5,
    )


def same_runner_restart_lifecycle(
    root: str,
    case: RunnerCase,
    runner: str,
):
    values = [71, 72, 73]
    key_seed = 700
    store_runner_cache(root, case, runner, values, key_seed=key_seed)
    assert_runner_cache(
        root, case, runner, values, key_seed=key_seed, job_id=6
    )


def incompatible_layout_lifecycle(root: str, case: LayoutCase):
    keys = [key(11), key(12), key(13)]
    portable_tensor = aligned_tensor(6)
    portable = tier(root, portable_tensor, make_spec(case, portable=True))
    write_blocks(portable, portable_tensor, keys, [11, 12, 13])
    portable.shutdown()

    specific_tensor = aligned_tensor(6)
    specific = tier(root, specific_tensor, make_spec(case, portable=False))
    try:
        assert lookup(specific, keys) == [LookupResult.MISS] * len(keys)
        write_blocks(specific, specific_tensor, keys, [21, 22, 23], job_id=10)
    finally:
        specific.shutdown()

    reopened_tensor = aligned_tensor(6)
    reopened = tier(root, reopened_tensor, make_spec(case, portable=False))
    try:
        assert lookup(reopened, keys) == [LookupResult.HIT] * len(keys)
        load_blocks(reopened, reopened_tensor, keys, [3, 4, 5], job_id=11)
        assert_blocks(reopened_tensor, [3, 4, 5], [21, 22, 23])
    finally:
        reopened.shutdown()


def portable_cross_parallel_lifecycle(root: str, case: LayoutCase, parallel):
    keys = [key(21), key(22)]
    writer_tensor = aligned_tensor(4)
    writer = tier(root, writer_tensor, make_spec(case, portable=True))
    write_blocks(writer, writer_tensor, keys, [31, 32])
    writer.shutdown()

    reader_tensor = aligned_tensor(4)
    reader = tier(root, reader_tensor, make_spec(case, portable=True, **parallel))
    try:
        assert lookup(reader, keys) == [LookupResult.HIT, LookupResult.HIT]
        load_blocks(reader, reader_tensor, keys, [2, 3])
        assert_blocks(reader_tensor, [2, 3], [31, 32])
    finally:
        reader.shutdown()


def layout_specific_parallel_miss(root: str, case: LayoutCase, parallel):
    keys = [key(31), key(32)]
    writer_tensor = aligned_tensor(4)
    writer = tier(root, writer_tensor, make_spec(case, portable=False))
    write_blocks(writer, writer_tensor, keys, [41, 42])
    writer.shutdown()

    reader_tensor = aligned_tensor(4)
    reader = tier(root, reader_tensor, make_spec(case, portable=False, **parallel))
    try:
        assert lookup(reader, keys) == [LookupResult.MISS, LookupResult.MISS]
    finally:
        reader.shutdown()


def legacy_fields(case: LayoutCase):
    return {
        "model_name": case.model_name,
        "tokens_per_hash": case.tokens_per_hash,
        "blocks_per_file": case.blocks_per_chunk,
        "tp_size": 1,
        "pp_size": 1,
        "pcp_size": 1,
        "dcp_size": 1,
        "dtype": case.dtype,
        "kv_cache_groups": [
            {"tokens_per_block": tokens, "layer_names": list(layers)}
            for tokens, layers in case.groups
        ],
        "inference_engine": "vllm",
    }


def legacy_base_path(root: str, case: LayoutCase):
    fields = legacy_fields(case)
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:12]
    model_name = case.model_name.replace("/", "_")
    return Path(root) / f"{model_name}_{digest}"


def legacy_file_path(root: str, case: LayoutCase, item):
    base = legacy_base_path(root, case)
    hash_hex = get_offload_block_hash(item).hex()
    group_idx = get_offload_group_idx(item)
    return Path(f"{base}_r0") / hash_hex[:3] / f"{hash_hex[3:5]}_g{group_idx}" / f"{hash_hex}.bin"


def create_legacy_portable_artifact(root: str, case: LayoutCase, item, value):
    base = legacy_base_path(root, case)
    base.mkdir(parents=True, exist_ok=True)
    (base / "config.json").write_text(
        json.dumps(legacy_fields(case), indent=2, sort_keys=True)
    )
    path = legacy_file_path(root, case, item)
    path.parent.mkdir(parents=True, exist_ok=True)
    source = aligned_tensor(1)
    source[0].fill_(value)
    path.write_bytes(source.numpy().tobytes())


def legacy_portable_read(root: str, case: LayoutCase):
    item = key(99)
    create_legacy_portable_artifact(root, case, item, 73)
    tensor = aligned_tensor(2)
    manager = tier(root, tensor, make_spec(case, portable=True, tp_size=4, rank=3))
    try:
        assert lookup(manager, [item]) == [LookupResult.HIT]
        load_blocks(manager, tensor, [item], [1])
        assert_blocks(tensor, [1], [73])
    finally:
        manager.shutdown()
