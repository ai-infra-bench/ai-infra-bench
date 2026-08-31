import json
import threading
from dataclasses import dataclass

import pytest
from vllm.distributed.kv_transfer.kv_connector.v1.base import KVConnectorRole
from vllm.distributed.kv_transfer.kv_connector.v1.simple_cpu_offload_connector import (
    SimpleCPUOffloadConnector,
)
from vllm.v1.core.kv_cache_manager import KVCacheBlocks
from vllm.v1.outputs import KVConnectorOutput
from vllm.v1.request import Request
from vllm.v1.simple_kv_offload.metadata import SimpleCPUOffloadWorkerMetadata

from . import test_scheduler as helpers


@dataclass
class ConnectorFixture:
    connector: SimpleCPUOffloadConnector
    scheduler_fixture: helpers.SchedulerFixture


def _use_offline_model_config(tmp_path, monkeypatch):
    model_dir = tmp_path / "tiny-opt"
    model_dir.mkdir(exist_ok=True)
    (model_dir / "config.json").write_text(
        json.dumps(
            {
                "architectures": ["OPTForCausalLM"],
                "model_type": "opt",
                "hidden_size": 64,
                "ffn_dim": 256,
                "num_attention_heads": 4,
                "num_hidden_layers": 2,
                "vocab_size": 256,
                "max_position_embeddings": 10000,
                "word_embed_proj_dim": 64,
                "do_layer_norm_before": True,
                "torch_dtype": "float16",
            }
        )
    )
    original = helpers.ModelConfig

    def offline_model_config(*args, **kwargs):
        kwargs["model"] = str(model_dir)
        kwargs["skip_tokenizer_init"] = True
        return original(*args, **kwargs)

    monkeypatch.setattr(helpers, "ModelConfig", offline_model_config)


def _make_connector(tmp_path, monkeypatch, *, lazy: bool) -> ConnectorFixture:
    _use_offline_model_config(tmp_path, monkeypatch)
    base = helpers.make_scheduler(
        num_cpu_blocks=12,
        num_gpu_blocks=20,
        lazy=lazy,
    )
    bytes_per_block = sum(
        tensor.size for tensor in base.kv_cache_config.kv_cache_tensors
    ) // base.kv_cache_config.num_blocks
    base.vllm_config.kv_transfer_config.kv_connector_extra_config = {
        "cpu_bytes_to_use": bytes_per_block * 12,
        "lazy_offload": lazy,
    }
    connector = SimpleCPUOffloadConnector(
        base.vllm_config,
        KVConnectorRole.SCHEDULER,
        base.kv_cache_config,
    )
    connector.bind_gpu_block_pool(base.gpu_block_pool)
    assert connector.scheduler_manager is not None
    fixture = helpers.SchedulerFixture(
        scheduler=connector.scheduler_manager,
        gpu_block_pool=base.gpu_block_pool,
        vllm_config=base.vllm_config,
        kv_cache_config=base.kv_cache_config,
    )
    return ConnectorFixture(connector, fixture)


def _matching_request(source: Request, request_id: str) -> Request:
    return Request(
        request_id=request_id,
        prompt_token_ids=source.prompt_token_ids,
        sampling_params=source.sampling_params,
        pooling_params=None,
        mm_features=None,
        block_hasher=source._block_hasher,
    )


def _observed_hit(connector: SimpleCPUOffloadConnector, source: Request, suffix: str):
    probe = _matching_request(source, f"probe-{suffix}")
    hit_tokens, is_async = connector.get_num_new_matched_tokens(probe, 0)
    connector.request_finished(probe, [])
    return hit_tokens, is_async


def _complete_store(connector: SimpleCPUOffloadConnector, event_idx: int) -> None:
    connector.update_connector_output(
        KVConnectorOutput(
            finished_recving=set(),
            kv_connector_worker_meta=SimpleCPUOffloadWorkerMetadata(
                completed_store_events={event_idx: 1}
            ),
        )
    )


def _complete_load(connector: SimpleCPUOffloadConnector, req_id: str) -> None:
    connector.update_connector_output(
        KVConnectorOutput(
            finished_sending=set(),
            finished_recving={req_id},
        )
    )


def _start_eager_store(
    fix: ConnectorFixture,
    request: Request,
    *,
    num_blocks: int,
):
    connector = fix.connector
    fixture = fix.scheduler_fixture
    blocks = helpers._alloc_and_register(fixture, request, num_blocks)
    connector.update_state_after_alloc(request, blocks, num_external_tokens=0)
    block_ids = blocks.get_block_ids()
    metadata = connector.build_connector_meta(
        helpers.make_scheduler_output(
            {request.request_id: num_blocks * helpers.BLOCK_SIZE},
            new_reqs={request.request_id: block_ids},
        )
    )
    fixture.gpu_block_pool.free_blocks(
        fixture.gpu_block_pool.blocks[block_id] for block_id in block_ids[0]
    )
    assert metadata.store_event >= 0
    return metadata


def _start_lazy_store(
    fix: ConnectorFixture,
    request: Request,
    *,
    num_blocks: int,
):
    connector = fix.connector
    fixture = fix.scheduler_fixture
    gpu_pool = fixture.gpu_block_pool
    blocks = helpers._allocate_gpu_blocks(
        gpu_pool,
        request,
        num_blocks,
        group_id=0,
    )
    gpu_pool.free_blocks(blocks)
    fillers = helpers._flush_old_blocks_to_lru_head(
        gpu_pool,
        num_filler_blocks=gpu_pool.num_gpu_blocks - 1 - num_blocks,
    )
    metadata = connector.build_connector_meta(helpers.make_scheduler_output({}))
    gpu_pool.free_blocks(fillers)
    assert metadata.store_event >= 0
    return metadata


def _start_store(
    fix: ConnectorFixture,
    request: Request,
    *,
    lazy: bool,
    num_blocks: int,
):
    if lazy:
        return _start_lazy_store(fix, request, num_blocks=num_blocks)
    return _start_eager_store(fix, request, num_blocks=num_blocks)


def _populate_cache(
    fix: ConnectorFixture,
    request: Request,
    *,
    lazy: bool,
    num_blocks: int,
) -> None:
    metadata = _start_store(
        fix,
        request,
        lazy=lazy,
        num_blocks=num_blocks,
    )
    _complete_store(fix.connector, metadata.store_event)


def _start_load(fix: ConnectorFixture, source: Request, request_id: str):
    connector = fix.connector
    fixture = fix.scheduler_fixture
    loading = _matching_request(source, request_id)
    hit_tokens, is_async = connector.get_num_new_matched_tokens(loading, 0)
    assert hit_tokens > 0
    assert is_async is True
    num_blocks = hit_tokens // helpers.BLOCK_SIZE
    gpu_blocks = fixture.gpu_block_pool.get_new_blocks(num_blocks)
    loading_blocks = KVCacheBlocks(blocks=(gpu_blocks,))
    connector.update_state_after_alloc(
        loading,
        loading_blocks,
        num_external_tokens=hit_tokens,
    )
    metadata = connector.build_connector_meta(
        helpers.make_scheduler_output(
            {loading.request_id: 1},
            new_reqs={loading.request_id: loading_blocks.get_block_ids()},
        )
    )
    fixture.gpu_block_pool.free_blocks(gpu_blocks)
    assert metadata.load_event >= 0
    return loading, metadata


def _finish_in_background(completion):
    gate = threading.Event()
    errors = []

    def run():
        gate.wait(timeout=10)
        try:
            completion()
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return gate, thread, errors


def _assert_reset_waits_then_succeeds(connector, completion):
    gate, thread, errors = _finish_in_background(completion)
    assert connector.reset_cache() is False
    assert connector.reset_cache() is False
    gate.set()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert not errors
    assert connector.reset_cache() is True


def _assert_new_store_still_works(fix: ConnectorFixture, *, lazy: bool):
    num_blocks = 2
    fresh = helpers.make_request(num_blocks=num_blocks, request_id=f"fresh-{lazy}")
    _populate_cache(fix, fresh, lazy=lazy, num_blocks=num_blocks)
    hit_tokens, is_async = _observed_hit(fix.connector, fresh, f"fresh-{lazy}")
    assert hit_tokens == 2 * helpers.BLOCK_SIZE
    assert is_async is True


@pytest.mark.parametrize("lazy", [False, True], ids=["eager", "lazy"])
@pytest.mark.parametrize("num_blocks", [1, 3], ids=["short", "long"])
def test_idle_reset_clears_old_entries_and_is_idempotent(
    tmp_path,
    monkeypatch,
    lazy,
    num_blocks,
):
    fix = _make_connector(tmp_path, monkeypatch, lazy=lazy)
    source = helpers.make_request(
        num_blocks=num_blocks,
        request_id=f"idle-{lazy}-{num_blocks}",
    )
    _populate_cache(fix, source, lazy=lazy, num_blocks=num_blocks)
    assert _observed_hit(fix.connector, source, "before-reset")[0] > 0

    assert fix.connector.reset_cache() is True
    assert _observed_hit(fix.connector, source, "after-reset")[0] == 0
    assert fix.connector.reset_cache() is True
    _assert_new_store_still_works(fix, lazy=lazy)


@pytest.mark.parametrize("lazy", [False, True], ids=["eager", "lazy"])
@pytest.mark.parametrize("num_blocks", [1, 2, 3], ids=["short", "medium", "long"])
def test_inflight_store_cannot_repopulate_reset_cache(
    tmp_path,
    monkeypatch,
    lazy,
    num_blocks,
):
    fix = _make_connector(tmp_path, monkeypatch, lazy=lazy)
    source = helpers.make_request(
        num_blocks=num_blocks,
        request_id=f"store-{lazy}-{num_blocks}",
    )
    metadata = _start_store(
        fix,
        source,
        lazy=lazy,
        num_blocks=num_blocks,
    )

    _assert_reset_waits_then_succeeds(
        fix.connector,
        lambda: _complete_store(fix.connector, metadata.store_event),
    )
    assert _observed_hit(fix.connector, source, "old-store")[0] == 0
    _assert_new_store_still_works(fix, lazy=lazy)


@pytest.mark.parametrize("lazy", [False, True], ids=["eager", "lazy"])
@pytest.mark.parametrize("num_blocks", [1, 3], ids=["short", "long"])
def test_inflight_load_reset_recovers_and_clears_cache(
    tmp_path,
    monkeypatch,
    lazy,
    num_blocks,
):
    fix = _make_connector(tmp_path, monkeypatch, lazy=lazy)
    source = helpers.make_request(
        num_blocks=num_blocks,
        request_id=f"load-source-{lazy}-{num_blocks}",
    )
    _populate_cache(fix, source, lazy=lazy, num_blocks=num_blocks)
    loading, _metadata = _start_load(fix, source, f"loading-{lazy}")

    _assert_reset_waits_then_succeeds(
        fix.connector,
        lambda: _complete_load(fix.connector, loading.request_id),
    )
    assert _observed_hit(fix.connector, source, "old-load")[0] == 0
    _assert_new_store_still_works(fix, lazy=lazy)
