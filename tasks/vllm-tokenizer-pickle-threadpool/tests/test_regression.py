from __future__ import annotations

import pickle

from vllm.tokenizers.hf import maybe_make_thread_pool

from tokenizer_fixture import (
    cloudpickle_roundtrip,
    make_tokenizer,
    concurrent_encodes,
    pickle_roundtrip,
    pooled,
    spawn_roundtrip,
)


def test_pickle_roundtrip_returns_tokenizer_not_none() -> None:
    assert pickle_roundtrip(pooled()) is not None


def test_pickle_roundtrip_preserves_encoding() -> None:
    original = pooled()
    restored = pickle_roundtrip(original)
    assert restored.encode("hello world") == original.encode("hello world") == [2, 3]


def test_pickle_roundtrip_preserves_decoding() -> None:
    restored = pickle_roundtrip(pooled())
    assert restored.decode([2, 3]) == "hello world"


def test_restored_tokenizer_handles_concurrent_calls() -> None:
    restored = pickle_roundtrip(pooled(copies=2))
    assert concurrent_encodes(restored) == [[2, 3], [4, 5]]


def test_spawned_process_receives_usable_tokenizer() -> None:
    observed = spawn_roundtrip(pooled())
    assert observed == {"is_none": False, "ids": [2, 3]}


def test_cloudpickle_roundtrip_is_usable() -> None:
    restored = cloudpickle_roundtrip(pooled())
    assert restored is not None
    assert restored.encode("杭州 weather") == [4, 5]


def test_multiple_pickle_protocols_are_supported() -> None:
    observations = []
    for protocol in (4, pickle.HIGHEST_PROTOCOL):
        restored = pickle_roundtrip(pooled(), protocol)
        observations.append(restored.encode("hello world") if restored else None)
    assert observations == [[2, 3], [2, 3]]


def test_non_default_pool_configuration_is_usable_after_roundtrip() -> None:
    restored = pickle_roundtrip(pooled(copies=3))
    assert restored is not None
    assert restored(["hello", "world"])["input_ids"] == [[2], [3]]


def test_repeated_wrapping_is_idempotent() -> None:
    tokenizer = pooled()
    original_type = type(tokenizer)
    assert maybe_make_thread_pool(tokenizer) is tokenizer
    assert type(tokenizer) is original_type


def test_non_fast_object_keeps_existing_behavior() -> None:
    marker = object()
    assert maybe_make_thread_pool(marker) is marker
