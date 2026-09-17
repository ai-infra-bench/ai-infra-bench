def observe_encoder_capacity(position):
    """Measure real scheduler and runner capacity consumers for a media item.

    Only the media input producer and processor-cache factory are controlled.
    Registry defaults and internal embedding-count accessors are unrestricted.
    """
    from vllm.config import SchedulerConfig
    from vllm.v1.core.encoder_cache_manager import compute_encoder_budget
    from vllm.v1.worker.utils import MultiModalBudget
    import vllm.v1.worker.utils as worker_utils

    processor = SimpleNamespace(
        info=SimpleNamespace(get_mm_max_tokens_per_item=lambda **kwargs: None),
        allowed_mm_limits={"image": 4},
    )
    registry = object.__new__(MultiModalRegistry)
    registry.create_processor = lambda *args, **kwargs: processor
    registry.supports_multimodal_inputs = lambda model: True
    model = SimpleNamespace(is_multimodal_model=True, max_model_len=4096)
    # The real constructor derives both encoder capacity floors from the
    # decoder batch limit. A one-token batch makes row accounting observable
    # while retaining a configuration the production constructor can create.
    config = SchedulerConfig(
        max_model_len=4096, is_encoder_decoder=False,
        max_num_batched_tokens=1, max_num_seqs=1,
        enable_chunked_prefill=True, is_multimodal_model=True,
        disable_chunked_mm_input=False,
    )
    original_inputs = MultiModalProfiler._get_dummy_mm_inputs
    original_cache = worker_utils.processor_only_cache_from_config
    try:
        MultiModalProfiler._get_dummy_mm_inputs = lambda *args, **kwargs: {
            "mm_placeholders": {"image": [position]}}
        worker_utils.processor_only_cache_from_config = lambda *args, **kwargs: None
        scheduler = compute_encoder_budget(model, config, registry)
        runner = MultiModalBudget(model, config, registry).get_encoder_budget()
        return {"scheduler": list(scheduler), "runner": runner}
    finally:
        MultiModalProfiler._get_dummy_mm_inputs = original_inputs
        worker_utils.processor_only_cache_from_config = original_cache


def observe_direct_encoder_capacity():
    """Exercise the model-provided estimate path as well as dummy profiling.

    Vision geometry/model execution is controlled; Qwen3-VL's production
    estimation method, inherited modality mapping, profiler, registry and both
    budget consumers remain real. Text wrappers around video features must not
    inflate the encoder-row estimate. No accessors introduced by an answer are
    required.
    """
    from vllm.config import SchedulerConfig
    from vllm.model_executor.models.qwen3_vl import Qwen3VLProcessingInfo
    from vllm.v1.core.encoder_cache_manager import compute_encoder_budget
    from vllm.v1.worker.utils import MultiModalBudget
    import vllm.v1.worker.utils as worker_utils

    observed=[]
    for rows in (16,48):
        info=object.__new__(Qwen3VLProcessingInfo)
        info.get_image_size_with_most_features=lambda: (rows * 7,112)
        info.get_max_image_tokens=lambda: rows
        info.get_num_frames_with_most_features=lambda *args,**kwargs: 2
        info.get_num_video_tokens=lambda *args,**kwargs: rows
        processor=SimpleNamespace(info=info,allowed_mm_limits={"video":4})
        registry=object.__new__(MultiModalRegistry)
        registry.create_processor=lambda *args,**kwargs: processor
        registry.supports_multimodal_inputs=lambda model: True
        model=SimpleNamespace(is_multimodal_model=True,max_model_len=4096)
        config=SchedulerConfig(max_model_len=4096,is_encoder_decoder=False,
            max_num_batched_tokens=1,max_num_seqs=1,enable_chunked_prefill=True,
            is_multimodal_model=True,disable_chunked_mm_input=False)
        original_cache=worker_utils.processor_only_cache_from_config
        try:
            worker_utils.processor_only_cache_from_config=lambda *args,**kwargs: None
            observed.append({"scheduler":list(compute_encoder_budget(model,config,registry)),
                "runner":MultiModalBudget(model,config,registry).get_encoder_budget()})
        finally:
            worker_utils.processor_only_cache_from_config=original_cache
    return observed
