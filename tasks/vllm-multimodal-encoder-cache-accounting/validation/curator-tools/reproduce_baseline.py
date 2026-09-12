from __future__ import annotations

import json

import torch

from vllm.multimodal.inputs import MultiModalFeatureSpec, PlaceholderRange
from vllm.v1.core.encoder_cache_manager import EncoderCacheManager
from vllm.v1.request import Request


P = 100
E = 8


class SparseRequest(Request):
    """Minimal production Request shape without prescribing its count API."""

    request_id = "sparse-placeholder"
    has_encoder_inputs = True

    def __init__(self) -> None:
        mask = torch.tensor([False] * (P - E) + [True] * E)
        self.mm_features = [
            MultiModalFeatureSpec(
                data=None,
                modality="image",
                identifier="sparse-item",
                mm_position=PlaceholderRange(0, P, mask),
            )
        ]

request = SparseRequest()
manager = EncoderCacheManager(cache_size=E)
can_allocate = manager.can_allocate(
    request,
    input_id=0,
    encoder_compute_budget=E,
    num_tokens_to_schedule=0,
)

evidence = {
    "placeholder_positions_P": P,
    "embedding_rows_E": E,
    "cache_capacity": E,
    "can_allocate": can_allocate,
    "expected_fixed_semantics": True,
    "baseline_bug_reproduced": can_allocate is False,
}
print(json.dumps(evidence, sort_keys=True))
assert can_allocate is False, "base unexpectedly accounts cache capacity in E units"
