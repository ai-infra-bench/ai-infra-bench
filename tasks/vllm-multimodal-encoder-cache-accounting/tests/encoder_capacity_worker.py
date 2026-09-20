"""Real constructor consumers and model-provided analytical video estimates."""
from vllm.model_executor.models.qwen3_vl import Qwen3VLProcessingInfo
from vllm.multimodal.processing import InputProcessingContext
from transformers import Qwen2VLImageProcessorFast, Qwen3VLVideoProcessor


def video_processor(runtime, count, frames, prefix):
    per_frame = count // frames
    width, height = per_frame * 7, 112
    indices = [i for frame in range(frames)
               for i in range(frame * (per_frame + prefix + 1) + prefix,
                              frame * (per_frame + prefix + 1) + prefix + per_frame)]
    spec = specification(count + frames * (prefix + 1), indices)
    spec['modality'] = 'video'
    processor = MediaProcessor(spec)
    info = Qwen3VLProcessingInfo(InputProcessingContext(runtime.video_config, None))
    sizes = {'shortest_edge': 28 * 28, 'longest_edge': width * height * frames}
    image = Qwen2VLImageProcessorFast(size=sizes, patch_size=14, merge_size=2,
                                     temporal_patch_size=1)
    video = Qwen3VLVideoProcessor(size=sizes, patch_size=14, merge_size=2,
                                 temporal_patch_size=1)
    info.get_hf_processor = lambda **kwargs: SimpleNamespace(image_processor=image, video_processor=video)
    info.get_image_size_with_most_features = lambda: (width, height)
    info.get_num_frames_with_most_features = lambda *args, **kwargs: frames
    # Run the real vision geometry calculation, including resizing and temporal
    # grouping. Neither the count nor the video estimate is replaced by a lambda.
    actual_rows = info.get_num_video_tokens(image_width=width, image_height=height,
        num_frames=frames, image_processor=None)
    assert actual_rows == count, (actual_rows, count)
    processor.info = info
    return spec, processor


def capacity_for(runtime, spec, processor=None):
    """Exercise a full-item budget without reading candidate budget containers.

    The two-token batch allows a token from each request. Both items have the
    declared maximal encoder output; one fills the configured encoder capacity.
    The second remains pending while the first still needs its cached rows.
    Dummy profiling is observed at the external encoder input/output boundary.
    """
    count = len(spec['rows'])
    pair = runtime.pair(spec, chunk=2, max_seqs=2, per_request=1,
                        processor=processor)
    try:
        if count:
            for index in range(2):
                item = specification(count, None, value=301 + 100 * index)
                item['modality'] = spec.get('modality', 'image')
                pair.add(request_workload(f'capacity-{index}', count + 1, [item]))
            first = pair.step()
            admitted_rows = sum(len(item) for item in first['encoded'])
            assert admitted_rows == count, ('whole-item capacity',
                {'expected_rows': count, 'observed_rows': admitted_rows,
                 'scheduled': first['counts']})
            second = pair.step()
            assert not second['encoded'], ('live item must retain its capacity',
                {'extra_rows': sum(len(item) for item in second['encoded']),
                 'scheduled': second['counts']})
            pair.finish()
            assert len(pair.model.encodings) == 2, 'whole-item output was not reused'
        else:
            pair.add(request_workload('zero-capacity', max(2, spec['length']), [spec]))
            pair.finish()
            assert not pair.model.encodings, 'zero-output input invoked the encoder'
    finally:
        pair.close()
    if not count:
        # Zero-output planning is checked by successful real request execution
        # without encoder work. It does not prescribe a zero-versus-one floor,
        # or introduce a new zero-item model profiling path in this repair.
        return {'admitted_rows': 0, 'live_capacity_preserved': True,
                'profile_encoder_rows': None}
    pair = runtime.pair(spec, chunk=2, max_seqs=2, per_request=1,
                        processor=processor)
    batches = []
    try:
        pair.model.on_encode = lambda outputs: batches.append(sum(len(item) for item in outputs))
        try:
            pair.runner.profile_run()
        except ModelInputObserved:
            pass
        else:
            raise AssertionError('profiling did not reach the decoder input boundary')
        largest = max(batches, default=0)
        assert largest == count, ('profile encoder rows', count, batches)
        return {'admitted_rows': count, 'live_capacity_preserved': True,
                'profile_encoder_rows': largest}
    finally:
        pair.close()


def check_capacity(runtime):
    specs = [specification(100, [5, 15, 25, 35, 45, 55, 65, 75]),
             specification(41, [2, 11, 29, 38]), specification(9, None),
             specification(12, []), specification(0, []), specification(0, None)]
    result = []
    for spec in specs:
        result.append(capacity_for(runtime, spec))
    videos = []
    for count in (16, 48):
        spec, processor = video_processor(runtime, count, frames=2, prefix=11)
        videos.append(capacity_for(runtime, spec, processor))
    return {'dummy': result, 'video': videos}
