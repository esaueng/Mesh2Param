from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    and_,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


TERMINAL_JOB_STATUSES = {
    JobStatus.COMPLETED.value,
    JobStatus.CANCELLED.value,
    JobStatus.FAILED.value,
}


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("units IN ('mm','cm','m','in','ft')", name="ck_project_units"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    units: Mapped[str] = mapped_column(String(4), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


Index("ix_projects_updated_id", Project.updated_at, Project.id)


class ProjectState(Base):
    __tablename__ = "project_states"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    document_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    based_on_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ArtifactBlob(Base):
    __tablename__ = "artifact_blobs"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class SourceAsset(Base):
    __tablename__ = "source_assets"
    __table_args__ = (
        CheckConstraint("format IN ('stl','obj','ply','generated')", name="ck_source_format"),
        CheckConstraint("state IN ('pending','valid','invalid')", name="ck_source_state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    encoding: Mapped[str] = mapped_column(String(40), nullable=False)
    blob_sha256: Mapped[str] = mapped_column(
        String(64), ForeignKey("artifact_blobs.sha256", ondelete="RESTRICT"), nullable=False
    )
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    declared_units: Mapped[str] = mapped_column(String(4), nullable=False)
    units_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scale_factor: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    diagnostics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Version(Base):
    __tablename__ = "versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("versions.id", ondelete="RESTRICT"), nullable=True
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    state_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    repair_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    segmentation_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(40), nullable=False, default="not-run")
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    artifact_set_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    engine_version: Mapped[str] = mapped_column(String(80), nullable=False)
    dependency_versions_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


Index("ix_versions_project_created_id", Version.project_id, Version.created_at, Version.id)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','completed','cancelled','failed')",
            name="ck_job_status",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_job_progress"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    input_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    output_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    mutates_project: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    input_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    settings_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    deterministic_seed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    phase: Mapped[str] = mapped_column(String(80), nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_attempt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(String(400), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_recoverable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


Index(
    "uq_jobs_one_active_mutation",
    Job.project_id,
    unique=True,
    sqlite_where=and_(
        Job.mutates_project.is_(True), Job.status.in_(("queued", "running"))
    ),
    postgresql_where=and_(
        Job.mutates_project.is_(True), Job.status.in_(("queued", "running"))
    ),
)
Index("ix_jobs_created_id", Job.created_at, Job.id)
Index("ix_jobs_project_status_created", Job.project_id, Job.status, Job.created_at)


class JobAttempt(Base):
    __tablename__ = "job_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','completed','cancelled','failed')",
            name="ck_attempt_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    run_token: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    worker_pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workdir_token: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)


Index("uq_job_attempt_number", JobAttempt.job_id, JobAttempt.attempt_number, unique=True)


EVENT_ID = BigInteger().with_variant(Integer, "sqlite")


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (
        CheckConstraint(
            "progress IS NULL OR (progress >= 0 AND progress <= 100)",
            name="ck_event_progress",
        ),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(EVENT_ID, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("job_attempts.id", ondelete="CASCADE"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    phase: Mapped[str | None] = mapped_column(String(80), nullable=True)
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ArtifactSet(Base):
    __tablename__ = "artifact_sets"
    __table_args__ = (
        CheckConstraint(
            "validation_state IN ('pending','valid','valid-with-warnings','invalid')",
            name="ck_artifact_set_validation",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    validation_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("artifact_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    logical_name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    blob_sha256: Mapped[str] = mapped_column(
        String(64), ForeignKey("artifact_blobs.sha256", ondelete="RESTRICT"), nullable=False
    )
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


Index("uq_artifact_set_name", Artifact.artifact_set_id, Artifact.logical_name, unique=True)


class OperationCache(Base):
    __tablename__ = "operation_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("artifact_sets.id", ondelete="CASCADE"), nullable=False
    )
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    engine_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AuditRecord(Base):
    __tablename__ = "audit_records"

    id: Mapped[int] = mapped_column(EVENT_ID, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


__all__ = [
    "TERMINAL_JOB_STATUSES",
    "Artifact",
    "ArtifactBlob",
    "ArtifactSet",
    "AuditRecord",
    "Base",
    "Job",
    "JobAttempt",
    "JobEvent",
    "JobStatus",
    "OperationCache",
    "Project",
    "ProjectState",
    "SourceAsset",
    "Version",
    "utc_now",
]
