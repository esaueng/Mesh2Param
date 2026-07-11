from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part[:1].upper() + part[1:] for part in rest)


class StrictAPIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        strict=True,
        validate_default=True,
    )


class Meta(StrictAPIModel):
    request_id: str


class SuccessEnvelope[DataT](StrictAPIModel):
    data: DataT
    meta: Meta


class ErrorBody(StrictAPIModel):
    code: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=400)
    detail: str = Field(min_length=1, max_length=4000)
    phase: str | None = None
    project_id: str | None = None
    job_id: str | None = None
    recoverable: bool
    recommended_action: str | None = None


class ErrorEnvelope(StrictAPIModel):
    error: ErrorBody
    meta: Meta


__all__ = ["ErrorBody", "ErrorEnvelope", "Meta", "StrictAPIModel", "SuccessEnvelope", "to_camel"]
