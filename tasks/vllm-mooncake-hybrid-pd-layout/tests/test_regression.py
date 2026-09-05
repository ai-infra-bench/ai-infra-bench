# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio

import pytest
import torch

from vllm import SamplingParams
from vllm.distributed.kv_transfer.kv_connector.v1.base import KVConnectorRole
from vllm.distributed.kv_transfer.kv_connector.v1.mooncake.mooncake_connector import (
    MooncakeConnector,
)
from vllm.distributed.kv_transfer.kv_connector.v1.nixl.connector import NixlConnector
from vllm.v1.attention.backends.utils import NULL_BLOCK_ID
from vllm.v1.kv_cache_interface import KVCacheConfig, KVCacheGroupSpec
from vllm.v1.outputs import KVConnectorOutput, ModelRunnerOutput
from vllm.v1.request import Request, RequestStatus

from verifier_support import (
    MemoryTransport,
    create_model_runner_output,
    create_request,
    create_scheduler,
    make_cross_group_shared_caches,
    make_hybrid_caches,
    make_hybrid_config,
    make_mamba_cache,
    make_mla_caches,
    make_mla_config,
    make_pure_attention_caches,
    make_pure_attention_config,
    make_vllm_config,
    make_worker_connector,
    mamba_storage_bytes,
    patched_worker_runtime,
    shutdown_connectors,
    transfer_once,
)


LOGICAL_BLOCK_SIZE = 16


@pytest.mark.parametrize("attention_kind", ["mla", "sliding_mla"])
@pytest.mark.parametrize("physical_ratio", [1, 3])
def test_non_gdn_mla_shared_storage_preserves_payload_and_neighbors(
    attention_kind: str,
    physical_ratio: int,
) -> None:
    logical_block_size = 24
    config = make_mla_config(
        logical_block_size=logical_block_size,
        attention_kind=attention_kind,
    )
    transport = MemoryTransport()
    with patched_worker_runtime(
        transport,
        kernel_block_size=logical_block_size // physical_ratio,
        hybrid_backends=False,
        mla_backend=True,
    ):
        producer = make_worker_connector(
            "kv_producer", config, logical_block_size=logical_block_size
        )
        consumer = make_worker_connector(
            "kv_consumer", config, logical_block_size=logical_block_size
        )
        source, source_backing = make_mla_caches(config, physical_ratio=physical_ratio)
        destination, destination_backing = make_mla_caches(
            config, physical_ratio=physical_ratio
        )
        source_backing.copy_(
            torch.arange(source_backing.numel(), dtype=torch.int64)
            .remainder(197)
            .to(torch.uint8)
            .reshape_as(source_backing)
        )
        destination_backing.fill_(239)
        expected = destination_backing.clone()
        payload_bytes = (
            config.kv_cache_groups[0].kv_cache_spec.page_size_bytes // physical_ratio
        )
        for source_block, destination_block in ((4, 7), (2, 9)):
            source_rows = slice(
                source_block * physical_ratio, (source_block + 1) * physical_ratio
            )
            destination_rows = slice(
                destination_block * physical_ratio,
                (destination_block + 1) * physical_ratio,
            )
            for start in (0, payload_bytes + 16):
                expected[destination_rows, start : start + payload_bytes] = (
                    source_backing[source_rows, start : start + payload_bytes]
                )
        try:
            producer.register_kv_caches(source)
            consumer.register_kv_caches(destination)
            finished = asyncio.run(
                transfer_once(
                    producer,
                    consumer,
                    local_block_ids=[[1, 4, 2]],
                    remote_block_ids=[[7, 9]],
                    transfer_id=f"non-gdn-{attention_kind}-{physical_ratio}",
                )
            )
            assert finished[1] == {"decoder-request"}
            assert torch.equal(destination_backing, expected)
        finally:
            shutdown_connectors(producer, consumer)


def _register_pair(
    config: KVCacheConfig,
    *,
    transport: MemoryTransport,
    kernel_block_size: int,
    physical_ratio: int = 1,
):
    producer = make_worker_connector(
        "kv_producer", config, logical_block_size=LOGICAL_BLOCK_SIZE
    )
    consumer = make_worker_connector(
        "kv_consumer", config, logical_block_size=LOGICAL_BLOCK_SIZE
    )
    producer_caches = make_hybrid_caches(config, physical_ratio=physical_ratio)
    consumer_caches = make_hybrid_caches(config, physical_ratio=physical_ratio)
    producer.register_kv_caches(producer_caches)
    consumer.register_kv_caches(consumer_caches)
    return producer, consumer, producer_caches, consumer_caches


def test_hybrid_worker_initializes_and_registers_through_connector() -> None:
    config = make_hybrid_config(logical_block_size=LOGICAL_BLOCK_SIZE)
    transport = MemoryTransport()
    with patched_worker_runtime(transport, kernel_block_size=LOGICAL_BLOCK_SIZE):
        connector = make_worker_connector(
            "kv_consumer", config, logical_block_size=LOGICAL_BLOCK_SIZE
        )
        try:
            caches = make_hybrid_caches(config)
            connector.register_kv_caches(caches)
            assert transport.regions
        finally:
            shutdown_connectors(connector)


@pytest.mark.parametrize("attention_kind", ["full", "mla", "sliding_mla"])
def test_hybrid_transfer_preserves_group_payloads(attention_kind: str) -> None:
    config = make_hybrid_config(
        logical_block_size=LOGICAL_BLOCK_SIZE,
        attention_kind=attention_kind,
    )
    transport = MemoryTransport()
    with patched_worker_runtime(transport, kernel_block_size=LOGICAL_BLOCK_SIZE):
        producer, consumer, source, destination = _register_pair(
            config,
            transport=transport,
            kernel_block_size=LOGICAL_BLOCK_SIZE,
        )
        try:
            source_attention = source["model.layers.0.self_attn"]
            source_gdn = source["model.layers.1.linear_attn"]
            destination_attention = destination["model.layers.0.self_attn"]
            destination_gdn = destination["model.layers.1.linear_attn"]
            source_gdn_conv, source_gdn_temporal = source_gdn
            destination_gdn_conv, destination_gdn_temporal = destination_gdn
            source_attention[2].fill_(37)
            source_gdn_conv[4].fill_(19)
            source_gdn_temporal[4].fill_(23)
            attention_neighbor = destination_attention[6].clone()
            gdn_before = mamba_storage_bytes(destination_gdn).clone()
            source_gdn_bytes = mamba_storage_bytes(source_gdn)

            finished = asyncio.run(
                transfer_once(
                    producer,
                    consumer,
                    local_block_ids=[[2], [NULL_BLOCK_ID, 4]],
                    remote_block_ids=[[5], [NULL_BLOCK_ID, 7]],
                    transfer_id=f"transfer-{attention_kind}",
                )
            )

            assert finished[1] == {"decoder-request"}
            assert torch.equal(destination_attention[5], source_attention[2])
            assert torch.equal(destination_gdn_conv[7], source_gdn_conv[4])
            assert torch.equal(destination_gdn_temporal[7], source_gdn_temporal[4])
            assert torch.equal(destination_attention[6], attention_neighbor)
            gdn_page_bytes = config.kv_cache_groups[1].kv_cache_spec.page_size_bytes
            expected_gdn = gdn_before.clone()
            expected_gdn[7 * gdn_page_bytes : 8 * gdn_page_bytes] = source_gdn_bytes[
                4 * gdn_page_bytes : 5 * gdn_page_bytes
            ]
            assert torch.equal(mamba_storage_bytes(destination_gdn), expected_gdn)
        finally:
            shutdown_connectors(producer, consumer)


def test_shared_padded_storage_transfers_without_neighbor_corruption() -> None:
    base_config = make_hybrid_config(
        logical_block_size=LOGICAL_BLOCK_SIZE,
        attention_kind="mla",
        num_blocks=10,
    )
    config = KVCacheConfig(
        num_blocks=base_config.num_blocks,
        kv_cache_tensors=[],
        kv_cache_groups=[
            KVCacheGroupSpec(
                ["model.layers.0.self_attn", "model.layers.2.self_attn"],
                base_config.kv_cache_groups[0].kv_cache_spec,
            ),
            base_config.kv_cache_groups[1],
        ],
    )
    transport = MemoryTransport()
    with patched_worker_runtime(transport, kernel_block_size=LOGICAL_BLOCK_SIZE):
        producer = make_worker_connector(
            "kv_producer", config, logical_block_size=LOGICAL_BLOCK_SIZE
        )
        consumer = make_worker_connector(
            "kv_consumer", config, logical_block_size=LOGICAL_BLOCK_SIZE
        )
        source_backing = torch.zeros((10, 160), dtype=torch.uint8)
        destination_backing = torch.full((10, 160), 203, dtype=torch.uint8)
        mamba_spec = base_config.kv_cache_groups[1].kv_cache_spec
        source_gdn = make_mamba_cache(mamba_spec, 10)
        destination_gdn = make_mamba_cache(mamba_spec, 10)
        source = {
            "model.layers.0.self_attn": source_backing[:, :64],
            "model.layers.2.self_attn": source_backing[:, 80:144],
            "model.layers.1.linear_attn": source_gdn,
        }
        destination = {
            "model.layers.0.self_attn": destination_backing[:, :64],
            "model.layers.2.self_attn": destination_backing[:, 80:144],
            "model.layers.1.linear_attn": destination_gdn,
        }
        try:
            producer.register_kv_caches(source)
            consumer.register_kv_caches(destination)
            source_backing[1, :64].fill_(41)
            source_backing[1, 80:144].fill_(73)
            source_gdn_conv, source_gdn_temporal = source_gdn
            destination_gdn_conv, destination_gdn_temporal = destination_gdn
            mamba_storage_bytes(destination_gdn).fill_(203)
            source_gdn_conv[3].fill_(29)
            source_gdn_temporal[3].fill_(47)
            untouched_before = destination_backing.clone()
            gdn_before = mamba_storage_bytes(destination_gdn).clone()
            source_gdn_bytes = mamba_storage_bytes(source_gdn)

            finished = asyncio.run(
                transfer_once(
                    producer,
                    consumer,
                    local_block_ids=[[1], [3]],
                    remote_block_ids=[[6], [8]],
                    transfer_id="shared-padded",
                )
            )

            assert finished[1] == {"decoder-request"}
            assert torch.equal(destination_backing[6, :64], source_backing[1, :64])
            assert torch.equal(
                destination_backing[6, 80:144], source_backing[1, 80:144]
            )
            assert torch.equal(destination_gdn_conv[8], source_gdn_conv[3])
            assert torch.equal(destination_gdn_temporal[8], source_gdn_temporal[3])
            expected = untouched_before.clone()
            expected[6, :64] = source_backing[1, :64]
            expected[6, 80:144] = source_backing[1, 80:144]
            assert torch.equal(destination_backing, expected)
            expected_gdn = gdn_before.clone()
            gdn_page_bytes = mamba_spec.page_size_bytes
            expected_gdn[8 * gdn_page_bytes : 9 * gdn_page_bytes] = source_gdn_bytes[
                3 * gdn_page_bytes : 4 * gdn_page_bytes
            ]
            assert torch.equal(mamba_storage_bytes(destination_gdn), expected_gdn)
        finally:
            shutdown_connectors(producer, consumer)


def test_cross_group_shared_backing_preserves_all_transfer_regions() -> None:
    config = make_hybrid_config(
        logical_block_size=LOGICAL_BLOCK_SIZE,
        num_blocks=12,
        attention_kind="full",
    )
    transport = MemoryTransport()
    with patched_worker_runtime(transport, kernel_block_size=LOGICAL_BLOCK_SIZE):
        producer = make_worker_connector(
            "kv_producer", config, logical_block_size=LOGICAL_BLOCK_SIZE
        )
        consumer = make_worker_connector(
            "kv_consumer", config, logical_block_size=LOGICAL_BLOCK_SIZE
        )
        source = make_cross_group_shared_caches(config)
        destination = make_cross_group_shared_caches(config)
        source_attention = source["model.layers.0.self_attn"]
        destination_attention = destination["model.layers.0.self_attn"]
        source_gdn = source["model.layers.1.linear_attn"]
        destination_gdn = destination["model.layers.1.linear_attn"]
        source_backing = mamba_storage_bytes(source_gdn)
        destination_backing = mamba_storage_bytes(destination_gdn)
        destination_backing.fill_(211)
        source_attention[1].copy_(
            torch.arange(source_attention.shape[1], dtype=torch.uint8)
        )
        source_gdn[0][3].fill_(37)
        source_gdn[1][3].fill_(41)
        destination_before = destination_backing.clone()

        try:
            producer.register_kv_caches(source)
            consumer.register_kv_caches(destination)

            finished = asyncio.run(
                transfer_once(
                    producer,
                    consumer,
                    local_block_ids=[[1], [3]],
                    remote_block_ids=[[6], [8]],
                    transfer_id="cross-group-shared-backing",
                )
            )

            assert finished[1] == {"decoder-request"}
            page_stride_bytes = source_attention.stride(0)
            expected = destination_before.clone()
            expected[6 * page_stride_bytes : 7 * page_stride_bytes] = source_backing[
                1 * page_stride_bytes : 2 * page_stride_bytes
            ]
            expected[8 * page_stride_bytes : 9 * page_stride_bytes] = source_backing[
                3 * page_stride_bytes : 4 * page_stride_bytes
            ]
            assert torch.equal(destination_attention[6], source_attention[1])
            assert torch.equal(destination_gdn[0][8], source_gdn[0][3])
            assert torch.equal(destination_gdn[1][8], source_gdn[1][3])
            assert torch.equal(destination_backing, expected)
            assert transport.transfers
        finally:
            shutdown_connectors(producer, consumer)


def test_partial_prefix_transfers_requested_suffix_per_group() -> None:
    config = make_hybrid_config(
        logical_block_size=LOGICAL_BLOCK_SIZE,
        num_blocks=12,
        attention_kind="full",
    )
    transport = MemoryTransport()
    with patched_worker_runtime(transport, kernel_block_size=LOGICAL_BLOCK_SIZE):
        producer, consumer, source, destination = _register_pair(
            config,
            transport=transport,
            kernel_block_size=LOGICAL_BLOCK_SIZE,
        )
        try:
            source_attention = source["model.layers.0.self_attn"]
            destination_attention = destination["model.layers.0.self_attn"]
            source_gdn = source["model.layers.1.linear_attn"]
            destination_gdn = destination["model.layers.1.linear_attn"]
            source_attention[1].fill_(11)
            source_attention[4].fill_(47)
            source_gdn[0][2].fill_(21)
            source_gdn[1][2].fill_(23)
            source_gdn[0][6].fill_(61)
            source_gdn[1][6].fill_(67)
            destination_attention.fill_(193)
            mamba_storage_bytes(destination_gdn).fill_(197)
            attention_before = destination_attention.clone()
            gdn_before = mamba_storage_bytes(destination_gdn).clone()
            source_gdn_bytes = mamba_storage_bytes(source_gdn)

            finished = asyncio.run(
                transfer_once(
                    producer,
                    consumer,
                    local_block_ids=[[1, 4], [NULL_BLOCK_ID, 2, 6]],
                    remote_block_ids=[[7], [NULL_BLOCK_ID, 9]],
                    transfer_id="partial-prefix-per-group",
                )
            )

            assert finished[1] == {"decoder-request"}
            expected_attention = attention_before.clone()
            expected_attention[7] = source_attention[4]
            assert torch.equal(destination_attention, expected_attention)
            gdn_page_bytes = config.kv_cache_groups[1].kv_cache_spec.page_size_bytes
            expected_gdn = gdn_before.clone()
            expected_gdn[9 * gdn_page_bytes : 10 * gdn_page_bytes] = source_gdn_bytes[
                6 * gdn_page_bytes : 7 * gdn_page_bytes
            ]
            assert torch.equal(mamba_storage_bytes(destination_gdn), expected_gdn)
            assert torch.equal(destination_gdn[0][9], source_gdn[0][6])
            assert torch.equal(destination_gdn[1][9], source_gdn[1][6])
        finally:
            shutdown_connectors(producer, consumer)


@pytest.mark.parametrize("attention_kind", ["full", "mla", "sliding_mla"])
def test_physical_block_expansion_copies_only_requested_payload(
    attention_kind: str,
) -> None:
    ratio = 4
    config = make_hybrid_config(
        logical_block_size=LOGICAL_BLOCK_SIZE,
        attention_kind=attention_kind,
        num_blocks=10,
    )
    transport = MemoryTransport()
    with patched_worker_runtime(
        transport, kernel_block_size=LOGICAL_BLOCK_SIZE // ratio
    ):
        producer, consumer, source, destination = _register_pair(
            config,
            transport=transport,
            kernel_block_size=LOGICAL_BLOCK_SIZE // ratio,
            physical_ratio=ratio,
        )
        try:
            source_attention = source["model.layers.0.self_attn"]
            destination_attention = destination["model.layers.0.self_attn"]
            source_rows = slice(2 * ratio, 3 * ratio)
            destination_rows = slice(5 * ratio, 6 * ratio)
            for offset, row in enumerate(range(source_rows.start, source_rows.stop)):
                source_attention[row].fill_(30 + offset)
            before = destination_attention.clone()

            finished = asyncio.run(
                transfer_once(
                    producer,
                    consumer,
                    local_block_ids=[[2], []],
                    remote_block_ids=[[5], []],
                    transfer_id=f"ratio-{attention_kind}",
                )
            )

            assert finished[1] == {"decoder-request"}
            assert torch.equal(
                destination_attention[destination_rows], source_attention[source_rows]
            )
            expected = before.clone()
            expected[destination_rows] = source_attention[source_rows]
            assert torch.equal(destination_attention, expected)
        finally:
            shutdown_connectors(producer, consumer)


def test_transfer_failure_is_not_reported_as_complete() -> None:
    config = make_hybrid_config(logical_block_size=LOGICAL_BLOCK_SIZE)
    transport = MemoryTransport()
    with patched_worker_runtime(transport, kernel_block_size=LOGICAL_BLOCK_SIZE):
        producer, consumer, source, destination = _register_pair(
            config,
            transport=transport,
            kernel_block_size=LOGICAL_BLOCK_SIZE,
        )
        try:
            source["model.layers.0.self_attn"][1].fill_(51)
            before = destination["model.layers.0.self_attn"].clone()
            transport.fail_transfer = True
            finished = asyncio.run(
                transfer_once(
                    producer,
                    consumer,
                    local_block_ids=[[1], []],
                    remote_block_ids=[[4], []],
                    transfer_id="failed-transfer",
                )
            )
            assert finished[1] is None
            assert torch.equal(destination["model.layers.0.self_attn"], before)
        finally:
            shutdown_connectors(producer, consumer)


def test_pure_full_attention_transfer_is_unchanged() -> None:
    config = make_pure_attention_config(logical_block_size=LOGICAL_BLOCK_SIZE)
    transport = MemoryTransport()
    with patched_worker_runtime(
        transport,
        kernel_block_size=LOGICAL_BLOCK_SIZE,
        hybrid_backends=False,
    ):
        producer = make_worker_connector(
            "kv_producer", config, logical_block_size=LOGICAL_BLOCK_SIZE
        )
        consumer = make_worker_connector(
            "kv_consumer", config, logical_block_size=LOGICAL_BLOCK_SIZE
        )
        source = make_pure_attention_caches(config)
        destination = make_pure_attention_caches(config)
        try:
            producer.register_kv_caches(source)
            consumer.register_kv_caches(destination)
            source_attention = source["model.layers.0.self_attn"]
            destination_attention = destination["model.layers.0.self_attn"]
            source_attention[2].fill_(91)
            before = destination_attention.clone()
            finished = asyncio.run(
                transfer_once(
                    producer,
                    consumer,
                    local_block_ids=[[2]],
                    remote_block_ids=[[6]],
                    transfer_id="pure-attention",
                )
            )
            assert finished[1] == {"decoder-request"}
            expected = before.clone()
            expected[6] = source_attention[2]
            assert torch.equal(destination_attention, expected)
        finally:
            shutdown_connectors(producer, consumer)


def test_layout_mismatch_is_not_reported_as_complete() -> None:
    producer_config = make_hybrid_config(logical_block_size=LOGICAL_BLOCK_SIZE)
    consumer_config = KVCacheConfig(
        num_blocks=producer_config.num_blocks,
        kv_cache_tensors=[],
        kv_cache_groups=list(reversed(producer_config.kv_cache_groups)),
    )
    transport = MemoryTransport()
    with patched_worker_runtime(transport, kernel_block_size=LOGICAL_BLOCK_SIZE):
        producer = make_worker_connector(
            "kv_producer",
            producer_config,
            logical_block_size=LOGICAL_BLOCK_SIZE,
        )
        consumer = make_worker_connector(
            "kv_consumer",
            consumer_config,
            logical_block_size=LOGICAL_BLOCK_SIZE,
        )
        try:
            producer.register_kv_caches(make_hybrid_caches(producer_config))
            consumer.register_kv_caches(make_hybrid_caches(producer_config))
            finished = asyncio.run(
                transfer_once(
                    producer,
                    consumer,
                    local_block_ids=[[1], [2]],
                    remote_block_ids=[[3], [4]],
                    transfer_id="layout-mismatch",
                )
            )
            assert finished[1] is None
            assert transport.transfers == []
        finally:
            shutdown_connectors(producer, consumer)


def test_group_count_mismatch_is_not_reported_as_complete() -> None:
    config = make_hybrid_config(logical_block_size=LOGICAL_BLOCK_SIZE)
    transport = MemoryTransport()
    with patched_worker_runtime(transport, kernel_block_size=LOGICAL_BLOCK_SIZE):
        producer, consumer, _source, _destination = _register_pair(
            config,
            transport=transport,
            kernel_block_size=LOGICAL_BLOCK_SIZE,
        )
        try:
            finished = asyncio.run(
                transfer_once(
                    producer,
                    consumer,
                    local_block_ids=[[1], [2]],
                    remote_block_ids=[[3]],
                    transfer_id="group-count-mismatch",
                )
            )
            assert finished[1] is None
            assert transport.transfers == []
        finally:
            shutdown_connectors(producer, consumer)


def test_hybrid_remote_prefill_leaves_one_token_for_decode() -> None:
    config = make_hybrid_config(logical_block_size=LOGICAL_BLOCK_SIZE)
    vllm_config = make_vllm_config("kv_consumer", logical_block_size=LOGICAL_BLOCK_SIZE)
    connector = MooncakeConnector(vllm_config, KVConnectorRole.SCHEDULER, config)
    request = create_request(
        request_id=31,
        block_size=LOGICAL_BLOCK_SIZE,
        num_tokens=35,
        do_remote_prefill=True,
    )
    matched, asynchronous = connector.get_num_new_matched_tokens(request, 0)
    assert matched == 34
    assert asynchronous is True


@pytest.mark.parametrize("prompt_kind", ["token_ids", "prompt_embeddings"])
def test_two_element_gdn_remote_decode_boundary(prompt_kind: str) -> None:
    prompt_token_ids = [101, 202] if prompt_kind == "token_ids" else None
    prompt_embeds = (
        torch.arange(2 * 8, dtype=torch.float32).reshape(2, 8)
        if prompt_kind == "prompt_embeddings"
        else None
    )

    def make_request(request_id: str, *, remote_decode: bool) -> Request:
        request = Request(
            request_id=request_id,
            prompt_token_ids=(
                list(prompt_token_ids) if prompt_token_ids is not None else None
            ),
            prompt_embeds=(
                prompt_embeds.clone() if prompt_embeds is not None else None
            ),
            sampling_params=SamplingParams(max_tokens=1),
            pooling_params=None,
            block_hasher=None,
        )
        request.kv_transfer_params = {
            "do_remote_prefill": not remote_decode,
            "do_remote_decode": remote_decode,
            "transfer_id": f"transfer-{request_id}",
        }
        if not remote_decode:
            request.kv_transfer_params.update(
                {
                    "remote_engine_id": "producer-engine",
                    "remote_bootstrap_addr": "http://unused",
                }
            )
        return request

    config = make_hybrid_config(
        logical_block_size=LOGICAL_BLOCK_SIZE,
        num_blocks=64,
    )
    producer_config = make_vllm_config(
        "kv_producer", logical_block_size=LOGICAL_BLOCK_SIZE
    )
    producer = create_scheduler(
        producer_config,
        num_blocks=64,
        kv_cache_config=config,
    )
    producer_request = make_request(f"producer-{prompt_kind}", remote_decode=True)
    producer.add_request(producer_request)
    producer_output = producer.schedule()
    assert producer_request.num_prompt_tokens == 1
    if prompt_token_ids is not None:
        assert producer_request.prompt_token_ids == prompt_token_ids[:1]
    else:
        assert torch.equal(producer_request.prompt_embeds, prompt_embeds[:1])
    assert producer_output.num_scheduled_tokens[producer_request.request_id] == 1
    producer_result = producer.update_from_output(
        producer_output,
        create_model_runner_output([producer_request]),
    )
    assert producer_result[0].outputs[0].finish_reason is not None

    consumer_config = make_vllm_config(
        "kv_consumer", logical_block_size=LOGICAL_BLOCK_SIZE
    )
    consumer = create_scheduler(
        consumer_config,
        num_blocks=64,
        kv_cache_config=config,
    )
    consumer_request = make_request(f"consumer-{prompt_kind}", remote_decode=False)
    consumer.add_request(consumer_request)
    waiting_output = consumer.schedule()
    assert consumer_request.status == RequestStatus.WAITING_FOR_REMOTE_KVS
    assert consumer_request.num_computed_tokens == 1
    assert consumer_request.request_id not in waiting_output.num_scheduled_tokens
    received = ModelRunnerOutput.with_kv_conn_output_only(
        KVConnectorOutput(finished_recving={consumer_request.request_id})
    )
    consumer.update_from_output(waiting_output, received)
    resumed_output = consumer.schedule()
    assert resumed_output.num_scheduled_tokens[consumer_request.request_id] == 1
    consumer_result = consumer.update_from_output(
        resumed_output,
        create_model_runner_output([consumer_request]),
    )
    assert consumer_result[0].outputs[0].finish_reason is not None


def test_prompt_embeddings_remote_prefill_uses_remote_state_then_resumes() -> None:
    embeddings = torch.arange(9 * 8, dtype=torch.float32).reshape(9, 8)

    def make_request(request_id: str) -> Request:
        request = Request(
            request_id=request_id,
            prompt_token_ids=None,
            prompt_embeds=embeddings.clone(),
            sampling_params=SamplingParams(max_tokens=1),
            pooling_params=None,
            block_hasher=None,
        )
        request.kv_transfer_params = {
            "do_remote_prefill": True,
            "do_remote_decode": False,
            "transfer_id": f"transfer-{request_id}",
            "remote_engine_id": "producer-engine",
            "remote_bootstrap_addr": "http://unused",
        }
        return request

    config = make_hybrid_config(
        logical_block_size=LOGICAL_BLOCK_SIZE,
        num_blocks=64,
    )
    vllm_config = make_vllm_config("kv_consumer", logical_block_size=LOGICAL_BLOCK_SIZE)
    connector = MooncakeConnector(vllm_config, KVConnectorRole.SCHEDULER, config)
    partial_request = make_request("partial-embedding-request")
    assert connector.get_num_new_matched_tokens(partial_request, 3) == (5, True)

    pure_config = make_pure_attention_config(logical_block_size=LOGICAL_BLOCK_SIZE)
    pure_vllm_config = make_vllm_config(
        "kv_consumer", logical_block_size=LOGICAL_BLOCK_SIZE
    )
    pure_connector = MooncakeConnector(
        pure_vllm_config,
        KVConnectorRole.SCHEDULER,
        pure_config,
    )
    pure_request = make_request("pure-embedding-request")
    assert pure_connector.get_num_new_matched_tokens(pure_request, 0) == (9, True)

    scheduler = create_scheduler(
        vllm_config,
        num_blocks=64,
        kv_cache_config=config,
    )
    request = make_request("consumer-embedding-request")
    scheduler.add_request(request)
    waiting_output = scheduler.schedule()
    assert request.status == RequestStatus.WAITING_FOR_REMOTE_KVS
    assert request.num_computed_tokens == 8
    assert request.request_id not in waiting_output.num_scheduled_tokens

    received = ModelRunnerOutput.with_kv_conn_output_only(
        KVConnectorOutput(finished_recving={request.request_id})
    )
    scheduler.update_from_output(waiting_output, received)
    resumed_output = scheduler.schedule()
    assert request.status == RequestStatus.RUNNING
    assert resumed_output.num_scheduled_tokens[request.request_id] == 1
    result = scheduler.update_from_output(
        resumed_output,
        create_model_runner_output([request]),
    )
    assert result[0].outputs[0].finish_reason is not None


def test_pure_attention_remote_prefill_keeps_full_prompt() -> None:
    config = make_pure_attention_config(logical_block_size=LOGICAL_BLOCK_SIZE)
    vllm_config = make_vllm_config("kv_consumer", logical_block_size=LOGICAL_BLOCK_SIZE)
    connector = MooncakeConnector(vllm_config, KVConnectorRole.SCHEDULER, config)
    request = create_request(
        request_id=32,
        block_size=LOGICAL_BLOCK_SIZE,
        num_tokens=35,
        do_remote_prefill=True,
    )
    matched, asynchronous = connector.get_num_new_matched_tokens(request, 0)
    assert matched == 35
    assert asynchronous is True


def test_nixl_hybrid_remote_prefill_behavior_is_unchanged() -> None:
    config = make_hybrid_config(logical_block_size=LOGICAL_BLOCK_SIZE)
    vllm_config = make_vllm_config(
        "kv_consumer",
        logical_block_size=LOGICAL_BLOCK_SIZE,
        connector="NixlConnector",
    )
    connector = NixlConnector(vllm_config, KVConnectorRole.SCHEDULER, config)
    request = create_request(
        request_id=33,
        block_size=LOGICAL_BLOCK_SIZE,
        num_tokens=35,
        do_remote_prefill=True,
    )
    matched, asynchronous = connector.get_num_new_matched_tokens(request, 0)
    assert matched == 34
    assert asynchronous is True


def test_warm_full_prefix_remote_decode_remains_schedulable() -> None:
    config = make_hybrid_config(
        logical_block_size=LOGICAL_BLOCK_SIZE,
        num_blocks=64,
    )
    vllm_config = make_vllm_config("kv_producer", logical_block_size=LOGICAL_BLOCK_SIZE)
    scheduler = create_scheduler(vllm_config, num_blocks=64, kv_cache_config=config)

    warm = create_request(
        request_id=41,
        block_size=LOGICAL_BLOCK_SIZE,
        num_tokens=LOGICAL_BLOCK_SIZE + 1,
        common_prefix_len=LOGICAL_BLOCK_SIZE + 1,
        max_tokens=1,
    )
    scheduler.add_request(warm)
    output = scheduler.schedule()
    scheduler.update_from_output(
        output, create_model_runner_output([warm], use_eos=True)
    )

    repeated = create_request(
        request_id=42,
        block_size=LOGICAL_BLOCK_SIZE,
        num_tokens=LOGICAL_BLOCK_SIZE + 1,
        common_prefix_len=LOGICAL_BLOCK_SIZE + 1,
        do_remote_decode=True,
    )
    scheduler.add_request(repeated)
    output = scheduler.schedule()
    assert output.num_scheduled_tokens[repeated.request_id] > 0
    assert repeated.num_prompt_tokens == LOGICAL_BLOCK_SIZE
    repeated_result = scheduler.update_from_output(
        output, create_model_runner_output([repeated])
    )
    assert repeated_result[0].outputs[0].finish_reason is not None

    follow_up = create_request(
        request_id=43,
        block_size=LOGICAL_BLOCK_SIZE,
        num_tokens=7,
        max_tokens=1,
    )
    scheduler.add_request(follow_up)
    output = scheduler.schedule()
    assert output.num_scheduled_tokens[follow_up.request_id] > 0
    follow_up_result = scheduler.update_from_output(
        output, create_model_runner_output([follow_up], use_eos=True)
    )
    assert follow_up_result[0].outputs[0].finish_reason is not None


def test_prompt_embeddings_remote_decode_remains_schedulable() -> None:
    config = make_hybrid_config(
        logical_block_size=LOGICAL_BLOCK_SIZE,
        num_blocks=64,
    )
    vllm_config = make_vllm_config("kv_producer", logical_block_size=LOGICAL_BLOCK_SIZE)
    vllm_config.cache_config.enable_prefix_caching = False
    scheduler = create_scheduler(vllm_config, num_blocks=64, kv_cache_config=config)
    embeddings = torch.arange(
        (LOGICAL_BLOCK_SIZE + 1) * 8, dtype=torch.float32
    ).reshape(LOGICAL_BLOCK_SIZE + 1, 8)
    original_embeddings = embeddings.clone()
    request = Request(
        request_id="embedding-request",
        prompt_token_ids=None,
        prompt_embeds=embeddings,
        sampling_params=SamplingParams(max_tokens=8),
        pooling_params=None,
        block_hasher=None,
    )
    request.kv_transfer_params = {
        "do_remote_prefill": False,
        "do_remote_decode": True,
        "transfer_id": "embedding-transfer",
    }
    scheduler.add_request(request)
    output = scheduler.schedule()
    assert output.num_scheduled_tokens[request.request_id] > 0
    assert request.num_prompt_tokens == LOGICAL_BLOCK_SIZE
    assert torch.equal(request.prompt_embeds, original_embeddings[:-1])
    result = scheduler.update_from_output(output, create_model_runner_output([request]))
    assert result[0].outputs[0].finish_reason is not None


def test_scheduler_can_finish_cold_gdn_remote_decode() -> None:
    config = make_hybrid_config(
        logical_block_size=LOGICAL_BLOCK_SIZE,
        num_blocks=64,
    )
    vllm_config = make_vllm_config("kv_producer", logical_block_size=LOGICAL_BLOCK_SIZE)
    scheduler = create_scheduler(vllm_config, num_blocks=64, kv_cache_config=config)
    request = create_request(
        request_id=51,
        block_size=LOGICAL_BLOCK_SIZE,
        num_tokens=35,
        do_remote_decode=True,
    )
    original_prompt_token_ids = list(request.prompt_token_ids)
    scheduler.add_request(request)
    output = scheduler.schedule()
    assert output.num_scheduled_tokens[request.request_id] == 34
    assert request.prompt_token_ids == original_prompt_token_ids[:-1]
    result = scheduler.update_from_output(output, create_model_runner_output([request]))
    assert result[0].outputs[0].finish_reason is not None
