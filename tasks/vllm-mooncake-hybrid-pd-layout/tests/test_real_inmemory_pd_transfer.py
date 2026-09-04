# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio

import torch

from vllm.v1.attention.backends.utils import NULL_BLOCK_ID

from verifier_support import (
    MemoryTransport,
    make_hybrid_caches,
    make_hybrid_config,
    make_worker_connector,
    mamba_storage_bytes,
    patched_worker_runtime,
    shutdown_connectors,
    transfer_once,
)


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
            assert torch.equal(
                destination_gdn_temporal[4], source_gdn_temporal[2]
            )
            assert torch.equal(destination_gdn_conv[8], source_gdn_conv[5])
            assert torch.equal(
                destination_gdn_temporal[8], source_gdn_temporal[5]
            )
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

    print(
        "REAL_MOONCAKE_CPU_PD_OK "
        f"ratio={physical_ratio} descriptors={len(transport.transfers)}"
    )


if __name__ == "__main__":
    main()
