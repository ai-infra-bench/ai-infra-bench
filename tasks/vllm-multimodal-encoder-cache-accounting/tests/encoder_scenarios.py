"""Behavioral cases composed through public scheduler/runner entrypoints."""
import time
import traceback
from vllm.v1.core.encoder_cache_manager import EncoderCacheManager


def specification(length, indices, count=None, offset=0, value=100):
    size = length if indices is None else len(indices)
    if count is not None:
        size = count
    return dict(offset=offset, length=length, indices=indices,
                rows=[[float(value + i + j) for j in range(WIDTH)] for i in range(size)])


def request_workload(rid, length, specs, token=17):
    tokens = [token] * length
    for spec in specs:
        chosen = range(spec['length']) if spec['indices'] is None else spec['indices']
        for p in chosen:
            tokens[spec['offset'] + p] = MEDIA_TOKEN
    return dict(id=rid, tokens=tokens, features=specs)


def allocator_request(rid, spec):
    position, data = media_item(spec)
    workload = request_workload(rid, max(1, spec['offset'] + spec['length']), [spec])
    return Request(request_id=rid, prompt_token_ids=workload['tokens'],
        sampling_params=SamplingParams(max_tokens=1), pooling_params=None,
        eos_token_id=None, mm_features=[MultiModalFeatureSpec(data=data,
            modality='image', identifier=rid + '-item', mm_position=position)])


def check_allocator():
    cases = [(0, []), (0, None), (5, None), (5, list(range(5))),
             (5, []), (5, [1, 3, 4]), (100, [5, 15, 25, 35, 45, 55, 65, 75]),
             (64, [0, 63])]
    verified = []
    for i, (length, indices) in enumerate(cases):
        spec = specification(length, indices)
        count = len(spec['rows'])
        req = allocator_request(f'allocator-{i}', spec)
        manager = EncoderCacheManager(count)
        assert manager.can_allocate(req, 0, count, 0), (length, count)
        manager.allocate(req, 0)
        verified.append(count)
        extra = allocator_request(f'extra-{i}', specification(1, None))
        assert not manager.can_allocate(extra, 0, 1, 0), 'exact-fit item did not consume its capacity'
        if count:
            assert not EncoderCacheManager(count - 1).can_allocate(req, 0, count, 0)
            assert not EncoderCacheManager(count).can_allocate(req, 0, count - 1, 0)
        manager.free(req)
        other = allocator_request(f'next-{i}', spec)
        assert manager.can_allocate(other, 0, count, 0)
        manager.allocate(other, 0)
        assert not manager.can_allocate(extra, 0, 1, 0), 'reallocated item did not consume its capacity'
    return verified


def check_pressure(runtime):
    profile = specification(16, list(range(8)))
    first = specification(8, None, value=100)
    second = specification(12, [5, 10], value=200)
    pair = runtime.pair(profile, chunk=4, max_seqs=4, per_request=1)
    try:
        pair.add(request_workload('holder', 8, [first], 19))
        pair.add(request_workload('waiting', 12, [second], 29))
        initial = pair.step()
        assert initial['counts'].get('waiting', 0) > 0, initial
        assert initial['encoded'] == [first['rows']], initial
        pair.finish()
        assert len(pair.model.encodings) == 2, 'cached item was recomputed'
        # Normal completion must leave request admission and eviction usable.
        fresh = specification(6, [1, 4], value=300)
        pair.add(request_workload('after-drain', 6, [fresh], 39))
        pair.finish()
        assert pair.scheduler.get_num_unfinished_requests() == 0
        assert len(pair.model.encodings) == 3
        return {'zero_resource_progress': True, 'reuse_and_eviction': True,
                'fresh_admission': True}
    finally:
        pair.close()


def check_whole_reservation(runtime):
    pair = runtime.pair(specification(16, list(range(8))), chunk=6)
    first = specification(5, [0, 1, 2, 3], value=100)
    second = specification(5, None, offset=5, value=200)
    try:
        pair.add(request_workload('whole', 10, [first, second]))
        initial = pair.step()
        assert 0 < initial['counts']['whole'] <= 5, initial
        assert initial['encoded'] == [first['rows']], initial
        pair.finish()
        assert len(pair.model.encodings) == 2
        return {'full_item_reserved': True}
    finally:
        pair.close()


def run_fresh(runtime, inputs, eagle=False):
    profile = specification(64, list(range(8)))
    pair = runtime.pair(profile, chunk=7, max_seqs=3, per_request=2, eagle=eagle)
    try:
        for request in inputs['requests']:
            pair.add(request)
        pair.finish()
        return pair.delivered, pair.draft_delivered
    finally:
        pair.close()


def check_text_and_empty(runtime):
    profile = specification(16, list(range(8)))
    pair = runtime.pair(profile, chunk=3, max_seqs=3, per_request=1)
    try:
        pair.add(request_workload('text', 7, [], 71))
        pair.add(request_workload('empty', 8,
            [specification(0, None, offset=1), specification(4, [], offset=2),
             specification(0, [], offset=7)], 81))
        pair.finish()
        assert not pair.model.encodings, 'empty placeholders invoked the encoder'
        return {'text_and_empty_advance': True}
    finally:
        pair.close()


def run_checks(inputs):
    stages, failures, timings, observations = {}, {}, {}, {}
    def check(name, operation):
        started = time.monotonic()
        try:
            stages[name] = operation()
        except Exception as exc:
            failures[name] = {'type': type(exc).__name__, 'message': str(exc),
                              'traceback': traceback.format_exc()}
        finally:
            timings[name] = round(time.monotonic() - started, 4)
    check('allocator', check_allocator)
    with Runtime() as runtime:
        check('capacity', lambda: check_capacity(runtime))
        check('resource_progress', lambda: check_pressure(runtime))
        check('whole_reservation', lambda: check_whole_reservation(runtime))
        check('text_and_empty', lambda: check_text_and_empty(runtime))
        check('storage', lambda: check_storage(runtime))
        check('storage_lifecycle', lambda: check_storage_lifecycle(runtime))
        def main_inputs():
            main, _ = run_fresh(runtime, inputs)
            observations['main'] = main
            return {'model_inputs_checked': True}
        def eagle_inputs():
            main, draft = run_fresh(runtime, inputs, eagle=True)
            observations['eagle_main'] = main
            observations['eagle_shifted'] = draft
            return {'model_inputs_checked': True}
        check('main_inputs', main_inputs)
        check('eagle_inputs', eagle_inputs)
    check('host_storage', check_host_storage)
    return {'stages': stages, 'failures': failures, 'timings': timings,
            'observations': observations}
