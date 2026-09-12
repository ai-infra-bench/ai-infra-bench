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
