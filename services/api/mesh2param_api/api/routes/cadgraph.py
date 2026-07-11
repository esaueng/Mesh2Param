from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from mesh2param_contracts import CADGraph

from ...config import Settings
from ...db import Repository
from ...schemas import CadgraphUpdate
from ..core import APIError, parse_if_match, request_id, revision_headers, success
from ..dependencies import repository, settings

router = APIRouter(prefix="/api/projects/{project_id}/cadgraph", tags=["cadgraph"])


@router.get("")
def get_cadgraph(
    request: Request,
    project_id: str,
    repo: Repository = Depends(repository),
) -> JSONResponse:
    revision, document = repo.get_state(project_id)
    graph = document.get("cadgraph")
    if not isinstance(graph, dict):
        raise APIError(
            404,
            "cadgraph_not_found",
            "CADGraph is not available",
            "The project has not produced or imported a CADGraph.",
            project_id=project_id,
            recoverable=True,
        )
    return success(request, graph, headers=revision_headers(revision))


@router.patch("")
def patch_cadgraph(
    request: Request,
    project_id: str,
    body: CadgraphUpdate,
    if_match: str | None = Header(default=None, alias="If-Match"),
    repo: Repository = Depends(repository),
    config: Settings = Depends(settings),
) -> JSONResponse:
    expected = parse_if_match(if_match)
    graph = CADGraph.model_validate(body.cadgraph)
    if len(graph.features) > config.max_operation_count:
        raise APIError(
            422,
            "operation_limit",
            "CADGraph operation limit exceeded",
            f"The graph exceeds the configured {config.max_operation_count} feature limit.",
            project_id=project_id,
        )
    _, document = repo.get_state(project_id)
    document["cadgraph"] = graph.model_dump(mode="json", by_alias=True)
    document["validation"] = {
        "status": "not-run",
        "brepValid": False,
        "stepReimportValid": False,
        "toleranceSatisfied": False,
        "issues": [],
    }
    revision, updated = repo.replace_state(project_id, expected, document)
    repo.record_audit(
        request_id(request), "cadgraph.update", "success", project_id=project_id
    )
    return success(
        request,
        updated["cadgraph"],
        headers=revision_headers(revision),
    )


__all__ = ["router"]
