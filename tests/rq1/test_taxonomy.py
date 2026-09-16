import pytest

from ai_infra_bench.rq1.taxonomy import Classification


def valid_value() -> dict:
    return {
        "source_id": "vllm__pr__123",
        "subsystems": ["kernels_operators", "memory_kv_cache"],
        "accelerator_scope": "specific",
        "accelerators": ["amd_rocm"],
        "subsystem_confidence": "high",
        "accelerator_confidence": "high",
        "rationale": "The title and kernel path explicitly identify the scope.",
        "evidence": ["csrc/rocm/attention.cu"],
    }


def test_classification_normalizes_controlled_multilabels() -> None:
    result = Classification.from_dict(valid_value())

    assert result.subsystems == ("kernels_operators", "memory_kv_cache")
    assert result.accelerators == ("amd_rocm",)


def test_agnostic_classification_rejects_named_accelerator() -> None:
    value = valid_value()
    value["accelerator_scope"] = "agnostic"

    with pytest.raises(ValueError, match="agnostic"):
        Classification.from_dict(value)


def test_agnostic_classification_accepts_empty_accelerator_list() -> None:
    value = valid_value()
    value["accelerator_scope"] = "agnostic"
    value["accelerators"] = []

    result = Classification.from_dict(value)

    assert result.accelerators == ()


def test_unknown_label_is_rejected() -> None:
    value = valid_value()
    value["subsystems"] = ["quantization"]

    with pytest.raises(ValueError, match="unsupported"):
        Classification.from_dict(value)
