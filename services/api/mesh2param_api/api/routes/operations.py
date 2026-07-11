from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Body, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from mesh2param import __version__ as engine_version
from mesh2param_contracts import content_sha256

from ...config import Settings
from ...db import Repository
from ...schemas import JobEnvelope, OperationRequest, UploadEnvelope
from ...security import UploadLimits, preflight_mesh_upload
from ...storage import ByteLimitExceeded, LocalCAS, validate_display_filename
from ..core import APIError, parse_if_match, request_id, success
from ..dependencies import repository, settings, storage

router = APIRouter(prefix="/api/projects/{project_id}", tags=["operations"])
OperationName = Literal["repair", "analyze", "reconstruct", "rebuild", "validate", "export"]


def _job_response(request: Request, job: dict[str, object]) -> JSONResponse:
    job_id = str(job["id"])
    return success(
        request,
        job,
        status_code=202,
        headers={"Location": f"/api/jobs/{job_id}"},
    )


def _operation_payload(
    project: dict[str, object], operation: OperationName, body: OperationRequest, store: LocalCAS
) -> dict[str, object]:
    state = project["state"]
    if not isinstance(state, dict):
        raise APIError(
            500,
            "invalid_project_state",
            "Project state is invalid",
            "State is not an object.",
        )
    payload: dict[str, object] = {
        "projectId": project["id"],
        "projectName": project["name"],
        "units": project["units"],
        "projectState": state,
        "settings": body.settings,
        "engineVersion": engine_version,
        "deterministicSeed": 0,
        "timestamp": project.get("updatedAt") or project.get("createdAt"),
    }
    source = state.get("source")
    if operation in {"repair", "analyze", "reconstruct"}:
        if not isinstance(source, dict) or not isinstance(source.get("sha256"), str):
            raise APIError(
                409,
                "source_required",
                "Source mesh is required",
                "Upload and validate a source mesh before starting this operation.",
                project_id=str(project["id"]),
                recoverable=True,
                recommended_action="Upload an STL, OBJ, or PLY source mesh.",
            )
        digest = str(source["sha256"])
        if not store.contains(digest):
            raise APIError(
                409,
                "source_missing",
                "Source mesh blob is missing",
                "The preserved source content is not available in local storage.",
                project_id=str(project["id"]),
                recoverable=True,
                recommended_action="Re-upload the unchanged source mesh.",
            )
        payload.update(
            {
                "source": source,
                "sourcePath": str(store.path_for(digest)),
                "inputHash": digest,
            }
        )
    else:
        cadgraph = state.get("cadgraph")
        if not isinstance(cadgraph, dict):
            raise APIError(
                409,
                "cadgraph_required",
                "CADGraph is required",
                "Reconstruct, restore, or provide a CADGraph before this operation.",
                project_id=str(project["id"]),
                recoverable=True,
            )
        payload["cadgraph"] = cadgraph
        identity: dict[str, object] = {"cadgraph": cadgraph}
        if operation == "export":
            identity["projectState"] = state
        payload["inputHash"] = content_sha256(identity)
        payload["source"] = source
        payload["versionId"] = state.get("currentVersionId")
    return payload


def _enqueue(
    request: Request,
    project_id: str,
    operation: OperationName,
    body: OperationRequest,
    if_match: str | None,
    repo: Repository,
    config: Settings,
    store: LocalCAS,
) -> JSONResponse:
    expected_revision = parse_if_match(if_match)
    project = repo.get_project(project_id)
    if int(project["revision"]) != expected_revision:
        from ...db.repository import RevisionConflictError

        raise RevisionConflictError(int(project["revision"]))
    payload = _operation_payload(project, operation, body, store)
    if operation == "export":
        payload["priorArtifacts"] = [
            {
                "name": item["name"],
                "kind": item["kind"],
                "sha256": item["sha256"],
                "mediaType": item["mediaType"],
            }
            for item in repo.list_artifacts(project_id)
            if item["name"]
            not in {"manifest.json", "mesh2param-export.zip", "project.mesh2param.json"}
        ]
    payload["limits"] = {
        "maxFileBytes": config.max_upload_bytes,
        "maxTriangles": config.max_triangles,
        "maxVertices": config.max_vertices,
        "maxAbsCoordinate": config.max_abs_coordinate,
    }
    graph = payload.get("cadgraph")
    if (
        isinstance(graph, dict)
        and isinstance(graph.get("features"), list)
        and len(graph["features"]) > config.max_operation_count
    ):
        raise APIError(
            422,
            "operation_limit",
            "CADGraph operation limit exceeded",
            f"The graph exceeds the configured {config.max_operation_count} feature limit.",
            project_id=project_id,
        )
    job = repo.create_job(
        project_id,
        expected_revision,
        operation,
        payload,
        timeout_seconds=body.timeout_seconds or config.worker_timeout_seconds,
        max_attempts=2,
    )
    repo.record_audit(
        request_id(request),
        f"job.{operation}.enqueue",
        "success",
        project_id=project_id,
        job_id=str(job["id"]),
    )
    return _job_response(request, job)


@router.post(
    "/upload",
    status_code=202,
    response_model=UploadEnvelope,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def upload_source(
    request: Request,
    project_id: str,
    filename: str | None = Query(default=None),
    units: Literal["mm", "cm", "m", "in", "ft"] = Query(default="mm"),
    units_confirmed: bool = Query(default=False, alias="unitsConfirmed"),
    scale_factor: float = Query(default=1.0, gt=0, le=1_000_000, alias="scaleFactor"),
    upload_filename: str | None = Header(default=None, alias="X-Mesh2Param-Filename"),
    if_match: str | None = Header(default=None, alias="If-Match"),
    repo: Repository = Depends(repository),
    config: Settings = Depends(settings),
    store: LocalCAS = Depends(storage),
) -> JSONResponse:
    expected_revision = parse_if_match(if_match)
    if not units_confirmed:
        raise APIError(
            422,
            "units_confirmation_required",
            "Source units must be confirmed",
            "Mesh formats do not reliably encode units; confirm the selected units explicitly.",
            project_id=project_id,
            recoverable=True,
        )
    display_filename = validate_display_filename(
        upload_filename or filename or "", allowed_extensions={".stl", ".obj", ".ply"}
    )
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise APIError(
                400,
                "invalid_content_length",
                "Invalid Content-Length",
                "Content-Length must be an integer.",
            ) from exc
        if declared_length > config.max_upload_bytes:
            raise APIError(
                413,
                "file_too_large",
                "Upload exceeds the file-size limit",
                f"The configured upload limit is {config.max_upload_mb} MiB.",
                project_id=project_id,
            )

    staging_root = config.resolved_data_dir / "upload-staging"
    staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, staging_name = tempfile.mkstemp(prefix="upload-", suffix=".part", dir=staging_root)
    staging_path = Path(staging_name)
    observed = 0
    try:
        with os.fdopen(descriptor, "wb") as destination:
            async for chunk in request.stream():
                observed += len(chunk)
                if observed > config.max_upload_bytes:
                    raise ByteLimitExceeded(
                        limit_bytes=config.max_upload_bytes, observed_bytes=observed
                    )
                await asyncio.to_thread(destination.write, chunk)
            await asyncio.to_thread(destination.flush)
            await asyncio.to_thread(os.fsync, destination.fileno())
        preflight = await asyncio.to_thread(
            preflight_mesh_upload,
            staging_path,
            display_filename,
            limits=UploadLimits(
                max_bytes=config.max_upload_bytes,
                max_triangles=config.max_triangles,
                max_vertices=config.max_vertices,
                max_coordinate_magnitude=config.max_abs_coordinate,
            ),
        )
        blob = await asyncio.to_thread(
            store.put_path, staging_path, max_bytes=config.max_upload_bytes
        )
        if blob.sha256 != preflight.sha256:
            raise APIError(
                500,
                "upload_hash_mismatch",
                "Upload integrity check failed",
                "The staged upload changed between validation and publication.",
                project_id=project_id,
            )
        source_document, source_revision = await asyncio.to_thread(
            repo.create_source_asset,
            project_id,
            expected_revision,
            original_filename=display_filename,
            format_name=preflight.format,
            encoding=preflight.encoding,
            blob={
                "sha256": blob.sha256,
                "byteSize": blob.byte_size,
                "mediaType": f"model/{preflight.format}",
                "storageKey": str(blob.path.relative_to(store.root)),
            },
            declared_units=units,
            units_confirmed=True,
            scale_factor=scale_factor,
        )
        payload = {
            "projectId": project_id,
            "units": units,
            "source": source_document,
            "sourcePath": str(store.path_for(blob.sha256)),
            "inputHash": blob.sha256,
            "limits": {
                "maxFileBytes": config.max_upload_bytes,
                "maxTriangles": config.max_triangles,
                "maxVertices": config.max_vertices,
                "maxAbsCoordinate": config.max_abs_coordinate,
            },
            "settings": {},
        }
        job = await asyncio.to_thread(
            repo.create_job,
            project_id,
            source_revision,
            "upload",
            payload,
            timeout_seconds=config.worker_timeout_seconds,
            max_attempts=1,
        )
        await asyncio.to_thread(
            repo.record_audit,
            request_id(request),
            "source.upload",
            "accepted",
            project_id=project_id,
            job_id=str(job["id"]),
            details={
                "sha256": blob.sha256,
                "byteSize": blob.byte_size,
                "format": preflight.format,
            },
        )
        return success(
            request,
            {"source": source_document, "job": job, "revision": source_revision},
            status_code=202,
            headers={"Location": f"/api/jobs/{job['id']}"},
        )
    finally:
        staging_path.unlink(missing_ok=True)


def _operation_route(operation: OperationName) -> Callable[..., JSONResponse]:
    def route(
        request: Request,
        project_id: str,
        body: OperationRequest = Body(default_factory=OperationRequest),
        if_match: str | None = Header(default=None, alias="If-Match"),
        repo: Repository = Depends(repository),
        config: Settings = Depends(settings),
        store: LocalCAS = Depends(storage),
    ) -> JSONResponse:
        return _enqueue(
            request, project_id, operation, body, if_match, repo, config, store
        )

    route.__name__ = f"{operation}_project"
    return route


OPERATIONS: tuple[OperationName, ...] = (
    "repair",
    "analyze",
    "reconstruct",
    "rebuild",
    "validate",
    "export",
)


for _operation in OPERATIONS:
    router.add_api_route(
        f"/{_operation}",
        _operation_route(_operation),
        methods=["POST"],
        status_code=202,
        response_model=JobEnvelope,
        tags=["operations"],
    )


__all__ = ["router"]
