from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse

from ...db import Repository
from ...schemas import (
    ProjectCreate,
    ProjectEnvelope,
    ProjectListEnvelope,
    ProjectPatch,
)
from ..core import parse_if_match, request_id, revision_headers, success
from ..dependencies import repository

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", status_code=201, response_model=ProjectEnvelope)
def create_project(
    request: Request,
    body: ProjectCreate,
    repo: Repository = Depends(repository),
) -> JSONResponse:
    project = repo.create_project(body.name, body.units)
    repo.record_audit(
        request_id(request), "project.create", "success", project_id=project["id"]
    )
    return success(
        request,
        project,
        status_code=201,
        headers={
            "Location": f"/api/projects/{project['id']}",
            **revision_headers(int(project["revision"])),
        },
    )


@router.get("", response_model=ProjectListEnvelope)
def list_projects(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repo: Repository = Depends(repository),
) -> JSONResponse:
    projects = repo.list_projects(limit=limit, offset=offset)
    total = repo.count_projects()
    return success(request, {
        "items": projects, "total": total, "limit": limit, "offset": offset,
        "hasMore": offset + len(projects) < total,
    })


@router.get("/{project_id}", response_model=ProjectEnvelope)
def get_project(
    request: Request,
    project_id: str,
    repo: Repository = Depends(repository),
) -> JSONResponse:
    project = repo.get_project(project_id)
    return success(
        request,
        project,
        headers=revision_headers(int(project["revision"])),
    )


@router.patch("/{project_id}", response_model=ProjectEnvelope)
def patch_project(
    request: Request,
    project_id: str,
    body: ProjectPatch,
    if_match: str | None = Header(default=None, alias="If-Match"),
    repo: Repository = Depends(repository),
) -> JSONResponse:
    project = repo.update_project(
        project_id,
        parse_if_match(if_match),
        name=body.name,
        units=body.units,
    )
    repo.record_audit(
        request_id(request), "project.update", "success", project_id=project_id
    )
    return success(
        request,
        project,
        headers=revision_headers(int(project["revision"])),
    )


@router.delete("/{project_id}", status_code=204)
def delete_project(
    request: Request,
    project_id: str,
    if_match: str | None = Header(default=None, alias="If-Match"),
    repo: Repository = Depends(repository),
) -> Response:
    expected = parse_if_match(if_match)
    current = repo.get_project(project_id)
    if int(current["revision"]) != expected:
        from ...db.repository import RevisionConflictError

        raise RevisionConflictError(int(current["revision"]))
    repo.record_audit(
        request_id(request), "project.delete", "success", project_id=project_id
    )
    repo.delete_project(project_id)
    return Response(status_code=204)


__all__ = ["router"]
