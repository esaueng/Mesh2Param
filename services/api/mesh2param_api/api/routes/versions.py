from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse

from ...db import Repository
from ...schemas import VersionCreate, VersionEnvelope, VersionListEnvelope
from ..core import parse_if_match, request_id, revision_headers, success
from ..dependencies import repository

router = APIRouter(prefix="/api/projects/{project_id}/versions", tags=["versions"])


@router.get("", response_model=VersionListEnvelope)
def list_versions(
    request: Request,
    project_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repo: Repository = Depends(repository),
) -> JSONResponse:
    versions = repo.list_versions(project_id, limit=limit, offset=offset)
    total = repo.count_versions(project_id)
    return success(request, {
        "items": versions, "total": total, "limit": limit, "offset": offset,
        "hasMore": offset + len(versions) < total,
    })


@router.post("", status_code=201, response_model=VersionEnvelope)
def create_version(
    request: Request,
    project_id: str,
    body: VersionCreate,
    if_match: str | None = Header(default=None, alias="If-Match"),
    repo: Repository = Depends(repository),
) -> JSONResponse:
    expected = parse_if_match(if_match)
    current, _ = repo.get_state(project_id)
    if current != expected:
        from ...db.repository import RevisionConflictError

        raise RevisionConflictError(current)
    version = repo.create_version(project_id, body.label)
    revision, _ = repo.get_state(project_id)
    repo.record_audit(
        request_id(request), "version.create", "success", project_id=project_id
    )
    return success(
        request,
        version,
        status_code=201,
        headers={
            "Location": f"/api/projects/{project_id}/versions/{version['id']}",
            **revision_headers(revision),
        },
    )


@router.get("/{version_id}", response_model=VersionEnvelope)
def get_version(
    request: Request,
    project_id: str,
    version_id: str,
    repo: Repository = Depends(repository),
) -> JSONResponse:
    return success(request, repo.get_version(project_id, version_id))


@router.post("/{version_id}/restore")
def restore_version(
    request: Request,
    project_id: str,
    version_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    repo: Repository = Depends(repository),
) -> JSONResponse:
    revision, document = repo.restore_version(
        project_id, version_id, parse_if_match(if_match)
    )
    repo.record_audit(
        request_id(request), "version.restore", "success", project_id=project_id
    )
    return success(
        request,
        {"revision": revision, "state": document, "restoredVersionId": version_id},
        status_code=201,
        headers=revision_headers(revision),
    )


@router.delete("/{version_id}", status_code=204)
def delete_version(
    request: Request,
    project_id: str,
    version_id: str,
    repo: Repository = Depends(repository),
) -> Response:
    repo.delete_version(project_id, version_id)
    repo.record_audit(
        request_id(request), "version.delete", "success", project_id=project_id
    )
    return Response(status_code=204)


__all__ = ["router"]
