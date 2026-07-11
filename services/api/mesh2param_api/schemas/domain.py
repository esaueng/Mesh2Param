from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue, model_validator

from .common import StrictAPIModel

Units = Literal["mm", "cm", "m", "in", "ft"]


class ProjectCreate(StrictAPIModel):
    name: str = Field(default="Untitled project", min_length=1, max_length=200)
    units: Units = "mm"


class ProjectPatch(StrictAPIModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    units: Units | None = None

    @model_validator(mode="after")
    def require_change(self) -> ProjectPatch:
        if self.name is None and self.units is None:
            raise ValueError("at least one project field is required")
        return self


class OperationRequest(StrictAPIModel):
    settings: dict[str, JsonValue] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, ge=0.1, le=86_400)


class CadgraphUpdate(StrictAPIModel):
    cadgraph: dict[str, JsonValue]


class PatchUpdate(StrictAPIModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    hidden: bool | None = None
    locked: bool | None = None
    classification: (
        Literal["plane", "cylinder", "cone", "sphere", "freeform", "unknown"] | None
    ) = None
    parameters: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def require_change(self) -> PatchUpdate:
        if all(
            value is None
            for value in (self.name, self.hidden, self.locked, self.classification, self.parameters)
        ):
            raise ValueError("at least one patch field is required")
        return self


class PatchMergeRequest(StrictAPIModel):
    patch_ids: list[str] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def require_distinct(self) -> PatchMergeRequest:
        if len(set(self.patch_ids)) != 2:
            raise ValueError("patch IDs must be distinct")
        return self


class PatchSplitRequest(StrictAPIModel):
    patch_id: str
    triangle_ids: list[int] = Field(min_length=1, max_length=2_000_000)


class VersionCreate(StrictAPIModel):
    label: str = Field(min_length=1, max_length=200)


__all__ = [
    "CadgraphUpdate",
    "OperationRequest",
    "PatchMergeRequest",
    "PatchSplitRequest",
    "PatchUpdate",
    "ProjectCreate",
    "ProjectPatch",
    "Units",
    "VersionCreate",
]
