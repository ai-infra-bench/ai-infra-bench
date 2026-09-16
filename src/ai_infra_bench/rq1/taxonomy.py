"""Controlled labels used by the RQ1 semantic classifier."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TAXONOMY_VERSION = "rq1-subsystem-accelerator-2026-08-13"

SUBSYSTEMS = frozenset(
    {
        "models",
        "scheduling",
        "memory_kv_cache",
        "distributed_serving",
        "kernels_operators",
        "frontend_api",
        "hardware_backends",
        "other",
        "unknown",
    }
)

ACCELERATORS = frozenset(
    {
        "cpu",
        "nvidia_cuda",
        "amd_rocm",
        "intel_xpu",
        "ascend_npu",
        "cambricon_mlu",
    }
)

ACCELERATOR_SCOPES = frozenset(
    {"agnostic", "specific", "cross_backend", "unknown"}
)

CONFIDENCE_LEVELS = frozenset({"low", "medium", "high"})


@dataclass(frozen=True)
class Classification:
    """Validated semantic labels for one pull request."""

    source_id: str
    subsystems: tuple[str, ...]
    accelerator_scope: str
    accelerators: tuple[str, ...]
    subsystem_confidence: str
    accelerator_confidence: str
    rationale: str
    evidence: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Classification:
        """Validate and normalize one model-produced classification."""
        source_id = _required_string(value, "source_id")
        subsystems = _string_list(value, "subsystems")
        accelerators = _string_list(value, "accelerators", allow_empty=True)
        accelerator_scope = _required_string(value, "accelerator_scope")
        subsystem_confidence = _required_string(
            value, "subsystem_confidence"
        )
        accelerator_confidence = _required_string(
            value, "accelerator_confidence"
        )
        rationale = _required_string(value, "rationale")
        evidence = _string_list(value, "evidence", allow_empty=True)

        _require_controlled("subsystems", subsystems, SUBSYSTEMS)
        _require_controlled("accelerators", accelerators, ACCELERATORS)
        _require_controlled(
            "accelerator_scope", [accelerator_scope], ACCELERATOR_SCOPES
        )
        _require_controlled(
            "subsystem_confidence",
            [subsystem_confidence],
            CONFIDENCE_LEVELS,
        )
        _require_controlled(
            "accelerator_confidence",
            [accelerator_confidence],
            CONFIDENCE_LEVELS,
        )

        if len(subsystems) != len(set(subsystems)):
            raise ValueError("subsystems contains duplicates")
        if len(accelerators) != len(set(accelerators)):
            raise ValueError("accelerators contains duplicates")
        if accelerator_scope == "agnostic" and accelerators:
            raise ValueError("agnostic classifications cannot name accelerators")

        return cls(
            source_id=source_id,
            subsystems=tuple(sorted(subsystems)),
            accelerator_scope=accelerator_scope,
            accelerators=tuple(sorted(accelerators)),
            subsystem_confidence=subsystem_confidence,
            accelerator_confidence=accelerator_confidence,
            rationale=rationale,
            evidence=tuple(evidence),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "source_id": self.source_id,
            "subsystems": list(self.subsystems),
            "accelerator_scope": self.accelerator_scope,
            "accelerators": list(self.accelerators),
            "subsystem_confidence": self.subsystem_confidence,
            "accelerator_confidence": self.accelerator_confidence,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
        }


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return result.strip()


def _string_list(
    value: dict[str, Any], key: str, *, allow_empty: bool = False
) -> list[str]:
    result = value.get(key)
    if not isinstance(result, list) or not all(
        isinstance(item, str) and item.strip() for item in result
    ):
        raise ValueError(f"{key} must be a list of non-empty strings")
    if not result and not allow_empty:
        raise ValueError(f"{key} cannot be empty")
    return [item.strip() for item in result]


def _require_controlled(
    field: str, values: list[str], allowed: frozenset[str]
) -> None:
    unexpected = sorted(set(values) - allowed)
    if unexpected:
        raise ValueError(f"{field} has unsupported values: {unexpected}")
