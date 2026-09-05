# SPDX-License-Identifier: Apache-2.0
import pytest

from padded_state_transfer import run_padded_state_transfer


@pytest.mark.parametrize("physical_ratio", [1, 4], ids=["logical-pages", "physical-blocks"])
def test_padded_gdn_preserves_payload_and_unrequested_pages(physical_ratio):
    run_padded_state_transfer(physical_ratio)
