import hashlib
import json

import pytest
from vllm.v1.kv_offload.base import make_offload_key
from vllm.v1.kv_offload.file_mapper import FileMapper


def _mapper(
    *,
    root_dir="/tmp/persistent-kv",
    parallel_agnostic,
    model_name="layout-compatible-model",
    dtype="float16",
    tokens_per_hash=16,
    blocks_per_file=1,
    groups=None,
    tp_size=1,
    pp_size=1,
    pcp_size=1,
    dcp_size=1,
    rank=0,
):
    if groups is None:
        groups = [{"tokens_per_block": 16, "layer_names": ["layer0"]}]
    return FileMapper(
        root_dir=root_dir,
        model_name=model_name,
        tokens_per_hash=tokens_per_hash,
        blocks_per_file=blocks_per_file,
        tp_size=tp_size,
        pp_size=pp_size,
        pcp_size=pcp_size,
        dcp_size=dcp_size,
        rank=rank,
        dtype=dtype,
        kv_cache_groups=groups,
        parallel_agnostic=parallel_agnostic,
    )


@pytest.mark.parametrize(
    "case",
    [
        {},
        {"dtype": "bfloat16"},
        {"tokens_per_hash": 32, "blocks_per_file": 4},
        {
            "groups": [
                {"tokens_per_block": 16, "layer_names": ["layer0", "layer1"]}
            ]
        },
    ],
    ids=["default", "bf16", "larger-files", "two-layers"],
)
def test_incompatible_layout_classification_separates_namespace(case):
    portable = _mapper(parallel_agnostic=True, **case)
    layout_specific = _mapper(parallel_agnostic=False, **case)

    assert portable.base_path != layout_specific.base_path
    assert portable.get_config_file_path() != layout_specific.get_config_file_path()


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
def test_portable_layouts_still_share_across_parallel_configs(parallel):
    single_rank = _mapper(parallel_agnostic=True)
    distributed = _mapper(parallel_agnostic=True, **parallel)

    assert single_rank.base_path == distributed.base_path
    assert single_rank.rank == distributed.rank == 0


@pytest.mark.parametrize(
    "parallel",
    [
        {"tp_size": 2, "rank": 1},
        {"pp_size": 2, "rank": 1},
        {"pcp_size": 2, "dcp_size": 2, "rank": 3},
    ],
    ids=["tp", "pp", "context-parallel"],
)
def test_layout_specific_parallel_configs_remain_distinct(parallel):
    single_rank = _mapper(parallel_agnostic=False)
    distributed = _mapper(parallel_agnostic=False, **parallel)

    assert single_rank.base_path != distributed.base_path


def test_equivalent_layout_specific_runs_are_deterministic():
    first = _mapper(parallel_agnostic=False)
    second = _mapper(parallel_agnostic=False)

    assert first.base_path == second.base_path
    assert first.get_config_file_path() == second.get_config_file_path()


def test_incompatible_layouts_cannot_name_the_same_block_file():
    key = make_offload_key(bytes(range(16)), 0)
    portable = _mapper(parallel_agnostic=True)
    layout_specific = _mapper(parallel_agnostic=False)

    assert portable.get_file_name(key) != layout_specific.get_file_name(key)


def test_model_and_layout_identity_compose_without_collisions():
    portable_a = _mapper(parallel_agnostic=True, model_name="org/model-a")
    specific_a = _mapper(parallel_agnostic=False, model_name="org/model-a")
    portable_b = _mapper(parallel_agnostic=True, model_name="org/model-b")
    specific_b = _mapper(parallel_agnostic=False, model_name="org/model-b")

    assert len(
        {
            portable_a.base_path,
            specific_a.base_path,
            portable_b.base_path,
            specific_b.base_path,
        }
    ) == 4


def test_portable_layout_keeps_legacy_persistent_namespace():
    mapper = _mapper(parallel_agnostic=True)
    legacy_fields = {
        "model_name": "layout-compatible-model",
        "tokens_per_hash": 16,
        "blocks_per_file": 1,
        "tp_size": 1,
        "pp_size": 1,
        "pcp_size": 1,
        "dcp_size": 1,
        "dtype": "float16",
        "kv_cache_groups": [
            {"tokens_per_block": 16, "layer_names": ["layer0"]}
        ],
        "inference_engine": "vllm",
    }
    canonical = json.dumps(legacy_fields, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:12]

    assert mapper.base_path == f"/tmp/persistent-kv/layout-compatible-model_{digest}"
