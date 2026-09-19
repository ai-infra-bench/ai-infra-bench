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
    pair = runtime.pair(spec, chunk=1, processor=processor)
    try:
        return {'scheduler': [int(pair.scheduler.max_num_encoder_input_tokens),
                              int(pair.scheduler.encoder_cache_manager.cache_size)],
                'runner': int(pair.runner.mm_budget.get_encoder_budget())}
    finally:
        pair.close()


def check_capacity(runtime):
    specs = [specification(100, [5, 15, 25, 35, 45, 55, 65, 75]),
             specification(41, [2, 11, 29, 38]), specification(9, None),
             specification(12, []), specification(0, []), specification(0, None)]
    result = []
    for spec in specs:
        actual = capacity_for(runtime, spec)
        count = len(spec['rows'])
        allowed = (count,) if count else (0, 1)
        assert all(value in allowed for value in actual['scheduler']), actual
        assert actual['runner'] == min(actual['scheduler']), actual
        result.append(actual)
    videos = []
    for count in (16, 48):
        spec, processor = video_processor(runtime, count, frames=2, prefix=11)
        actual = capacity_for(runtime, spec, processor)
        assert actual == {'scheduler': [count, count], 'runner': count}, actual
        videos.append(actual)
    return {'dummy': result, 'video': videos}
