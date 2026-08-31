from __future__ import annotations

import pytest

from verifier_support import (
    DEFAULT_CASE,
    LAYOUT_CASES,
    LayoutCase,
    incompatible_layout_lifecycle,
    layout_specific_parallel_miss,
    legacy_portable_read,
    portable_cross_parallel_lifecycle,
)


@pytest.mark.parametrize("case", LAYOUT_CASES, ids=lambda case: case.name)
def test_incompatible_layouts_do_not_reuse_persistent_blocks(tmp_path, case):
    incompatible_layout_lifecycle(str(tmp_path), case)


@pytest.mark.parametrize(
    "parallel",
    [
        {"tp_size": 2, "rank": 1},
        {"pp_size": 3, "rank": 2},
        {"pcp_size": 2, "rank": 1},
        {"dcp_size": 4, "rank": 3},
    ],
    ids=["tp", "pp", "pcp", "dcp"],
)
def test_portable_layouts_reopen_and_load_across_parallel_configs(
    tmp_path, parallel
):
    portable_cross_parallel_lifecycle(str(tmp_path), DEFAULT_CASE, parallel)


@pytest.mark.parametrize(
    "parallel",
    [
        {"tp_size": 2, "rank": 1},
        {"pp_size": 2, "rank": 1},
        {"pcp_size": 2, "dcp_size": 2, "rank": 3},
    ],
    ids=["tp", "pp", "context-parallel"],
)
def test_layout_specific_parallel_configs_do_not_reuse_files(tmp_path, parallel):
    layout_specific_parallel_miss(str(tmp_path), DEFAULT_CASE, parallel)


def test_equivalent_layout_specific_restarts_roundtrip_data(tmp_path):
    incompatible_layout_lifecycle(str(tmp_path), DEFAULT_CASE)


def test_model_identity_remains_part_of_persistent_compatibility(tmp_path):
    writer = LayoutCase("model-a", model_name="org/model-a")
    reader = LayoutCase("model-b", model_name="org/model-b")
    # A portable artifact from model A must not be visible to model B.
    from verifier_support import aligned_tensor, key, lookup, make_spec, tier, write_blocks
    from vllm.v1.kv_offload.base import LookupResult

    item = key(81)
    tensor = aligned_tensor(2)
    manager = tier(str(tmp_path), tensor, make_spec(writer, portable=True))
    write_blocks(manager, tensor, [item], [61])
    manager.shutdown()
    reader_tensor = aligned_tensor(2)
    reader_manager = tier(
        str(tmp_path), reader_tensor, make_spec(reader, portable=True)
    )
    try:
        assert lookup(reader_manager, [item]) == [LookupResult.MISS]
    finally:
        reader_manager.shutdown()


def test_portable_layout_reads_preexisting_legacy_artifact(tmp_path):
    legacy_portable_read(str(tmp_path), DEFAULT_CASE)


def test_multi_key_larger_file_configuration_survives_restart(tmp_path):
    incompatible_layout_lifecycle(str(tmp_path), LAYOUT_CASES[2])
