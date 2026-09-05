from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing as mp
import os
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import Any

from ..config import Settings
from ..db.models import JobStatus
from ..db.repository import Repository, RevisionConflictError
from ..storage import LocalCAS, validate_artifact_name
from .protocol import MAX_IPC_BYTES, MAX_RESULT_BYTES, WorkerEvent, decode_event
from .worker import worker_main

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ActiveJob:
    job_id: str
    project_id: str
    kind: str
    attempt_id: str
    run_token: str
    process: BaseProcess
    receive_connection: Connection
    cancel_event: Any
    workdir: Path
    payload: dict[str, Any]
    started_monotonic: float
    timeout_seconds: float
    max_attempts: int
    last_heartbeat_monotonic: float
    signal_reason: str | None = None
    signal_monotonic: float | None = None
    terminal_received: bool = False


class JobSupervisor:
    """One API-owned supervisor with one fresh spawn process per geometry job."""

    def __init__(self, repository: Repository, storage: LocalCAS, settings: Settings) -> None:
        self.repository = repository
        self.storage = storage
        self.settings = settings
        self.context = mp.get_context("spawn")
        self.active: dict[str, ActiveJob] = {}
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def healthy(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        self.settings.jobs_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        await asyncio.to_thread(self.repository.recover_abandoned)
        self._task = asyncio.create_task(self._run(), name="mesh2param-job-supervisor")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task

    async def _run(self) -> None:
        try:
            while not self._stop.is_set():
                await self._launch_available()
                for active in list(self.active.values()):
                    await self._monitor(active)
                await asyncio.sleep(self.settings.worker_poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("job_supervisor_crashed")
            raise
        finally:
            for active in list(self.active.values()):
                await self._force_stop(active)
                await asyncio.to_thread(
                    self.repository.terminalize_job,
                    active.job_id,
                    active.attempt_id,
                    active.run_token,
                    status=JobStatus.FAILED,
                    code="service_shutdown",
                    summary="Service stopped while geometry work was running",
                    detail="The API supervisor shut down before the worker completed.",
                    phase="failed",
                    recoverable=True,
                    recommended_action="Retry the operation after the service is ready.",
                    exit_code=active.process.exitcode,
                )
                self._cleanup(active)

    async def _launch_available(self) -> None:
        while len(self.active) < self.settings.worker_concurrency:
            claimed = await asyncio.to_thread(self.repository.claim_one)
            if claimed is None:
                return
            receive_connection, send_connection = self.context.Pipe(duplex=False)
            cancel_event = self.context.Event()
            workdir = Path(
                tempfile.mkdtemp(
                    prefix=f"{claimed['workdirToken']}-",
                    dir=self.settings.jobs_root,
                )
            )
            payload = dict(claimed["payload_json"])
            try:
                await asyncio.to_thread(self._stage_prior_artifacts, payload, workdir)
            except Exception:
                receive_connection.close()
                send_connection.close()
                shutil.rmtree(workdir, ignore_errors=True)
                LOGGER.exception(
                    "prior_artifact_staging_failed", extra={"job_id": str(claimed["id"])}
                )
                await asyncio.to_thread(
                    self.repository.terminalize_job,
                    str(claimed["id"]),
                    str(claimed["attemptId"]),
                    str(claimed["runToken"]),
                    status=JobStatus.FAILED,
                    code="artifact_staging_failed",
                    summary="Prior artifacts could not be staged for export",
                    detail="A referenced content-addressed artifact was missing or unsafe.",
                    phase="finalizing artifacts",
                    recoverable=True,
                    recommended_action="Rebuild the project artifacts and retry export.",
                )
                continue
            process = self.context.Process(
                target=worker_main,
                args=(
                    str(claimed["id"]),
                    str(claimed["kind"]),
                    json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False),
                    str(workdir),
                    send_connection,
                    cancel_event,
                    os.getpid(),
                    float(claimed["timeout_seconds"]),
                    self.settings.worker_memory_mb * 1024 * 1024,
                    self.settings.environment == "production",
                ),
                name=f"mesh2param-{str(claimed['id'])[:8]}",
                daemon=False,
            )
            try:
                process.start()
            except Exception:
                receive_connection.close()
                send_connection.close()
                shutil.rmtree(workdir, ignore_errors=True)
                await asyncio.to_thread(
                    self.repository.terminalize_job,
                    str(claimed["id"]),
                    str(claimed["attemptId"]),
                    str(claimed["runToken"]),
                    status=JobStatus.FAILED,
                    code="worker_start_failed",
                    summary="Geometry worker could not start",
                    detail="The operating system rejected the isolated worker process.",
                    phase="starting worker",
                    recoverable=True,
                    recommended_action="Retry after checking process and memory limits.",
                )
                continue
            send_connection.close()
            active = ActiveJob(
                job_id=str(claimed["id"]),
                project_id=str(claimed["project_id"]),
                kind=str(claimed["kind"]),
                attempt_id=str(claimed["attemptId"]),
                run_token=str(claimed["runToken"]),
                process=process,
                receive_connection=receive_connection,
                cancel_event=cancel_event,
                workdir=workdir,
                payload=payload,
                started_monotonic=time.monotonic(),
                timeout_seconds=float(claimed["timeout_seconds"]),
                max_attempts=int(claimed["max_attempts"]),
                last_heartbeat_monotonic=time.monotonic(),
            )
            self.active[active.job_id] = active
            await asyncio.to_thread(
                self.repository.set_worker_pid,
                active.job_id,
                active.attempt_id,
                active.run_token,
                int(process.pid or 0),
            )

    def _stage_prior_artifacts(self, payload: dict[str, Any], workdir: Path) -> None:
        raw_items = payload.get("priorArtifacts")
        if raw_items is None:
            return
        if not isinstance(raw_items, list) or len(raw_items) > 128:
            raise ValueError("prior artifact list is invalid")
        prior_root = workdir / "prior"
        prior_root.mkdir(mode=0o700)
        staged: list[dict[str, Any]] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                raise ValueError("prior artifact descriptor is invalid")
            name = validate_artifact_name(str(raw.get("name", "")))
            digest = str(raw.get("sha256", ""))
            source = self.storage.path_for(digest)
            source_status = source.lstat()
            if stat.S_ISLNK(source_status.st_mode) or not stat.S_ISREG(source_status.st_mode):
                raise ValueError("prior artifact is not a safe regular file")
            destination = prior_root / name
            try:
                os.link(source, destination, follow_symlinks=False)
            except OSError:
                with (
                    self.storage.open_blob(digest) as source_stream,
                    destination.open("xb") as destination_stream,
                ):
                    shutil.copyfileobj(source_stream, destination_stream)
            staged.append({**raw, "path": f"prior/{name}"})
        payload["priorArtifacts"] = staged

    async def _monitor(self, active: ActiveJob) -> None:
        now = time.monotonic()
        heartbeat_interval = min(5.0, max(0.5, active.timeout_seconds / 4.0))
        if (
            active.process.is_alive()
            and now - active.last_heartbeat_monotonic >= heartbeat_interval
        ):
            await asyncio.to_thread(
                self.repository.touch_heartbeat,
                active.job_id,
                active.attempt_id,
                active.run_token,
            )
            active.last_heartbeat_monotonic = now
        if active.signal_reason is None and not active.terminal_received:
            cancelled = await asyncio.to_thread(
                self.repository.cancellation_requested, active.job_id, active.attempt_id
            )
            if cancelled:
                active.signal_reason = "cancel"
                active.signal_monotonic = now
                active.cancel_event.set()
            elif now - active.started_monotonic >= active.timeout_seconds:
                active.signal_reason = "timeout"
                active.signal_monotonic = now
                active.cancel_event.set()

        await self._drain(active)

        if (
            active.signal_reason is not None
            and active.signal_monotonic is not None
            and time.monotonic() - active.signal_monotonic
            >= self.settings.worker_cancel_grace_seconds
            and active.process.is_alive()
        ):
            await self._force_stop(active)

        if not active.process.is_alive():
            await asyncio.to_thread(active.process.join, 0)
            await self._drain(active)
            if not active.terminal_received:
                await self._terminalize_missing(active)
            self._cleanup(active)

    async def _drain(self, active: ActiveJob) -> None:
        for _ in range(100):
            try:
                if not active.receive_connection.poll():
                    return
                raw = active.receive_connection.recv_bytes(MAX_IPC_BYTES)
                event = decode_event(raw)
            except EOFError:
                return
            except Exception:
                LOGGER.exception("worker_protocol_failure", extra={"job_id": active.job_id})
                active.signal_reason = "protocol"
                active.signal_monotonic = (
                    time.monotonic() - self.settings.worker_cancel_grace_seconds
                )
                active.cancel_event.set()
                return

            if event.internal_traceback:
                LOGGER.error(
                    "geometry_worker_failure",
                    extra={"job_id": active.job_id, "traceback": event.internal_traceback},
                )
            if active.signal_reason == "timeout" and event.type in {
                "completed",
                "cancelled",
                "failed",
            }:
                continue
            if active.signal_reason == "cancel" and event.type == "completed":
                continue
            if event.type in {"progress", "heartbeat", "log"}:
                await asyncio.to_thread(
                    self.repository.apply_worker_event,
                    active.job_id,
                    active.attempt_id,
                    active.run_token,
                    event.model_dump(mode="json", by_alias=True, exclude_none=True),
                )
                continue
            if event.type == "completed":
                try:
                    await self._publish_completed(active, event)
                except RevisionConflictError as exc:
                    await asyncio.to_thread(
                        self.repository.terminalize_job,
                        active.job_id,
                        active.attempt_id,
                        active.run_token,
                        status=JobStatus.FAILED,
                        code="project_revision_conflict",
                        summary="Project changed while the job was running",
                        detail=f"The current project revision is {exc.current_revision}.",
                        phase="finalizing artifacts",
                        recoverable=True,
                        recommended_action=(
                            "Review the newer project state and rerun the operation."
                        ),
                    )
                except Exception:
                    LOGGER.exception("artifact_publication_failed", extra={"job_id": active.job_id})
                    await asyncio.to_thread(
                        self.repository.terminalize_job,
                        active.job_id,
                        active.attempt_id,
                        active.run_token,
                        status=JobStatus.FAILED,
                        code="artifact_publication_failed",
                        summary="Validated worker output could not be published",
                        detail="The service rejected or could not persist a worker artifact.",
                        phase="finalizing artifacts",
                        recoverable=True,
                        recommended_action="Check storage capacity and retry.",
                    )
                active.terminal_received = True
            elif event.type == "cancelled":
                applied = await asyncio.to_thread(
                    self.repository.terminalize_job,
                    active.job_id,
                    active.attempt_id,
                    active.run_token,
                    status=JobStatus.CANCELLED,
                    code="job_cancelled",
                    summary="Job cancelled",
                    detail="Cancellation was acknowledged at a safe worker checkpoint.",
                    phase=event.phase,
                    recoverable=True,
                    recommended_action="Start the operation again when ready.",
                )
                active.terminal_received = bool(applied)
            elif event.type == "failed":
                applied = await asyncio.to_thread(
                    self.repository.terminalize_job,
                    active.job_id,
                    active.attempt_id,
                    active.run_token,
                    status=JobStatus.FAILED,
                    code=event.code or "worker_failed",
                    summary=event.summary or "Geometry worker failed",
                    detail=event.detail or "The worker did not provide additional detail.",
                    phase=event.phase,
                    recoverable=bool(event.recoverable),
                    recommended_action=event.recommended_action,
                )
                active.terminal_received = bool(applied)

    async def _publish_completed(self, active: ActiveJob, event: WorkerEvent) -> None:
        await asyncio.to_thread(self._publish_completed_locked, active, event)

    def _publish_completed_locked(self, active: ActiveJob, event: WorkerEvent) -> None:
        with self.storage.publication_lock():
            self._publish_completed_sync(active, event)

    def _publish_completed_sync(self, active: ActiveJob, event: WorkerEvent) -> None:
        if event.result_file is None:
            raise ValueError("completed event omitted resultFile")
        result_path = self._safe_worker_path(active.workdir, event.result_file)
        status = result_path.lstat()
        if status.st_size > MAX_RESULT_BYTES:
            raise ValueError("worker result file exceeds size limit")
        output = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(output, dict):
            raise ValueError("worker result must be an object")
        result = output.get("result", {})
        state_patch = output.get("statePatch", {})
        raw_artifacts = output.get("artifacts", [])
        if not isinstance(result, dict) or not isinstance(state_patch, dict):
            raise ValueError("worker result/state patch must be objects")
        if not isinstance(raw_artifacts, list) or len(raw_artifacts) > 128:
            raise ValueError("worker artifact list is invalid")

        prepared: list[dict[str, Any]] = []
        for raw_artifact in raw_artifacts:
            if not isinstance(raw_artifact, dict):
                raise ValueError("worker artifact descriptor must be an object")
            name = validate_artifact_name(str(raw_artifact.get("name", "")))
            path = self._safe_worker_path(active.workdir, str(raw_artifact.get("path", "")))
            media_type = str(raw_artifact.get("mediaType", "application/octet-stream"))[:160]
            kind = str(raw_artifact.get("kind", "artifact"))[:40]
            blob = self.storage.put_path(path, max_bytes=2 * 1024**3)
            prepared.append(
                {
                    "name": name,
                    "kind": kind,
                    "sha256": blob.sha256,
                    "byteSize": blob.byte_size,
                    "mediaType": media_type,
                    "storageKey": str(blob.path.relative_to(self.storage.root)),
                    "metadata": {},
                }
            )

        if active.kind == "reconstruct":
            prepared = self._replace_manifest(active, result, state_patch, prepared)
        self.repository.complete_job(
            active.job_id,
            active.attempt_id,
            active.run_token,
            result=result,
            state_patch=state_patch,
            artifacts=prepared,
        )

    def _replace_manifest(
        self,
        active: ActiveJob,
        result: dict[str, Any],
        state_patch: dict[str, Any],
        artifacts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        payload_artifacts = [item for item in artifacts if item["name"] != "manifest.json"]
        source = active.payload.get("source", {})
        manifest = {
            "schemaVersion": "1.0.0",
            "projectId": active.project_id,
            "projectName": active.payload.get("projectName"),
            "modelVersionId": active.payload.get("versionId"),
            "parentVersionId": active.payload.get("parentVersionId"),
            "source": source,
            "internalUnits": active.payload.get("units", "mm"),
            "engineVersion": active.payload.get("engineVersion", "0.1.0"),
            "settings": active.payload.get("settings", {}),
            "schemaVersions": {
                "cadgraph": (
                    state_patch.get("cadgraph", {}).get("schemaVersion")
                    if isinstance(state_patch.get("cadgraph"), dict)
                    else None
                ),
                "manifest": "1.0.0",
            },
            "dependencyVersions": (
                state_patch.get("cadgraph", {}).get("engineVersions", {})
                if isinstance(state_patch.get("cadgraph"), dict)
                else {}
            ),
            "validation": state_patch.get("validation"),
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "artifacts": [
                {
                    "name": item["name"],
                    "sha256": item["sha256"],
                    "byteSize": item["byteSize"],
                    "mediaType": item["mediaType"],
                }
                for item in sorted(payload_artifacts, key=lambda entry: str(entry["name"]))
            ],
        }
        manifest_path = active.workdir / "manifest.service.json"
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        blob = self.storage.put_path(manifest_path)
        payload_artifacts.append(
            {
                "name": "manifest.json",
                "kind": "manifest",
                "sha256": blob.sha256,
                "byteSize": blob.byte_size,
                "mediaType": "application/json",
                "storageKey": str(blob.path.relative_to(self.storage.root)),
                "metadata": {"scope": "payload-artifacts"},
            }
        )
        result["manifestSha256"] = blob.sha256
        return payload_artifacts

    def _safe_worker_path(self, workdir: Path, relative: str) -> Path:
        candidate_relative = Path(relative)
        if not relative or candidate_relative.is_absolute() or ".." in candidate_relative.parts:
            raise ValueError("unsafe worker output path")
        candidate = (workdir / candidate_relative).resolve()
        try:
            candidate.relative_to(workdir.resolve())
        except ValueError as exc:
            raise ValueError("worker output escaped its attempt directory") from exc
        file_status = candidate.lstat()
        if stat.S_ISLNK(file_status.st_mode) or not stat.S_ISREG(file_status.st_mode):
            raise ValueError("worker output is not a safe regular file")
        return candidate

    async def _terminalize_missing(self, active: ActiveJob) -> None:
        if active.signal_reason == "cancel":
            await asyncio.to_thread(
                self.repository.terminalize_job,
                active.job_id,
                active.attempt_id,
                active.run_token,
                status=JobStatus.CANCELLED,
                code="job_cancelled",
                summary="Job cancelled",
                detail="The worker was stopped after the cancellation grace period.",
                phase="cancelled",
                recoverable=True,
                recommended_action="Start the operation again when ready.",
                exit_code=active.process.exitcode,
            )
        elif active.signal_reason == "timeout":
            await asyncio.to_thread(
                self.repository.terminalize_job,
                active.job_id,
                active.attempt_id,
                active.run_token,
                status=JobStatus.FAILED,
                code="worker_timeout",
                summary="Geometry worker timed out",
                detail=f"The job exceeded its {active.timeout_seconds:g} second timeout.",
                phase="failed",
                recoverable=True,
                recommended_action="Reduce input complexity or reconstruction search bounds.",
                exit_code=active.process.exitcode,
            )
        elif active.signal_reason == "protocol" or active.process.exitcode == 0:
            await asyncio.to_thread(
                self.repository.terminalize_job,
                active.job_id,
                active.attempt_id,
                active.run_token,
                status=JobStatus.FAILED,
                code="worker_protocol_error",
                summary="Geometry worker protocol failed",
                detail="The worker exited without a valid terminal event.",
                phase="failed",
                recoverable=True,
                recommended_action="Retry the operation.",
                exit_code=active.process.exitcode,
            )
        else:
            await asyncio.to_thread(
                self.repository.retry_or_fail_crash,
                active.job_id,
                active.attempt_id,
                active.run_token,
                exit_code=active.process.exitcode,
            )

    async def _force_stop(self, active: ActiveJob) -> None:
        active.cancel_event.set()
        if active.process.is_alive():
            active.process.terminate()
            await asyncio.to_thread(
                active.process.join, self.settings.worker_cancel_grace_seconds
            )
        if active.process.is_alive():
            active.process.kill()
            await asyncio.to_thread(
                active.process.join, self.settings.worker_cancel_grace_seconds
            )

    def _cleanup(self, active: ActiveJob) -> None:
        active.receive_connection.close()
        shutil.rmtree(active.workdir, ignore_errors=True)
        self.active.pop(active.job_id, None)


__all__ = ["JobSupervisor"]
