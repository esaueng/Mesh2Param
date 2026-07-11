from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from mesh2param import __version__ as engine_version
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from .models import (
    TERMINAL_JOB_STATUSES,
    Artifact,
    ArtifactBlob,
    ArtifactSet,
    AuditRecord,
    Job,
    JobAttempt,
    JobEvent,
    JobStatus,
    OperationCache,
    Project,
    ProjectState,
    SourceAsset,
    Version,
    utc_now,
)
from .session import Database


class RepositoryError(RuntimeError):
    pass


class NotFoundError(RepositoryError):
    pass


class RevisionConflictError(RepositoryError):
    def __init__(self, current_revision: int) -> None:
        super().__init__(f"project revision is {current_revision}")
        self.current_revision = current_revision


class ActiveJobConflictError(RepositoryError):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _hash_json(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _initial_document(project_id: str, name: str, units: str) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0.0",
        "projectId": project_id,
        "name": name,
        "units": units,
        "source": None,
        "diagnostics": None,
        "repair": None,
        "analysis": None,
        "patches": [],
        "cadgraph": None,
        "validation": None,
        "metrics": None,
        "artifactSetId": None,
        "artifacts": [],
        "currentVersionId": None,
        "settings": {},
    }


class Repository:
    """Database authority with short, independent SQLAlchemy transactions."""

    def __init__(self, database: Database, *, max_job_events: int = 20_000) -> None:
        if max_job_events < 1:
            raise ValueError("max_job_events must be positive")
        self.database = database
        self.sessions = database.sessions
        self.max_job_events = max_job_events

    # Projects and authoritative working state.
    def create_project(self, name: str, units: str) -> dict[str, Any]:
        project_id = _uuid()
        now = utc_now()
        document = _initial_document(project_id, name, units)
        with self.sessions.begin() as session:
            session.add(
                Project(
                    id=project_id,
                    name=name,
                    units=units,
                    schema_version="1.0.0",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                ProjectState(
                    project_id=project_id,
                    revision=1,
                    document_json=document,
                    updated_at=now,
                )
            )
        return self.get_project(project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        with self.sessions() as session:
            rows = session.execute(
                select(Project, ProjectState)
                .join(ProjectState, ProjectState.project_id == Project.id)
                .order_by(Project.updated_at.desc(), Project.id)
            ).all()
            return [self._project_dict(project, state) for project, state in rows]

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self.sessions() as session:
            row = session.execute(
                select(Project, ProjectState)
                .join(ProjectState, ProjectState.project_id == Project.id)
                .where(Project.id == project_id)
            ).one_or_none()
            if row is None:
                raise NotFoundError("project not found")
            return self._project_dict(row[0], row[1])

    def get_state(self, project_id: str) -> tuple[int, dict[str, Any]]:
        with self.sessions() as session:
            state = session.get(ProjectState, project_id)
            if state is None:
                raise NotFoundError("project not found")
            return int(state.revision), copy.deepcopy(state.document_json)

    def update_project(
        self,
        project_id: str,
        expected_revision: int,
        *,
        name: str | None,
        units: str | None,
    ) -> dict[str, Any]:
        with self.sessions.begin() as session:
            project = session.get(Project, project_id)
            state = session.get(ProjectState, project_id)
            if project is None or state is None:
                raise NotFoundError("project not found")
            self._require_revision(state, expected_revision)
            document = copy.deepcopy(state.document_json)
            if name is not None:
                project.name = name
                document["name"] = name
            if units is not None:
                project.units = units
                document["units"] = units
            project.updated_at = utc_now()
            state.document_json = document
            state.revision += 1
            state.updated_at = utc_now()
        return self.get_project(project_id)

    def replace_state(
        self,
        project_id: str,
        expected_revision: int,
        document: dict[str, Any],
        *,
        based_on_version_id: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        with self.sessions.begin() as session:
            project = session.get(Project, project_id)
            state = session.get(ProjectState, project_id)
            if project is None or state is None:
                raise NotFoundError("project not found")
            self._require_revision(state, expected_revision)
            next_document = copy.deepcopy(document)
            next_document["projectId"] = project_id
            next_document["name"] = project.name
            next_document["units"] = project.units
            state.document_json = next_document
            state.revision += 1
            state.based_on_version_id = based_on_version_id
            state.updated_at = utc_now()
            project.updated_at = utc_now()
            next_revision = int(state.revision)
        return next_revision, next_document

    def delete_project(self, project_id: str) -> None:
        with self.sessions.begin() as session:
            project = session.get(Project, project_id)
            if project is None:
                raise NotFoundError("project not found")
            session.delete(project)

    # Upload/source preservation.
    def create_source_asset(
        self,
        project_id: str,
        expected_revision: int,
        *,
        original_filename: str,
        format_name: str,
        encoding: str,
        blob: dict[str, Any],
        declared_units: str,
        units_confirmed: bool,
        scale_factor: float,
    ) -> tuple[dict[str, Any], int]:
        source_id = _uuid()
        with self.sessions.begin() as session:
            state = session.get(ProjectState, project_id)
            if state is None:
                raise NotFoundError("project not found")
            self._require_revision(state, expected_revision)
            self._upsert_blob(session, blob)
            source = SourceAsset(
                id=source_id,
                project_id=project_id,
                original_filename=original_filename,
                format=format_name,
                encoding=encoding,
                blob_sha256=str(blob["sha256"]),
                byte_size=int(blob["byteSize"]),
                declared_units=declared_units,
                units_confirmed=units_confirmed,
                scale_factor=scale_factor,
                state="pending",
            )
            session.add(source)
            source_document = {
                "id": source_id,
                "originalFileName": original_filename,
                "format": format_name,
                "encoding": encoding,
                "sha256": source.blob_sha256,
                "byteSize": source.byte_size,
                "declaredUnits": declared_units,
                "unitsConfirmed": units_confirmed,
                "scaleFactor": scale_factor,
                "state": "pending",
            }
            document = copy.deepcopy(state.document_json)
            project_settings = document.get("settings")
            if isinstance(project_settings, dict):
                project_settings = copy.deepcopy(project_settings)
                project_settings.pop("automaticReconstruction", None)
                document["settings"] = project_settings
            document.update(
                {
                    "source": source_document,
                    "diagnostics": None,
                    "repair": None,
                    "analysis": None,
                    "patches": [],
                    "cadgraph": None,
                    "validation": None,
                    "metrics": None,
                    "artifactSetId": None,
                    "artifacts": [],
                }
            )
            state.document_json = document
            state.revision += 1
            state.updated_at = utc_now()
            revision = int(state.revision)
        return source_document, revision

    def get_source_asset(self, project_id: str, source_id: str | None = None) -> dict[str, Any]:
        with self.sessions() as session:
            statement = select(SourceAsset).where(SourceAsset.project_id == project_id)
            if source_id is not None:
                statement = statement.where(SourceAsset.id == source_id)
            else:
                statement = statement.order_by(SourceAsset.created_at.desc()).limit(1)
            source = session.scalar(statement)
            if source is None:
                raise NotFoundError("source asset not found")
            blob = session.get(ArtifactBlob, source.blob_sha256)
            if blob is None:
                raise RepositoryError("source blob metadata is missing")
            return {
                "id": source.id,
                "projectId": source.project_id,
                "originalFileName": source.original_filename,
                "format": source.format,
                "encoding": source.encoding,
                "sha256": source.blob_sha256,
                "byteSize": source.byte_size,
                "declaredUnits": source.declared_units,
                "unitsConfirmed": source.units_confirmed,
                "scaleFactor": source.scale_factor,
                "state": source.state,
                "diagnostics": source.diagnostics_json,
                "storageKey": blob.storage_key,
            }

    # Database-backed job queue and event log.
    def create_job(
        self,
        project_id: str,
        expected_revision: int,
        kind: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float,
        mutates_project: bool = True,
        max_attempts: int = 1,
    ) -> dict[str, Any]:
        job_id = _uuid()
        now = utc_now()
        settings = payload.get("settings", {})
        input_hash = str(payload.get("inputHash") or _hash_json(payload.get("input", payload)))
        settings_hash = _hash_json(settings)
        cache_key = _hash_json(
            {
                "kind": kind,
                "inputHash": input_hash,
                "settingsHash": settings_hash,
                "engineVersion": engine_version,
            }
        )
        try:
            with self.sessions.begin() as session:
                state = session.get(ProjectState, project_id)
                if state is None:
                    raise NotFoundError("project not found")
                self._require_revision(state, expected_revision)
                job = Job(
                    id=job_id,
                    project_id=project_id,
                    kind=kind,
                    status=JobStatus.QUEUED.value,
                    mutates_project=mutates_project,
                    payload_json=copy.deepcopy(payload),
                    input_revision=expected_revision,
                    input_hash=input_hash,
                    settings_hash=settings_hash,
                    cache_key=cache_key,
                    deterministic_seed=int(payload.get("deterministicSeed", 0)),
                    progress=0.0,
                    phase="queued",
                    created_at=now,
                    available_at=now,
                    timeout_seconds=timeout_seconds,
                    max_attempts=max_attempts,
                )
                session.add(job)
                session.flush()
                self._event(
                    session,
                    job,
                    None,
                    "state",
                    phase="queued",
                    progress=0.0,
                    message="Job queued",
                    data={"status": "queued"},
                )
        except IntegrityError as exc:
            raise ActiveJobConflictError("another mutating project job is active") from exc
        return self.get_job(job_id)

    def claim_one(self) -> dict[str, Any] | None:
        now = utc_now()
        attempt_id = _uuid()
        run_token = _uuid()
        workdir_token = uuid.uuid4().hex
        candidate = (
            select(Job.id)
            .where(Job.status == JobStatus.QUEUED.value, Job.available_at <= now)
            .order_by(Job.available_at, Job.created_at, Job.id)
            .limit(1)
            .scalar_subquery()
        )
        statement = (
            update(Job)
            .where(Job.id == candidate, Job.status == JobStatus.QUEUED.value)
            .values(
                status=JobStatus.RUNNING.value,
                phase="starting worker",
                progress=0.0,
                started_at=now,
                heartbeat_at=now,
                attempt_count=Job.attempt_count + 1,
                current_attempt_id=attempt_id,
            )
            .returning(
                Job.id,
                Job.project_id,
                Job.kind,
                Job.payload_json,
                Job.input_revision,
                Job.timeout_seconds,
                Job.attempt_count,
                Job.max_attempts,
            )
        )
        with self.sessions.begin() as session:
            row = session.execute(statement).mappings().one_or_none()
            if row is None:
                return None
            attempt_number = int(row["attempt_count"])
            attempt = JobAttempt(
                id=attempt_id,
                job_id=str(row["id"]),
                attempt_number=attempt_number,
                run_token=run_token,
                status=JobStatus.RUNNING.value,
                workdir_token=workdir_token,
                started_at=now,
                heartbeat_at=now,
            )
            session.add(attempt)
            job = session.get(Job, str(row["id"]))
            if job is None:
                raise AssertionError("claimed job disappeared")
            self._event(
                session,
                job,
                attempt_id,
                "state",
                phase="starting worker",
                progress=0.0,
                message="Geometry worker starting",
                data={"status": "running", "attempt": attempt_number},
            )
            result = dict(row)
            result.update(
                {
                    "attemptId": attempt_id,
                    "runToken": run_token,
                    "workdirToken": workdir_token,
                }
            )
            return result

    def set_worker_pid(self, job_id: str, attempt_id: str, run_token: str, pid: int) -> bool:
        with self.sessions.begin() as session:
            attempt = session.scalar(
                select(JobAttempt).where(
                    JobAttempt.id == attempt_id,
                    JobAttempt.job_id == job_id,
                    JobAttempt.run_token == run_token,
                    JobAttempt.status == JobStatus.RUNNING.value,
                )
            )
            if attempt is None:
                return False
            attempt.worker_pid = pid
            return True

    def touch_heartbeat(self, job_id: str, attempt_id: str, run_token: str) -> bool:
        """Persist supervisor-observed liveness without growing the durable event log."""

        now = utc_now()
        with self.sessions.begin() as session:
            pair = session.execute(
                select(Job, JobAttempt)
                .join(JobAttempt, JobAttempt.id == Job.current_attempt_id)
                .where(
                    Job.id == job_id,
                    Job.status == JobStatus.RUNNING.value,
                    JobAttempt.id == attempt_id,
                    JobAttempt.run_token == run_token,
                    JobAttempt.status == JobStatus.RUNNING.value,
                )
            ).one_or_none()
            if pair is None:
                return False
            job, attempt = pair
            job.heartbeat_at = now
            attempt.heartbeat_at = now
            return True

    def apply_worker_event(
        self,
        job_id: str,
        attempt_id: str,
        run_token: str,
        item: dict[str, Any],
    ) -> bool:
        event_type = str(item["type"])
        if event_type not in {"progress", "heartbeat", "log"}:
            return False
        now = utc_now()
        with self.sessions.begin() as session:
            pair = session.execute(
                select(Job, JobAttempt)
                .join(JobAttempt, JobAttempt.id == Job.current_attempt_id)
                .where(
                    Job.id == job_id,
                    Job.status == JobStatus.RUNNING.value,
                    JobAttempt.id == attempt_id,
                    JobAttempt.run_token == run_token,
                    JobAttempt.status == JobStatus.RUNNING.value,
                )
            ).one_or_none()
            if pair is None:
                return False
            job, attempt = pair
            progress = max(job.progress, min(99.0, float(item.get("progress", job.progress))))
            phase = str(item.get("phase", job.phase))[:80]
            job.progress = progress
            job.phase = phase
            job.heartbeat_at = now
            attempt.heartbeat_at = now
            self._event(
                session,
                job,
                attempt_id,
                event_type,
                phase=phase,
                progress=progress,
                level=str(item.get("level", "info"))[:16],
                message=str(item.get("message", ""))[:2000] or None,
                code=str(item.get("code", ""))[:100] or None,
                data=self._public_worker_data(item),
            )
            return True

    def complete_job(
        self,
        job_id: str,
        attempt_id: str,
        run_token: str,
        *,
        result: dict[str, Any],
        state_patch: dict[str, Any],
        artifacts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = utc_now()
        artifact_set_id = _uuid() if artifacts else None
        with self.sessions.begin() as session:
            pair = session.execute(
                select(Job, JobAttempt)
                .join(JobAttempt, JobAttempt.id == Job.current_attempt_id)
                .where(
                    Job.id == job_id,
                    Job.status == JobStatus.RUNNING.value,
                    JobAttempt.id == attempt_id,
                    JobAttempt.run_token == run_token,
                    JobAttempt.status == JobStatus.RUNNING.value,
                )
            ).one_or_none()
            if pair is None:
                return {"applied": False}
            job, attempt = pair
            state = session.get(ProjectState, job.project_id)
            if state is None:
                raise NotFoundError("project not found")
            if job.mutates_project and state.revision != job.input_revision:
                raise RevisionConflictError(int(state.revision))

            published_artifacts = [copy.deepcopy(raw) for raw in artifacts]
            if artifact_set_id is not None:
                replaced_names = {str(raw["name"]) for raw in artifacts}
                previous_set_id = state.document_json.get("artifactSetId")
                if isinstance(previous_set_id, str):
                    inherited_rows = session.execute(
                        select(Artifact, ArtifactBlob)
                        .join(ArtifactBlob, ArtifactBlob.sha256 == Artifact.blob_sha256)
                        .where(
                            Artifact.artifact_set_id == previous_set_id,
                            Artifact.logical_name.not_in(replaced_names),
                        )
                        .order_by(Artifact.logical_name)
                    ).all()
                    published_artifacts.extend(
                        {
                            "name": inherited.logical_name,
                            "kind": inherited.kind,
                            "sha256": blob.sha256,
                            "byteSize": blob.byte_size,
                            "mediaType": inherited.media_type,
                            "storageKey": blob.storage_key,
                            "metadata": copy.deepcopy(inherited.metadata_json),
                        }
                        for inherited, blob in inherited_rows
                    )
                published_artifacts.sort(key=lambda raw: str(raw["name"]))
                artifact_set = ArtifactSet(
                    id=artifact_set_id,
                    project_id=job.project_id,
                    job_id=job.id,
                    validation_state=str(result.get("artifactValidationState", "valid")),
                    created_at=now,
                )
                session.add(artifact_set)
                for raw in artifacts:
                    self._upsert_blob(session, raw)
                session.flush()
                for raw in published_artifacts:
                    session.add(
                        Artifact(
                            id=_uuid(),
                            artifact_set_id=artifact_set_id,
                            logical_name=str(raw["name"]),
                            kind=str(raw.get("kind", "artifact")),
                            blob_sha256=str(raw["sha256"]),
                            media_type=str(raw["mediaType"]),
                            metadata_json=copy.deepcopy(raw.get("metadata", {})),
                            created_at=now,
                        )
                    )

            document = copy.deepcopy(state.document_json)
            document.update(copy.deepcopy(state_patch))
            source_result = result.get("sourceAsset")
            if job.kind == "sample_open":
                if not isinstance(source_result, dict) or artifact_set_id is None:
                    raise RepositoryError("sample completion omitted its source artifact")
                source_artifact_name = source_result.get("artifactName")
                if (
                    source_artifact_name != "source-random.stl"
                    or source_result.get("originalFileName") != "source-random.stl"
                    or source_result.get("format") != "stl"
                    or source_result.get("encoding") != "binary"
                    or source_result.get("declaredUnits", "mm") != "mm"
                    or source_result.get("scaleFactor", 1.0) != 1.0
                ):
                    raise RepositoryError("sample completion selected an invalid source artifact")
                source_blob = next(
                    (
                        raw
                        for raw in published_artifacts
                        if raw.get("name") == source_artifact_name
                    ),
                    None,
                )
                if (
                    source_blob is None
                    or source_blob.get("kind") != "source"
                    or source_blob.get("mediaType") != "model/stl"
                ):
                    raise RepositoryError("sample source artifact is missing")
                source_id = _uuid()
                source = SourceAsset(
                    id=source_id,
                    project_id=job.project_id,
                    original_filename=str(source_result["originalFileName"]),
                    format=str(source_result["format"]),
                    encoding=str(source_result["encoding"]),
                    blob_sha256=str(source_blob["sha256"]),
                    byte_size=int(source_blob["byteSize"]),
                    declared_units=str(source_result.get("declaredUnits", "mm")),
                    units_confirmed=True,
                    scale_factor=float(source_result.get("scaleFactor", 1.0)),
                    state="valid",
                )
                session.add(source)
                document["source"] = {
                    "id": source_id,
                    "originalFileName": source.original_filename,
                    "format": source.format,
                    "encoding": source.encoding,
                    "sha256": source.blob_sha256,
                    "byteSize": source.byte_size,
                    "declaredUnits": source.declared_units,
                    "unitsConfirmed": True,
                    "scaleFactor": source.scale_factor,
                    "state": "valid",
                }
            if artifact_set_id is not None:
                document["artifactSetId"] = artifact_set_id
                document["artifacts"] = [
                    {
                        "name": raw["name"],
                        "sha256": raw["sha256"],
                        "byteSize": raw["byteSize"],
                        "mediaType": raw["mediaType"],
                    }
                    for raw in published_artifacts
                ]
            if job.kind == "upload" and isinstance(document.get("source"), dict):
                source_document = dict(document["source"])
                source_document["state"] = "valid"
                document["source"] = source_document
                upload_source_id = source_document.get("id")
                if isinstance(upload_source_id, str):
                    existing_source = session.get(SourceAsset, upload_source_id)
                    if existing_source is not None:
                        existing_source.state = "valid"
                        diagnostics = state_patch.get("diagnostics")
                        existing_source.diagnostics_json = (
                            copy.deepcopy(diagnostics) if isinstance(diagnostics, dict) else None
                        )

            next_revision = int(state.revision)
            if job.mutates_project:
                state.document_json = document
                state.revision += 1
                state.updated_at = now
                next_revision = int(state.revision)

            public_result = copy.deepcopy(result)
            public_result.pop("statePatch", None)
            public_result.pop("artifacts", None)
            public_result["revision"] = next_revision
            public_result["artifactSetId"] = artifact_set_id
            job.status = JobStatus.COMPLETED.value
            job.progress = 100.0
            job.phase = "completed"
            job.finished_at = now
            job.result_json = public_result
            attempt.status = JobStatus.COMPLETED.value
            attempt.finished_at = now
            self._event(
                session,
                job,
                attempt_id,
                "completed",
                phase="completed",
                progress=100.0,
                message="Job completed",
                data={"status": "completed", "result": public_result},
            )
            if artifact_set_id is not None and session.get(OperationCache, job.cache_key) is None:
                session.add(
                    OperationCache(
                        cache_key=job.cache_key,
                        artifact_set_id=artifact_set_id,
                        result_json=public_result,
                        engine_fingerprint=f"mesh2param/{engine_version}",
                    )
                )
            return {
                "applied": True,
                "revision": next_revision,
                "artifactSetId": artifact_set_id,
            }

    def terminalize_job(
        self,
        job_id: str,
        attempt_id: str | None,
        run_token: str | None,
        *,
        status: JobStatus,
        code: str,
        summary: str,
        detail: str,
        phase: str,
        recoverable: bool,
        recommended_action: str | None,
        exit_code: int | None = None,
    ) -> bool:
        if status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
            raise ValueError("terminalize_job only accepts failed or cancelled")
        now = utc_now()
        with self.sessions.begin() as session:
            job = session.get(Job, job_id)
            if job is None or job.status not in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}:
                return False
            attempt: JobAttempt | None = None
            if attempt_id is not None:
                attempt = session.get(JobAttempt, attempt_id)
                if (
                    attempt is None
                    or attempt.job_id != job_id
                    or (run_token is not None and attempt.run_token != run_token)
                    or job.current_attempt_id != attempt_id
                ):
                    return False
                attempt.status = status.value
                attempt.finished_at = now
                attempt.exit_code = exit_code
                attempt.failure_code = code
            job.status = status.value
            job.phase = phase[:80]
            job.finished_at = now
            if status == JobStatus.FAILED:
                job.error_code = code[:100]
                job.error_summary = summary[:400]
                job.error_detail = detail[:4000]
                job.error_recoverable = recoverable
                job.recommended_action = recommended_action
            self._event(
                session,
                job,
                attempt_id,
                status.value,
                phase=job.phase,
                progress=job.progress,
                level="error" if status == JobStatus.FAILED else "info",
                message=summary,
                code=code,
                data={
                    "status": status.value,
                    "detail": detail,
                    "recoverable": recoverable,
                    "recommendedAction": recommended_action,
                },
            )
            return True

    def retry_or_fail_crash(
        self,
        job_id: str,
        attempt_id: str,
        run_token: str,
        *,
        exit_code: int | None,
    ) -> bool:
        now = utc_now()
        with self.sessions.begin() as session:
            job = session.get(Job, job_id)
            attempt = session.get(JobAttempt, attempt_id)
            if (
                job is None
                or attempt is None
                or job.current_attempt_id != attempt_id
                or attempt.run_token != run_token
                or job.status != JobStatus.RUNNING.value
            ):
                return False
            attempt.status = JobStatus.FAILED.value
            attempt.finished_at = now
            attempt.exit_code = exit_code
            attempt.failure_code = "worker_crash"
            if job.attempt_count < job.max_attempts and job.cancel_requested_at is None:
                job.status = JobStatus.QUEUED.value
                job.phase = "queued"
                job.progress = 0.0
                job.current_attempt_id = None
                job.available_at = now + timedelta(milliseconds=100)
                self._event(
                    session,
                    job,
                    attempt_id,
                    "retry_scheduled",
                    phase="queued",
                    progress=0.0,
                    level="warning",
                    message="Worker crashed; retry scheduled in a fresh process",
                    code="worker_crash",
                    data={"attempt": job.attempt_count, "maxAttempts": job.max_attempts},
                )
                return True
            job.status = JobStatus.FAILED.value
            job.phase = "failed"
            job.finished_at = now
            job.error_code = "worker_crash"
            job.error_summary = "Geometry worker exited unexpectedly"
            job.error_detail = f"Worker exit code: {exit_code}"
            job.error_recoverable = True
            job.recommended_action = "Retry once; if the crash repeats, reduce input complexity."
            self._event(
                session,
                job,
                attempt_id,
                "failed",
                phase="failed",
                progress=job.progress,
                level="error",
                message=job.error_summary,
                code="worker_crash",
                data={
                    "status": "failed",
                    "detail": job.error_detail,
                    "exitCode": exit_code,
                },
            )
            return False

    def request_cancel(self, job_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.sessions.begin() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise NotFoundError("job not found")
            if job.status == JobStatus.QUEUED.value:
                job.status = JobStatus.CANCELLED.value
                job.phase = "cancelled"
                job.cancel_requested_at = now
                job.finished_at = now
                self._event(
                    session,
                    job,
                    None,
                    "cancelled",
                    phase="cancelled",
                    progress=job.progress,
                    message="Queued job cancelled",
                    code="job_cancelled",
                    data={"status": "cancelled"},
                )
            elif job.status == JobStatus.RUNNING.value and job.cancel_requested_at is None:
                job.cancel_requested_at = now
                self._event(
                    session,
                    job,
                    job.current_attempt_id,
                    "cancel_requested",
                    phase=job.phase,
                    progress=job.progress,
                    message="Cancellation requested",
                    data={"status": "running"},
                )
        return self.get_job(job_id)

    def cancellation_requested(self, job_id: str, attempt_id: str) -> bool:
        with self.sessions() as session:
            value = session.execute(
                select(Job.cancel_requested_at).where(
                    Job.id == job_id,
                    Job.current_attempt_id == attempt_id,
                    Job.status == JobStatus.RUNNING.value,
                )
            ).scalar_one_or_none()
            return value is not None

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self.sessions() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise NotFoundError("job not found")
            return self._job_dict(job)

    def events_after(self, job_id: str, cursor: int) -> tuple[list[dict[str, Any]], bool]:
        with self.sessions() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise NotFoundError("job not found")
            rows = session.scalars(
                select(JobEvent)
                .where(JobEvent.job_id == job_id, JobEvent.id > cursor)
                .order_by(JobEvent.id)
                .limit(100)
            ).all()
            return (
                [self._event_dict(row) for row in rows],
                job.status in TERMINAL_JOB_STATUSES,
            )

    def recover_abandoned(self) -> int:
        now = utc_now()
        with self.sessions.begin() as session:
            jobs = session.scalars(select(Job).where(Job.status == JobStatus.RUNNING.value)).all()
            for job in jobs:
                attempt = (
                    session.get(JobAttempt, job.current_attempt_id)
                    if job.current_attempt_id is not None
                    else None
                )
                if attempt is not None:
                    attempt.status = JobStatus.FAILED.value
                    attempt.failure_code = "worker_abandoned"
                    attempt.finished_at = now
                job.status = JobStatus.FAILED.value
                job.phase = "failed"
                job.finished_at = now
                job.error_code = "worker_abandoned"
                job.error_summary = "Worker ownership was lost during service restart"
                job.error_detail = "The prior API process no longer owns this worker attempt."
                job.error_recoverable = True
                job.recommended_action = "Retry the operation."
                self._event(
                    session,
                    job,
                    job.current_attempt_id,
                    "failed",
                    phase="failed",
                    progress=job.progress,
                    level="error",
                    message=job.error_summary,
                    code="worker_abandoned",
                    data={
                        "status": "failed",
                        "detail": job.error_detail,
                        "recoverable": True,
                    },
                )
            return len(jobs)

    # Immutable versions.
    def create_version(self, project_id: str, label: str) -> dict[str, Any]:
        version_id = _uuid()
        with self.sessions.begin() as session:
            state = session.get(ProjectState, project_id)
            if state is None:
                raise NotFoundError("project not found")
            document = copy.deepcopy(state.document_json)
            source = document.get("source")
            parent_id = document.get("currentVersionId")
            validation = document.get("validation")
            version = Version(
                id=version_id,
                project_id=project_id,
                parent_id=parent_id if isinstance(parent_id, str) else None,
                label=label,
                state_snapshot_json=document,
                source_sha256=(source.get("sha256") if isinstance(source, dict) else None),
                validation_status=(
                    str(validation.get("status", "not-run"))
                    if isinstance(validation, dict)
                    else "not-run"
                ),
                metrics_json=(
                    copy.deepcopy(document.get("metrics"))
                    if isinstance(document.get("metrics"), dict)
                    else None
                ),
                artifact_set_id=(
                    str(document["artifactSetId"]) if document.get("artifactSetId") else None
                ),
                engine_version=engine_version,
                dependency_versions_json={"mesh2param": engine_version},
            )
            session.add(version)
            document["currentVersionId"] = version_id
            state.document_json = document
            state.revision += 1
            state.updated_at = utc_now()
        return self.get_version(project_id, version_id)

    def list_versions(self, project_id: str) -> list[dict[str, Any]]:
        with self.sessions() as session:
            if session.get(Project, project_id) is None:
                raise NotFoundError("project not found")
            rows = session.scalars(
                select(Version)
                .where(Version.project_id == project_id)
                .order_by(Version.created_at.desc(), Version.id)
            ).all()
            return [self._version_dict(row) for row in rows]

    def get_version(self, project_id: str, version_id: str) -> dict[str, Any]:
        with self.sessions() as session:
            version = session.scalar(
                select(Version).where(
                    Version.id == version_id, Version.project_id == project_id
                )
            )
            if version is None:
                raise NotFoundError("version not found")
            return self._version_dict(version)

    def restore_version(
        self, project_id: str, version_id: str, expected_revision: int
    ) -> tuple[int, dict[str, Any]]:
        with self.sessions.begin() as session:
            version = session.scalar(
                select(Version).where(
                    Version.id == version_id, Version.project_id == project_id
                )
            )
            state = session.get(ProjectState, project_id)
            if version is None or state is None:
                raise NotFoundError("version not found")
            self._require_revision(state, expected_revision)
            document = copy.deepcopy(version.state_snapshot_json)
            document["currentVersionId"] = version_id
            state.document_json = document
            state.based_on_version_id = version_id
            state.revision += 1
            state.updated_at = utc_now()
            return int(state.revision), document

    def delete_version(self, project_id: str, version_id: str) -> None:
        with self.sessions.begin() as session:
            version = session.scalar(
                select(Version).where(
                    Version.id == version_id, Version.project_id == project_id
                )
            )
            if version is None:
                raise NotFoundError("version not found")
            child_count = session.scalar(
                select(func.count()).select_from(Version).where(Version.parent_id == version_id)
            )
            state = session.get(ProjectState, project_id)
            current = state.document_json.get("currentVersionId") if state is not None else None
            if child_count or current == version_id:
                raise ActiveJobConflictError("version is still referenced")
            session.delete(version)

    # Artifacts.
    def list_artifacts(self, project_id: str) -> list[dict[str, Any]]:
        revision, document = self.get_state(project_id)
        del revision
        artifact_set_id = document.get("artifactSetId")
        if not isinstance(artifact_set_id, str):
            return []
        with self.sessions() as session:
            rows = session.execute(
                select(Artifact, ArtifactBlob)
                .join(ArtifactBlob, ArtifactBlob.sha256 == Artifact.blob_sha256)
                .where(Artifact.artifact_set_id == artifact_set_id)
                .order_by(Artifact.logical_name)
            ).all()
            return [self._artifact_dict(artifact, blob) for artifact, blob in rows]

    def get_artifact(self, project_id: str, logical_name: str) -> dict[str, Any]:
        revision, document = self.get_state(project_id)
        del revision
        artifact_set_id = document.get("artifactSetId")
        if not isinstance(artifact_set_id, str):
            raise NotFoundError("artifact not found")
        with self.sessions() as session:
            row = session.execute(
                select(Artifact, ArtifactBlob)
                .join(ArtifactBlob, ArtifactBlob.sha256 == Artifact.blob_sha256)
                .where(
                    Artifact.artifact_set_id == artifact_set_id,
                    Artifact.logical_name == logical_name,
                )
            ).one_or_none()
            if row is None:
                raise NotFoundError("artifact not found")
            return self._artifact_dict(row[0], row[1])

    def delete_orphan_blobs_before(self, cutoff: datetime) -> list[str]:
        """Drop old blob metadata only when no source or artifact row references it."""

        source_reference = select(SourceAsset.id).where(
            SourceAsset.blob_sha256 == ArtifactBlob.sha256
        ).exists()
        artifact_reference = select(Artifact.id).where(
            Artifact.blob_sha256 == ArtifactBlob.sha256
        ).exists()
        with self.sessions.begin() as session:
            blobs = session.scalars(
                select(ArtifactBlob).where(
                    ArtifactBlob.created_at < cutoff,
                    ~source_reference,
                    ~artifact_reference,
                )
            ).all()
            digests = [blob.sha256 for blob in blobs]
            for blob in blobs:
                session.delete(blob)
            return digests

    def record_audit(
        self,
        request_id: str,
        action: str,
        outcome: str,
        *,
        project_id: str | None = None,
        job_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.sessions.begin() as session:
            session.add(
                AuditRecord(
                    request_id=request_id,
                    action=action,
                    outcome=outcome,
                    project_id=project_id,
                    job_id=job_id,
                    details_json=copy.deepcopy(details or {}),
                )
            )

    @staticmethod
    def _require_revision(state: ProjectState, expected: int) -> None:
        if int(state.revision) != expected:
            raise RevisionConflictError(int(state.revision))

    @staticmethod
    def _upsert_blob(session: Any, raw: dict[str, Any]) -> None:
        digest = str(raw["sha256"])
        existing = session.get(ArtifactBlob, digest)
        if existing is not None:
            if existing.byte_size != int(raw["byteSize"]):
                raise RepositoryError("content-addressed blob size mismatch")
            return
        session.add(
            ArtifactBlob(
                sha256=digest,
                byte_size=int(raw["byteSize"]),
                media_type=str(raw["mediaType"]),
                storage_key=str(raw["storageKey"]),
            )
        )

    def _event(
        self,
        session: Any,
        job: Job,
        attempt_id: str | None,
        event_type: str,
        *,
        phase: str | None,
        progress: float | None,
        message: str | None,
        data: dict[str, Any],
        level: str = "info",
        code: str | None = None,
    ) -> None:
        event_count = int(
            session.scalar(
                select(func.count()).select_from(JobEvent).where(JobEvent.job_id == job.id)
            )
            or 0
        )
        if event_count >= self.max_job_events:
            oldest_id = session.scalar(
                select(JobEvent.id)
                .where(JobEvent.job_id == job.id)
                .order_by(JobEvent.id)
                .limit(1)
            )
            if oldest_id is not None:
                session.execute(delete(JobEvent).where(JobEvent.id == oldest_id))
        session.add(
            JobEvent(
                job_id=job.id,
                attempt_id=attempt_id,
                event_type=event_type,
                phase=phase,
                progress=progress,
                level=level,
                message=message,
                code=code,
                data_json=data,
            )
        )

    @staticmethod
    def _public_worker_data(item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: copy.deepcopy(value)
            for key, value in item.items()
            if key not in {"internalTraceback", "artifacts", "statePatch", "result"}
        }

    @staticmethod
    def _project_dict(project: Project, state: ProjectState) -> dict[str, Any]:
        return {
            "id": project.id,
            "name": project.name,
            "units": project.units,
            "schemaVersion": project.schema_version,
            "revision": int(state.revision),
            "state": copy.deepcopy(state.document_json),
            "basedOnVersionId": state.based_on_version_id,
            "createdAt": _iso(project.created_at),
            "updatedAt": _iso(project.updated_at),
        }

    @staticmethod
    def _job_dict(job: Job) -> dict[str, Any]:
        error = None
        if job.error_code is not None:
            error = {
                "code": job.error_code,
                "summary": job.error_summary,
                "detail": job.error_detail,
                "phase": job.phase,
                "projectId": job.project_id,
                "jobId": job.id,
                "recoverable": bool(job.error_recoverable),
                "recommendedAction": job.recommended_action,
            }
        return {
            "id": job.id,
            "projectId": job.project_id,
            "kind": job.kind,
            "status": job.status,
            "progress": job.progress,
            "phase": job.phase,
            "inputRevision": int(job.input_revision),
            "attempt": job.attempt_count,
            "maxAttempts": job.max_attempts,
            "createdAt": _iso(job.created_at),
            "startedAt": _iso(job.started_at),
            "heartbeatAt": _iso(job.heartbeat_at),
            "finishedAt": _iso(job.finished_at),
            "cancelRequestedAt": _iso(job.cancel_requested_at),
            "error": error,
            "result": copy.deepcopy(job.result_json),
            "eventsUrl": f"/api/jobs/{job.id}/events",
        }

    @staticmethod
    def _event_dict(event: JobEvent) -> dict[str, Any]:
        return {
            "id": int(event.id),
            "event": event.event_type,
            "data": {
                "jobId": event.job_id,
                "type": event.event_type,
                "phase": event.phase,
                "progress": event.progress,
                "level": event.level,
                "message": event.message,
                "code": event.code,
                "timestamp": _iso(event.created_at),
                **copy.deepcopy(event.data_json),
            },
        }

    @staticmethod
    def _version_dict(version: Version) -> dict[str, Any]:
        return {
            "id": version.id,
            "projectId": version.project_id,
            "parentId": version.parent_id,
            "label": version.label,
            "state": copy.deepcopy(version.state_snapshot_json),
            "sourceSha256": version.source_sha256,
            "validationStatus": version.validation_status,
            "metrics": copy.deepcopy(version.metrics_json),
            "artifactSetId": version.artifact_set_id,
            "engineVersion": version.engine_version,
            "dependencyVersions": copy.deepcopy(version.dependency_versions_json),
            "createdAt": _iso(version.created_at),
        }

    @staticmethod
    def _artifact_dict(artifact: Artifact, blob: ArtifactBlob) -> dict[str, Any]:
        return {
            "id": artifact.id,
            "name": artifact.logical_name,
            "kind": artifact.kind,
            "sha256": artifact.blob_sha256,
            "byteSize": int(blob.byte_size),
            "mediaType": artifact.media_type,
            "storageKey": blob.storage_key,
            "metadata": copy.deepcopy(artifact.metadata_json),
            "createdAt": _iso(artifact.created_at),
        }


__all__ = [
    "ActiveJobConflictError",
    "NotFoundError",
    "Repository",
    "RepositoryError",
    "RevisionConflictError",
]
