# SPDX-License-Identifier: Apache-2.0
"""Compose real producer/consumer schedulers and worker entry points."""
from __future__ import annotations

import time
from unittest.mock import patch

import torch

from vllm import SamplingParams
from vllm.v1.attention.backends.utils import NULL_BLOCK_ID
from vllm.v1.outputs import KVConnectorOutput, ModelRunnerOutput
from vllm.v1.request import Request, RequestStatus

from verifier_support import (
    LoopbackDealerSocket, MemoryTransport, SocketContext, SuccessfulAsyncClient,
    SuccessfulResponse, assert_gdn_slots, create_model_runner_output,
    create_request, create_scheduler, make_cross_group_shared_config,
    make_hybrid_caches, make_vllm_config, make_worker_connector,
    mamba_storage_bytes, mooncake, patched_worker_runtime, shutdown_connectors,
)


def run_scheduler_handoff(*, num_tokens=51, prompt_kind="token_ids",
                          logical_block_size=16, physical_ratio=1, warm=False):
    """No fabricated send/pull metadata or finished_recving event is used."""
    config = make_cross_group_shared_config(
        logical_block_size=logical_block_size, num_blocks=64
    )
    p_config = make_vllm_config("kv_producer", logical_block_size=logical_block_size)
    d_config = make_vllm_config("kv_consumer", logical_block_size=logical_block_size)
    if prompt_kind == "prompt_embeddings":
        # These requests intentionally have no block hasher, as in the existing
        # embedding producer test. Do not enable an unrelated APC lookup that
        # requires hashes for full prompt blocks.
        p_config.cache_config.enable_prefix_caching = False
        d_config.cache_config.enable_prefix_caching = False
    p_scheduler = create_scheduler(p_config, num_blocks=64, kv_cache_config=config)
    d_scheduler = create_scheduler(d_config, num_blocks=64, kv_cache_config=config)

    # A completed, unrelated local request changes the decoder's allocation
    # order. Expected data is computed from the allocators, never from the
    # connector's transfer descriptors or receive metadata.
    priming = create_request(request_id=991, num_tokens=5, max_tokens=1,
                             block_size=logical_block_size)
    d_scheduler.add_request(priming)
    primed = d_scheduler.schedule()
    d_scheduler.update_from_output(primed, create_model_runner_output([priming], use_eos=True))

    if warm:
        assert prompt_kind == "token_ids"
        previous = create_request(request_id=992, num_tokens=num_tokens,
                                  common_prefix_len=num_tokens, max_tokens=1,
                                  block_size=logical_block_size)
        p_scheduler.add_request(previous)
        scheduled = p_scheduler.schedule()
        p_scheduler.update_from_output(scheduled, create_model_runner_output([previous], use_eos=True))

    def new_request(name, remote_decode):
        if prompt_kind == "token_ids":
            req = create_request(request_id=name, num_tokens=num_tokens,
                                 common_prefix_len=num_tokens,
                                 max_tokens=1, block_size=logical_block_size)
        else:
            req = Request(request_id=f"request-{name}", prompt_token_ids=None,
                          prompt_embeds=torch.arange(num_tokens * 8, dtype=torch.float32).reshape(num_tokens, 8),
                          sampling_params=SamplingParams(max_tokens=1),
                          pooling_params=None, block_hasher=None)
        req.kv_transfer_params = {
            "do_remote_prefill": not remote_decode,
            "do_remote_decode": remote_decode,
            "transfer_id": "scheduled-transfer",
            "remote_engine_id": "kv_producer-engine",
            "remote_bootstrap_addr": "http://single-producer",
        }
        return req

    p_request = new_request(201, True)
    d_request = new_request(202, False)
    p_scheduler.add_request(p_request)
    p_output = p_scheduler.schedule()
    p_blocks = p_scheduler.kv_cache_manager.get_block_ids(p_request.request_id)
    d_scheduler.add_request(d_request)
    waiting = d_scheduler.schedule()
    d_blocks = d_scheduler.kv_cache_manager.get_block_ids(d_request.request_id)
    assert d_request.status == RequestStatus.WAITING_FOR_REMOTE_KVS
    assert d_request.request_id not in waiting.num_scheduled_tokens

    transport = MemoryTransport()
    with patched_worker_runtime(transport, kernel_block_size=logical_block_size // physical_ratio):
        producer = make_worker_connector("kv_producer", config, logical_block_size=logical_block_size)
        consumer = make_worker_connector("kv_consumer", config, logical_block_size=logical_block_size)
        source = make_hybrid_caches(config, physical_ratio=physical_ratio)
        destination = make_hybrid_caches(config, physical_ratio=physical_ratio)
        for index, row in enumerate(source["model.layers.0.self_attn"]):
            row.copy_(torch.arange(row.numel()).add(7 * index).remainder(193).to(torch.uint8))
        for state_index, state in enumerate(source["model.layers.1.linear_attn"]):
            for block_id, row in enumerate(state):
                row.copy_(torch.arange(row.numel()).reshape_as(row).add(5 + 13 * block_id + 71 * state_index).to(row.dtype))
        destination["model.layers.0.self_attn"].fill_(211)
        mamba_storage_bytes(destination["model.layers.1.linear_attn"]).fill_(227)
        attention_before = destination["model.layers.0.self_attn"].clone()
        gdn_before = mamba_storage_bytes(destination["model.layers.1.linear_attn"]).clone()

        class DiscoveryResponse(SuccessfulResponse):
            def json(self):
                return {"0": {"engine_id": "kv_producer-engine", "worker_addr": {"0": {"0": "loopback"}}}}

        class DiscoveryClient(SuccessfulAsyncClient):
            async def get(self, _url):
                return DiscoveryResponse()

        def deliver(connector, scheduler_output):
            connector.bind_connector_metadata(scheduler_output.kv_connector_metadata)
            connector.start_load_kv(None)
            connector.clear_connector_metadata()

        try:
            producer.register_kv_caches(source)
            consumer.register_kv_caches(destination)
            dealer = LoopbackDealerSocket(producer.connector_worker)
            with patch.object(mooncake.httpx, "AsyncClient", DiscoveryClient), patch.object(
                mooncake, "make_zmq_socket", return_value=SocketContext(dealer)
            ):
                deliver(producer, p_output)
                p_result = p_scheduler.update_from_output(p_output, create_model_runner_output([p_request]))
                assert p_result[0].outputs[0].finish_reason is not None
                ready = p_scheduler.schedule()
                deliver(producer, ready)
                deliver(consumer, waiting)

                sent, received = set(), set()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    sent.update(producer.get_finished(set())[0] or ())
                    received.update(consumer.get_finished(set())[1] or ())
                    if p_request.request_id in sent and d_request.request_id in received:
                        break
                    time.sleep(0.005)

            # Propagate only completion emitted by the actual workers.
            d_scheduler.update_from_output(waiting, ModelRunnerOutput.with_kv_conn_output_only(
                KVConnectorOutput(finished_recving=received or None)))
            p_scheduler.update_from_output(ready, ModelRunnerOutput.with_kv_conn_output_only(
                KVConnectorOutput(finished_sending=sent or None)))
            resumed = d_scheduler.schedule()
            assert resumed.num_scheduled_tokens.get(d_request.request_id, 0) == 1, (
                "scheduled remote request did not receive state and resume",
                d_request.status.name, received, len(transport.transfers),
            )

            expected_attention = attention_before.clone()
            for src_id, dst_id in zip(p_blocks[0][-len(d_blocks[0]):], d_blocks[0], strict=True):
                expected_attention[dst_id * physical_ratio:(dst_id + 1) * physical_ratio] = source[
                    "model.layers.0.self_attn"
                ][src_id * physical_ratio:(src_id + 1) * physical_ratio]
            assert torch.equal(destination["model.layers.0.self_attn"], expected_attention)
            src_ids = [i for i in p_blocks[1] if i != NULL_BLOCK_ID]
            dst_ids = [i for i in d_blocks[1] if i != NULL_BLOCK_ID]
            assert src_ids and dst_ids, "a hybrid request must have live GDN state"
            assert_gdn_slots(source["model.layers.1.linear_attn"], destination["model.layers.1.linear_attn"],
                             gdn_before, list(zip(src_ids[-len(dst_ids):], dst_ids, strict=True)))
            result = d_scheduler.update_from_output(resumed, create_model_runner_output([d_request]))
            assert result[0].outputs[0].finish_reason is not None
            assert p_request.request_id in sent
            return {"prompt_kind": prompt_kind, "prompt_elements": num_tokens,
                    "warm": warm, "physical_ratio": physical_ratio,
                    "copy_descriptors": len(transport.transfers),
                    "producer_completed": True, "consumer_completed": True,
                    "local_recomputed_elements": 1}
        finally:
            shutdown_connectors(producer, consumer)
