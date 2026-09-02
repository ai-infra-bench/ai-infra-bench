from __future__ import annotations

import hashlib
from dataclasses import asdict
from typing import Any, Iterable

import ray

from domain import (
    GatewayReport,
    InspectedRequest,
    PlannedBatch,
    RejectedRequest,
    RequestEnvelope,
    stable_priority_order,
)
from gateway_config import AdmissionSettings


class RuntimeTokenizerClient:
    def __init__(self, tokenizer: Any) -> None:
        self._tokenizer = tokenizer

    def encode(self, prompt: str) -> tuple[int, ...]:
        token_ids = self._tokenizer.encode(prompt, add_special_tokens=False)
        return tuple(int(token_id) for token_id in token_ids)


class PromptInspector:
    def __init__(self, tokenizer: RuntimeTokenizerClient, settings: AdmissionSettings) -> None:
        self._tokenizer = tokenizer
        self._settings = settings

    def inspect(self, request: RequestEnvelope) -> InspectedRequest | RejectedRequest:
        token_ids = self._tokenizer.encode(request.prompt)
        input_tokens = len(token_ids)
        if input_tokens > self._settings.request_token_limit:
            return RejectedRequest(
                request_id=request.request_id,
                reason="input token limit exceeded",
                observed_tokens=input_tokens,
            )
        reserved_output = max(
            request.requested_output_tokens,
            self._settings.reserve_output_tokens,
        )
        return InspectedRequest(
            request=request,
            input_token_ids=token_ids,
            input_tokens=input_tokens,
            total_reserved_tokens=input_tokens + reserved_output,
        )


class BatchBuilder:
    def __init__(self, settings: AdmissionSettings) -> None:
        self._settings = settings

    @staticmethod
    def _batch_id(items: Iterable[InspectedRequest]) -> str:
        request_ids = ",".join(item.request.request_id for item in items)
        return hashlib.sha256(request_ids.encode("utf-8")).hexdigest()[:12]

    def build(self, requests: tuple[InspectedRequest, ...]) -> tuple[PlannedBatch, ...]:
        batches: list[PlannedBatch] = []
        current: list[InspectedRequest] = []
        current_tokens = 0

        def flush() -> None:
            nonlocal current, current_tokens
            if not current:
                return
            batches.append(
                PlannedBatch(
                    batch_id=self._batch_id(current),
                    request_ids=tuple(item.request.request_id for item in current),
                    reserved_tokens=current_tokens,
                    tenants=tuple(sorted({item.request.tenant for item in current})),
                )
            )
            current = []
            current_tokens = 0

        for request in requests:
            would_exceed_tokens = (
                current_tokens + request.total_reserved_tokens
                > self._settings.batch_token_limit
            )
            would_exceed_size = len(current) >= self._settings.max_batch_size
            if current and (would_exceed_tokens or would_exceed_size):
                flush()
            current.append(request)
            current_tokens += request.total_reserved_tokens
        flush()
        return tuple(batches)


class AdmissionPipeline:
    def __init__(self, tokenizer: Any, settings: AdmissionSettings) -> None:
        client = RuntimeTokenizerClient(tokenizer)
        self._inspector = PromptInspector(client, settings)
        self._batch_builder = BatchBuilder(settings)

    def run(self, requests: tuple[RequestEnvelope, ...]) -> GatewayReport:
        accepted: list[InspectedRequest] = []
        rejected: list[RejectedRequest] = []
        ordered = stable_priority_order(requests)
        for request in ordered:
            inspected = self._inspector.inspect(request)
            if isinstance(inspected, RejectedRequest):
                rejected.append(inspected)
            else:
                accepted.append(inspected)
        accepted_tuple = tuple(accepted)
        batches = self._batch_builder.build(accepted_tuple)
        counters = {
            "received": len(requests),
            "accepted": len(accepted_tuple),
            "rejected": len(rejected),
            "batches": len(batches),
            "accepted_input_tokens": sum(item.input_tokens for item in accepted_tuple),
            "reserved_tokens": sum(item.total_reserved_tokens for item in accepted_tuple),
        }
        return GatewayReport(
            accepted=accepted_tuple,
            rejected=tuple(rejected),
            batches=batches,
            counters=counters,
        )


def _request_from_payload(payload: dict[str, Any]) -> RequestEnvelope:
    metadata = {str(key): str(value) for key, value in dict(payload.get("metadata", {})).items()}
    return RequestEnvelope(
        request_id=str(payload["request_id"]),
        tenant=str(payload["tenant"]),
        prompt=str(payload["prompt"]),
        requested_output_tokens=int(payload["requested_output_tokens"]),
        priority=int(payload.get("priority", 0)),
        metadata=metadata,
    )


@ray.remote(num_cpus=1)
def plan_remote_batch(
    tokenizer: Any,
    raw_requests: list[dict[str, Any]],
    raw_settings: dict[str, Any],
) -> dict[str, Any]:
    settings = AdmissionSettings(**raw_settings)
    requests = tuple(_request_from_payload(payload) for payload in raw_requests)
    report = AdmissionPipeline(tokenizer, settings).run(requests)
    return report.to_mapping()


def request_payloads(requests: tuple[RequestEnvelope, ...]) -> list[dict[str, Any]]:
    return [asdict(request) for request in requests]


def admission_settings_payload(settings: AdmissionSettings) -> dict[str, Any]:
    return asdict(settings)
