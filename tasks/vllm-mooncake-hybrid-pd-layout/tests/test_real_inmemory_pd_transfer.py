# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio

import torch

from vllm.v1.attention.backends.utils import NULL_BLOCK_ID

from verifier_support import (
    MemoryTransport,
    make_cross_group_shared_caches,
    make_hybrid_caches,
    make_hybrid_config,
    make_mla_caches,
    make_mla_config,
    make_worker_connector,
    mamba_storage_bytes,
    patched_worker_runtime,
    shutdown_connectors,
    transfer_once,
)


def run_cross_group_shared_transfer() -> int:
    logical_block_size = 16
    config = make_hybrid_config(
        logical_block_size=logical_block_size,
        num_blocks=12,
        attention_kind="full",
    )
    transport = MemoryTransport()
    with patched_worker_runtime(
        transport,
        kernel_block_size=logical_block_size,
    ):
        producer = make_worker_connector(
            "kv_producer", config, logical_block_size=logical_block_size
        )
        consumer = make_worker_connector(
            "kv_consumer", config, logical_block_size=logical_block_size
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
        before = destination_backing.clone()
        try:
            producer.register_kv_caches(source)
            consumer.register_kv_caches(destination)
            finished = asyncio.run(
                transfer_once(
                    producer,
                    consumer,
                    local_block_ids=[[1], [3]],
                    remote_block_ids=[[6], [8]],
                    transfer_id="e2e-cross-group-shared-backing",
                )
            )
            assert finished[1] == {"decoder-request"}
            page_stride_bytes = source_attention.stride(0)
            expected = before.clone()
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
        finally:
            shutdown_connectors(producer, consumer)
    return len(transport.transfers)


def run_non_gdn_mla_transfer(attention_kind: str) -> int:
    logical_block_size = 32
    physical_ratio = 4
    config = make_mla_config(
        logical_block_size=logical_block_size,
        num_blocks=13,
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
        source, source_backing = make_mla_caches(
            config, physical_ratio=physical_ratio, gap_bytes=24
        )
        destination, destination_backing = make_mla_caches(
            config, physical_ratio=physical_ratio, gap_bytes=24
        )
        source_backing.copy_(
            torch.arange(source_backing.numel(), dtype=torch.int64)
            .mul(7)
            .remainder(199)
            .to(torch.uint8)
            .reshape_as(source_backing)
        )
        destination_backing.fill_(229)
        expected = destination_backing.clone()
        page_bytes = (
            config.kv_cache_groups[0].kv_cache_spec.page_size_bytes // physical_ratio
        )
        for source_block, destination_block in ((2, 6), (3, 7), (5, 10)):
            source_rows = slice(
                source_block * physical_ratio, (source_block + 1) * physical_ratio
            )
            destination_rows = slice(
                destination_block * physical_ratio,
                (destination_block + 1) * physical_ratio,
            )
            for start in (0, page_bytes + 24):
                expected[destination_rows, start : start + page_bytes] = source_backing[
                    source_rows, start : start + page_bytes
                ]
        try:
            producer.register_kv_caches(source)
            consumer.register_kv_caches(destination)
            finished = asyncio.run(
                transfer_once(
                    producer,
                    consumer,
                    local_block_ids=[[1, 2, 3, 5]],
                    remote_block_ids=[[6, 7, 10]],
                    transfer_id=f"e2e-non-gdn-{attention_kind}",
                )
            )
            assert finished[1] == {"decoder-request"}
            assert torch.equal(destination_backing, expected)
        finally:
            shutdown_connectors(producer, consumer)
    return len(transport.transfers)


def main() -> None:
    logical_block_size = 18
    physical_ratio = 3
    config = make_hybrid_config(
        logical_block_size=logical_block_size,
        num_blocks=12,
        attention_kind="mla",
    )
    transport = MemoryTransport()

    with patched_worker_runtime(
        transport,
        kernel_block_size=logical_block_size // physical_ratio,
    ):
        producer = make_worker_connector(
            "kv_producer", config, logical_block_size=logical_block_size
        )
        consumer = make_worker_connector(
            "kv_consumer", config, logical_block_size=logical_block_size
        )
        source = make_hybrid_caches(config, physical_ratio=physical_ratio)
        destination = make_hybrid_caches(config, physical_ratio=physical_ratio)
        destination_attention = destination["model.layers.0.self_attn"]
        destination_gdn = destination["model.layers.1.linear_attn"]
        destination_gdn_conv, destination_gdn_temporal = destination_gdn
        destination_attention.fill_(211)
        mamba_storage_bytes(destination_gdn).fill_(211)

        try:
            producer.register_kv_caches(source)
            consumer.register_kv_caches(destination)

            source_attention = source["model.layers.0.self_attn"]
            source_gdn = source["model.layers.1.linear_attn"]
            source_gdn_conv, source_gdn_temporal = source_gdn
            for logical_block, base_value in ((0, 10), (1, 20), (3, 60)):
                start = logical_block * physical_ratio
                for offset in range(physical_ratio):
                    source_attention[start + offset].fill_(base_value + offset)
            source_gdn_conv[1].fill_(11)
            source_gdn_temporal[1].fill_(13)
            source_gdn_conv[2].fill_(17)
            source_gdn_temporal[2].fill_(23)
            source_gdn_conv[5].fill_(29)
            source_gdn_temporal[5].fill_(37)

            attention_before = destination_attention.clone()
            gdn_before = mamba_storage_bytes(destination_gdn).clone()
            source_gdn_bytes = mamba_storage_bytes(source_gdn)
            finished = asyncio.run(
                transfer_once(
                    producer,
                    consumer,
                    local_block_ids=[
                        [0, 1, 3],
                        [NULL_BLOCK_ID, 1, 2, 5],
                    ],
                    remote_block_ids=[
                        [7, 9],
                        [NULL_BLOCK_ID, 4, 8],
                    ],
                    transfer_id="e2e-hybrid-layout",
                )
            )

            assert finished[1] == {"decoder-request"}
            expected_attention = attention_before.clone()
            expected_attention[7 * physical_ratio : 8 * physical_ratio] = (
                source_attention[1 * physical_ratio : 2 * physical_ratio]
            )
            expected_attention[9 * physical_ratio : 10 * physical_ratio] = (
                source_attention[3 * physical_ratio : 4 * physical_ratio]
            )
            assert torch.equal(destination_gdn_conv[4], source_gdn_conv[2])
            assert torch.equal(destination_gdn_temporal[4], source_gdn_temporal[2])
            assert torch.equal(destination_gdn_conv[8], source_gdn_conv[5])
            assert torch.equal(destination_gdn_temporal[8], source_gdn_temporal[5])
            gdn_page_bytes = config.kv_cache_groups[1].kv_cache_spec.page_size_bytes
            expected_gdn = gdn_before.clone()
            expected_gdn[4 * gdn_page_bytes : 5 * gdn_page_bytes] = source_gdn_bytes[
                2 * gdn_page_bytes : 3 * gdn_page_bytes
            ]
            expected_gdn[8 * gdn_page_bytes : 9 * gdn_page_bytes] = source_gdn_bytes[
                5 * gdn_page_bytes : 6 * gdn_page_bytes
            ]
            assert torch.equal(destination_attention, expected_attention)
            assert torch.equal(mamba_storage_bytes(destination_gdn), expected_gdn)
            assert transport.transfers
        finally:
            shutdown_connectors(producer, consumer)

    shared_descriptors = run_cross_group_shared_transfer()
    mla_descriptors = run_non_gdn_mla_transfer("mla")
    sliding_mla_descriptors = run_non_gdn_mla_transfer("sliding_mla")
    print(
        "REAL_MOONCAKE_CPU_PD_OK "
        f"ratio={physical_ratio} descriptors={len(transport.transfers)} "
        f"cross_group_descriptors={shared_descriptors} "
        f"non_gdn_mla_descriptors={mla_descriptors} "
        f"non_gdn_sliding_mla_descriptors={sliding_mla_descriptors}"
    )


if __name__ == "__main__":
    main()
