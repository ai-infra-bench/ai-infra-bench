from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class RequestEnvelope:
    request_id: str
    tenant: str
    prompt: str
    requested_output_tokens: int
    priority: int = 0
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: dict[str, Any], line_number: int) -> "RequestEnvelope":
        request_id = str(data.get("request_id", "")).strip()
        tenant = str(data.get("tenant", "")).strip()
        prompt = str(data.get("prompt", ""))
        requested_output_tokens = int(data.get("requested_output_tokens", 0))
        priority = int(data.get("priority", 0))
        metadata = {str(key): str(value) for key, value in dict(data.get("metadata", {})).items()}
        if not request_id:
            raise ValueError(f"line {line_number}: request_id is required")
        if not tenant:
            raise ValueError(f"line {line_number}: tenant is required")
        if not prompt.strip():
            raise ValueError(f"line {line_number}: prompt is required")
        if requested_output_tokens < 1:
            raise ValueError(f"line {line_number}: requested_output_tokens must be positive")
        return cls(
            request_id=request_id,
            tenant=tenant,
            prompt=prompt,
            requested_output_tokens=requested_output_tokens,
            priority=priority,
            metadata=metadata,
        )


@dataclass(frozen=True)
class InspectedRequest:
    request: RequestEnvelope
    input_token_ids: tuple[int, ...]
    input_tokens: int
    total_reserved_tokens: int

    def to_mapping(self) -> dict[str, Any]:
        return {
            "request": asdict(self.request),
            "input_token_ids": list(self.input_token_ids),
            "input_tokens": self.input_tokens,
            "total_reserved_tokens": self.total_reserved_tokens,
        }


@dataclass(frozen=True)
class RejectedRequest:
    request_id: str
    reason: str
    observed_tokens: int | None = None

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlannedBatch:
    batch_id: str
    request_ids: tuple[str, ...]
    reserved_tokens: int
    tenants: tuple[str, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "request_ids": list(self.request_ids),
            "reserved_tokens": self.reserved_tokens,
            "tenants": list(self.tenants),
        }


@dataclass(frozen=True)
class GatewayReport:
    accepted: tuple[InspectedRequest, ...]
    rejected: tuple[RejectedRequest, ...]
    batches: tuple[PlannedBatch, ...]
    counters: dict[str, int]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "accepted": [item.to_mapping() for item in self.accepted],
            "rejected": [item.to_mapping() for item in self.rejected],
            "batches": [item.to_mapping() for item in self.batches],
            "counters": dict(self.counters),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_mapping(), indent=2, sort_keys=True)


def load_requests(path: Path) -> tuple[RequestEnvelope, ...]:
    requests: list[RequestEnvelope] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        request = RequestEnvelope.from_mapping(json.loads(line), line_number)
        if request.request_id in seen:
            raise ValueError(f"line {line_number}: duplicate request_id {request.request_id!r}")
        seen.add(request.request_id)
        requests.append(request)
    if not requests:
        raise ValueError(f"no requests found in {path}")
    return tuple(requests)


def stable_priority_order(requests: Iterable[RequestEnvelope]) -> tuple[RequestEnvelope, ...]:
    indexed = list(enumerate(requests))
    indexed.sort(key=lambda item: (-item[1].priority, item[0]))
    return tuple(request for _, request in indexed)
