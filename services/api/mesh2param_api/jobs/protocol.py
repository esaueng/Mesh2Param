from __future__ import annotations

import json
from typing import Literal

from pydantic import Field

from ..schemas.common import StrictAPIModel

MAX_IPC_BYTES = 64 * 1024
MAX_RESULT_BYTES = 64 * 1024 * 1024


class WorkerEvent(StrictAPIModel):
    type: Literal["progress", "heartbeat", "log", "completed", "cancelled", "failed"]
    phase: str = Field(min_length=1, max_length=80)
    progress: float | None = Field(default=None, ge=0, le=100)
    level: Literal["debug", "info", "warning", "error"] = "info"
    message: str | None = Field(default=None, max_length=2000)
    code: str | None = Field(default=None, max_length=100)
    summary: str | None = Field(default=None, max_length=400)
    detail: str | None = Field(default=None, max_length=4000)
    recoverable: bool | None = None
    recommended_action: str | None = Field(default=None, max_length=2000)
    result_file: str | None = Field(default=None, max_length=100)
    internal_traceback: str | None = Field(default=None, max_length=16_000)
    previous_phase: str | None = Field(default=None, max_length=80)
    previous_phase_duration_ms: float | None = Field(default=None, ge=0)


def encode_event(event: WorkerEvent) -> bytes:
    payload = event.model_dump_json(by_alias=True, exclude_none=True).encode("utf-8")
    if len(payload) > MAX_IPC_BYTES:
        raise RuntimeError("worker IPC event exceeds the protocol limit")
    return payload


def decode_event(payload: bytes) -> WorkerEvent:
    if len(payload) > MAX_IPC_BYTES:
        raise ValueError("worker IPC event exceeds the protocol limit")
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("worker IPC event is not valid JSON") from exc
    return WorkerEvent.model_validate(raw)


__all__ = ["MAX_IPC_BYTES", "MAX_RESULT_BYTES", "WorkerEvent", "decode_event", "encode_event"]
