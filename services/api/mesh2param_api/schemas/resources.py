from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, JsonValue

from .common import StrictAPIModel, SuccessEnvelope


class ProjectResource(StrictAPIModel):
    id: str
    name: str
    units: Literal["mm", "cm", "m", "in", "ft"]
    schema_version: str
    revision: int
    state: dict[str, JsonValue]
    based_on_version_id: str | None
    created_at: str
    updated_at: str


class ProjectList(StrictAPIModel):
    items: list[ProjectResource]
    total: int


class JobErrorResource(StrictAPIModel):
    code: str
    summary: str | None
    detail: str | None
    phase: str
    project_id: str
    job_id: str
    recoverable: bool
    recommended_action: str | None


class JobResource(StrictAPIModel):
    id: str
    project_id: str
    kind: str
    status: Literal["queued", "running", "completed", "cancelled", "failed"]
    progress: float
    phase: str
    input_revision: int
    attempt: int
    max_attempts: int
    created_at: str
    started_at: str | None
    heartbeat_at: str | None
    finished_at: str | None
    cancel_requested_at: str | None
    error: JobErrorResource | None
    result: dict[str, JsonValue] | None
    events_url: str


class SourceResource(StrictAPIModel):
    id: str
    original_file_name: str
    format: str
    encoding: str
    sha256: str
    byte_size: int
    declared_units: str
    units_confirmed: bool
    scale_factor: float
    state: str


class UploadAccepted(StrictAPIModel):
    source: SourceResource
    job: JobResource
    revision: int


class ArtifactResource(StrictAPIModel):
    id: str
    name: str
    kind: str
    sha256: str
    byte_size: int
    media_type: str
    storage_key: str
    metadata: dict[str, JsonValue]
    created_at: str


class ArtifactList(StrictAPIModel):
    items: list[ArtifactResource]
    total: int


class VersionResource(StrictAPIModel):
    id: str
    project_id: str
    parent_id: str | None
    label: str
    state: dict[str, JsonValue]
    source_sha256: str | None
    validation_status: str
    metrics: dict[str, JsonValue] | None
    artifact_set_id: str | None
    engine_version: str
    dependency_versions: dict[str, JsonValue]
    created_at: str


class VersionList(StrictAPIModel):
    items: list[VersionResource]
    total: int


class PatchResource(StrictAPIModel):
    model_config = ConfigDict(
        alias_generator=StrictAPIModel.model_config["alias_generator"],
        populate_by_name=True,
        extra="allow",
        strict=True,
    )

    id: str
    type: str
    locked: bool = False
    name: str | None = None
    triangle_count: int | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class PatchList(StrictAPIModel):
    items: list[PatchResource]
    total: int


ProjectEnvelope = SuccessEnvelope[ProjectResource]
ProjectListEnvelope = SuccessEnvelope[ProjectList]
JobEnvelope = SuccessEnvelope[JobResource]
UploadEnvelope = SuccessEnvelope[UploadAccepted]
ArtifactListEnvelope = SuccessEnvelope[ArtifactList]
VersionEnvelope = SuccessEnvelope[VersionResource]
VersionListEnvelope = SuccessEnvelope[VersionList]
PatchEnvelope = SuccessEnvelope[PatchResource]
PatchListEnvelope = SuccessEnvelope[PatchList]


__all__ = [
    "ArtifactListEnvelope",
    "ArtifactResource",
    "JobEnvelope",
    "JobResource",
    "PatchEnvelope",
    "PatchListEnvelope",
    "ProjectEnvelope",
    "ProjectListEnvelope",
    "ProjectResource",
    "UploadEnvelope",
    "VersionEnvelope",
    "VersionListEnvelope",
    "VersionResource",
]
