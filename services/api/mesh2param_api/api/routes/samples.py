from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from mesh2param.samples import SAMPLE_SPECS, sample_spec

from ...config import Settings
from ...db import Repository
from ..core import APIError, request_id, success
from ..dependencies import repository, settings

router = APIRouter(prefix="/api/samples", tags=["samples"])


@router.get("")
def list_samples(request: Request) -> JSONResponse:
    items = [
        {
            "id": spec.slug,
            "name": spec.name,
            "seed": spec.seed,
            "expectedBoundingBox": list(spec.expected_bbox),
            "expectedVolume": spec.expected_volume,
            "expectedPlanarFaces": spec.expected_planar_faces,
            "expectedCylindricalFaces": spec.expected_cylindrical_faces,
        }
        for spec in SAMPLE_SPECS
    ]
    return success(request, {"items": items, "total": len(items)})


@router.post("/{sample_id}/open", status_code=202)
def open_sample(
    request: Request,
    sample_id: str,
    repo: Repository = Depends(repository),
    config: Settings = Depends(settings),
) -> JSONResponse:
    try:
        spec = sample_spec(sample_id)
    except KeyError as exc:
        raise APIError(
            404,
            "sample_not_found",
            "Sample not found",
            f"No bundled sample has the identifier {sample_id!r}.",
            recoverable=False,
        ) from exc
    project = repo.create_project(spec.name, "mm")
    payload = {
        "projectId": project["id"],
        "projectName": project["name"],
        "sampleId": sample_id,
        "inputHash": f"sample:{sample_id}:{spec.seed}",
        "deterministicSeed": spec.seed,
        "settings": {},
    }
    job = repo.create_job(
        str(project["id"]),
        int(project["revision"]),
        "sample_open",
        payload,
        timeout_seconds=config.worker_timeout_seconds,
        max_attempts=2,
    )
    repo.record_audit(
        request_id(request),
        "sample.open",
        "accepted",
        project_id=str(project["id"]),
        job_id=str(job["id"]),
        details={"sampleId": sample_id},
    )
    return success(
        request,
        {"project": project, "job": job},
        status_code=202,
        headers={
            "Location": f"/api/jobs/{job['id']}",
            "Content-Location": f"/api/projects/{project['id']}",
        },
    )


__all__ = ["router"]
