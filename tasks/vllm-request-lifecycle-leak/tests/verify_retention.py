"""Behavior worker. OS memory observations are collected by the parent, not here."""
from __future__ import annotations
import gc
import json
import random
import sys
import weakref
from types import SimpleNamespace as NS

# Read run parameters before importing candidate code. This reduces accidental
# protocol interference; it is not a security boundary against arbitrary Python.
settings = json.loads(sys.stdin.readline())
sys.path.insert(0, '/workspace/repo')
import torch
from vllm.config import CacheConfig, ParallelConfig, SchedulerConfig, ObservabilityConfig
from vllm.multimodal.inputs import MultiModalFeatureSpec, PlaceholderRange
from vllm.sampling_params import SamplingParams
from vllm.utils.hashing import sha256
from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.kv_cache_interface import FullAttentionSpec, KVCacheConfig, KVCacheGroupSpec
from vllm.v1.outputs import ModelRunnerOutput
from vllm.v1.request import Request, RequestStatus

init_none_hash(sha256)
hasher = get_request_block_hasher(4, sha256)
rng = random.Random(settings['seed'])

class Payload:
    def __init__(self, size=256 * 1024):
        self.data = bytearray(size)
        # Commit every page; virtual allocation alone is not memory evidence.
        for offset in range(0, size, 4096):
            self.data[offset] = 73

class ModelInputs:
    """Fixed media shape provider; real scheduler and encoder ownership run."""
    def supports_multimodal_inputs(self, config):
        return True
    def processor_only_cache_from_config(self, config):
        return None
    def create_processor(self, config, cache=None):
        return NS(info=NS(supported_mm_limits={'image': 1},
            allowed_mm_limits={'image': 1},
            get_mm_max_tokens_per_item=lambda **kw: {'image': 4}))

def make_scheduler(caching=True):
    cache = CacheConfig(block_size=4, enable_prefix_caching=caching)
    cache.num_gpu_blocks = 512
    config = NS(
        scheduler_config=SchedulerConfig(max_num_seqs=32, max_num_batched_tokens=512,
            max_model_len=256, enable_chunked_prefill=True, is_encoder_decoder=False),
        cache_config=cache, lora_config=None, kv_events_config=None,
        parallel_config=ParallelConfig(), observability_config=ObservabilityConfig(),
        model_config=NS(is_encoder_decoder=False, max_model_len=256,
            enable_return_routed_experts=False,
            get_multimodal_config=lambda: NS(enable_mm_embeds=False)),
        kv_transfer_config=None, ec_transfer_config=None, speculative_config=None)
    kv = KVCacheConfig(num_blocks=512, kv_cache_tensors=[], kv_cache_groups=[
        KVCacheGroupSpec(['layer'], FullAttentionSpec(block_size=4,
            num_kv_heads=1, head_size=8, dtype=torch.float32))])
    return Scheduler(config, kv, NS(should_advance=lambda request: False),
                     block_size=4, mm_registry=ModelInputs())

def make_request(name, *, tokens=None, image='image-A', resumable=False,
                 caching=True, size=256 * 1024, media=True):
    payload = Payload(size)
    mm = [MultiModalFeatureSpec(data={'payload': payload}, modality='image',
        identifier=image, mm_position=PlaceholderRange(offset=0, length=4))] if media else []
    request = Request(request_id=name, prompt_token_ids=list(tokens) if tokens is not None else list(range(1, 9)),
        sampling_params=SamplingParams(max_tokens=24), pooling_params=None,
        eos_token_id=0, mm_features=mm, block_hasher=hasher if caching else None,
        resumable=resumable)
    return request, payload

def step(scheduler, token=0):
    scheduled = scheduler.schedule()
    ids = list(scheduled.num_scheduled_tokens)
    assert ids, 'eligible request was not scheduled'
    output = ModelRunnerOutput(req_ids=ids,
        req_id_to_index={name: i for i, name in enumerate(ids)},
        sampled_token_ids=[[token] for _ in ids])
    result = scheduler.update_from_output(scheduled, output)
    returned = [entry for batch in result.values() for entry in batch.outputs]
    assert {entry.request_id for entry in returned} == set(ids)
    assert all(entry.new_token_ids == [token] for entry in returned)
    return result

def lifecycle(mode, caching=True):
    scheduler = make_scheduler(caching)
    request, payload = make_request(mode, resumable=mode.startswith('stream'), caching=caching)
    rid = request.request_id
    refs = weakref.ref(request), weakref.ref(payload)
    scheduler.add_request(request)
    del request, payload
    assert all(ref() is not None for ref in refs), 'live payload was released'
    if mode == 'waiting_cancel':
        scheduler.finish_requests(rid, RequestStatus.FINISHED_ABORTED)
    elif mode == 'running_cancel':
        step(scheduler, 17)
        scheduler.finish_requests(rid, RequestStatus.FINISHED_ABORTED)
    elif mode == 'stream_queued_end':
        step(scheduler, 17)
        end, data = make_request(rid, caching=False, media=False)
        scheduler.add_request(end)
        del end, data
        step(scheduler)
    elif mode == 'stream_resume':
        step(scheduler)
        assert all(ref() is not None for ref in refs), 'waiting stream lost data'
        update, data = make_request(rid, tokens=[21, 22, 23, 24],
                                   resumable=True, caching=False, media=False)
        scheduler.add_request(update)
        del update, data
        assert all(ref() is not None for ref in refs), 'continuation lost data'
        step(scheduler)
        end, data = make_request(rid, caching=False, media=False)
        scheduler.add_request(end)
        del end, data
    else:
        step(scheduler)
    assert all(ref() is None for ref in refs), f'{mode}: completed objects retained'
    assert not scheduler.has_unfinished_requests(), f'{mode}: unfinished bookkeeping'


def cached_hits(manager, request):
    return manager.get_computed_blocks(request)[1]


def cache_cases():
    for stage in ('initial', 'append', 'stream'):
        scheduler = make_scheduler()
        tokens = [rng.randrange(50, 10000) for _ in range(8)]
        request, data = make_request('seed-' + stage, tokens=tokens,
                                     resumable=stage == 'stream')
        if stage == 'initial':
            request, data = make_request('initial', tokens=tokens + [31, 32, 33, 34])
        elif stage == 'append':
            request.append_output_token_ids([31, 32, 33, 34])
        else:
            scheduler.add_request(request)
            for token in (31, 32, 33, 0):
                step(scheduler, token)
            update, _ = make_request(request.request_id, tokens=[41, 42, 43, 44],
                                     resumable=True, caching=False, media=False)
            scheduler.add_request(update)
            # The old uncomputed EOS must not survive continuation.
            assert list(request.all_token_ids) == tokens + [31, 32, 33, 41, 42, 43, 44]
        # Fresh real manager avoids scheduler allocation history affecting lookup.
        manager = make_scheduler().kv_cache_manager
        assert manager.allocate_slots(request, num_new_tokens=request.num_tokens) is not None
        manager.cache_blocks(request, request.num_tokens)
        manager.free(request)
        full = list(request.all_token_ids)
        same, _ = make_request('same', tokens=full)
        expected = ((len(full) - 1) // 4) * 4
        assert cached_hits(manager, same) == expected, f'{stage}: same prefix not reused'
        changed = full.copy()
        changed[0] += 10001
        other, _ = make_request('different', tokens=changed)
        assert cached_hits(manager, other) == 0, f'{stage}: different tokens reused'
        media, _ = make_request('media', tokens=full, image='image-B')
        assert cached_hits(manager, media) == 0, f'{stage}: different media reused'
        if stage == 'stream':
            changed = full.copy()
            changed[11] = 0
            other, _ = make_request('edge', tokens=changed)
            assert cached_hits(manager, other) == 8, 'stream: stale final block reused'


def checkpoint(phase):
    print('CHECKPOINT=' + phase, flush=True)
    assert sys.stdin.readline().strip() == 'continue', 'parent did not acknowledge'


def memory_rounds():
    scheduler = make_scheduler()
    checkpoint('baseline')
    for round_id in range(4):
        refs = []
        ids = []
        for index in range(12):
            request, payload = make_request(f'memory-{round_id}-{index}',
                size=4 * 1024 * 1024, image=f'media-{round_id}-{index}')
            refs.append((weakref.ref(request), weakref.ref(payload)))
            ids.append(request.request_id)
            scheduler.add_request(request)
            del request, payload
        assert all(a() is not None and b() is not None for a, b in refs)
        checkpoint(f'live-{round_id}')
        step(scheduler)
        assert all(a() is None and b() is None for a, b in refs), 'batch retained'
        checkpoint(f'released-{round_id}')


def main():
    # Initialize lazy components before disabling automatic GC and monitoring.
    make_scheduler()
    gc.collect()
    gc.disable()
    collections = []
    def on_gc(phase, info):
        if phase == 'start':
            collections.append(info['generation'])
    gc.callbacks.append(on_gc)
    try:
        for mode in ('normal', 'waiting_cancel', 'running_cancel',
                     'stream_queued_end', 'stream_resume'):
            lifecycle(mode)
            assert not collections, f'GC ran during {mode} lifecycle'
        lifecycle('normal', caching=False)
        cache_cases()
        memory_rounds()
        assert not collections, 'GC ran during target lifecycle'
        print('BEHAVIOR_COMPLETE', flush=True)
    finally:
        gc.callbacks.remove(on_gc)
        gc.enable()

if __name__ == '__main__':
    main()
