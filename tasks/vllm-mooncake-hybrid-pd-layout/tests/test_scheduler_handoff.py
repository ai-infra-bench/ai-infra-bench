# SPDX-License-Identifier: Apache-2.0
import pytest

from scheduler_handoff import run_scheduler_handoff


@pytest.mark.parametrize(
    "num_tokens,prompt_kind,logical_block_size,physical_ratio,warm",
    [
        (51, "token_ids", 16, 1, False),
        (2, "token_ids", 16, 1, False),
        (2, "prompt_embeddings", 16, 1, False),
        (19, "token_ids", 18, 3, True),
        (35, "prompt_embeddings", 16, 4, False),
    ],
    ids=["cold-token-ids", "two-token-ids", "two-embeddings", "warm-ratio-three", "embedding-ratio-four"],
)
def test_real_scheduler_worker_handoff(
    num_tokens, prompt_kind, logical_block_size, physical_ratio, warm
):
    run_scheduler_handoff(num_tokens=num_tokens, prompt_kind=prompt_kind,
                          logical_block_size=logical_block_size,
                          physical_ratio=physical_ratio, warm=warm)
