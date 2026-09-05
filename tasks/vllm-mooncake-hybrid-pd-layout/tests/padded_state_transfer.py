# SPDX-License-Identifier: Apache-2.0
"""Mixed-dtype padded GDN slots with successive partial-prefix transfers."""
import asyncio
from dataclasses import replace

import torch

from vllm.v1.kv_cache_interface import KVCacheGroupSpec
from verifier_support import (
    MemoryTransport, assert_cross_group_transfer, make_cross_group_shared_caches,
    make_cross_group_shared_config, make_worker_connector, mamba_storage_bytes,
    patched_worker_runtime, shutdown_connectors, transfer_once,
)


def run_padded_state_transfer(physical_ratio=4):
    logical = 64
    config = make_cross_group_shared_config(logical_block_size=logical, num_blocks=19)
    group = config.kv_cache_groups[1]
    spec = replace(group.kv_cache_spec, shapes=((12, 3), (2, 4, 4)),
                   dtypes=(torch.float16, torch.float32), page_size_padded=256)
    config.kv_cache_groups[1] = KVCacheGroupSpec(group.layer_names, spec)
    transport = MemoryTransport()
    results = []
    with patched_worker_runtime(transport, kernel_block_size=logical // physical_ratio):
        producer = make_worker_connector("kv_producer", config, logical_block_size=logical)
        consumer = make_worker_connector("kv_consumer", config, logical_block_size=logical)
        source = make_cross_group_shared_caches(config, physical_ratio=physical_ratio)
        destination = make_cross_group_shared_caches(config, physical_ratio=physical_ratio)
        src = mamba_storage_bytes(source["model.layers.1.linear_attn"])
        dst = mamba_storage_bytes(destination["model.layers.1.linear_attn"])
        src.copy_(torch.arange(src.numel()).mul(17).remainder(193).to(torch.uint8))
        dst.fill_(227)
        try:
            producer.register_kv_caches(source)
            consumer.register_kv_caches(destination)
            for step, (local, remote, attn_pairs, gdn_pairs) in enumerate([
                ([[2, 1, 3], [0, 4, 5]], [[6, 7], [0, 9]], [(1, 6), (3, 7)], [(5, 9)]),
                ([[18], [11]], [[10], [14]], [(18, 10)], [(11, 14)]),
            ]):
                before = dst.clone()
                finished = asyncio.run(transfer_once(
                    producer, consumer, local_block_ids=local, remote_block_ids=remote,
                    transfer_id=f"padded-state-{physical_ratio}-{step}",
                ))
                assert finished[1] == {"decoder-request"}
                result = assert_cross_group_transfer(
                    source, destination, before, attention_pairs=attn_pairs,
                    gdn_pairs=gdn_pairs, physical_ratio=physical_ratio,
                )
                results.append({"step": step, "completed": True, **result})
        finally:
            shutdown_connectors(producer, consumer)
    return results
