from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from mesh2param.samples import SAMPLE_SPECS, SampleSpec, sample_spec

from ...config import Settings
from ...db import Repository
from ..core import APIError, request_id, success
from ..dependencies import repository, settings

router = APIRouter(prefix="/api/samples", tags=["samples"])

_OPERATION_LABELS = {
    "extrusion": "Extrusion",
    "pocket": "Pocket",
    "hole": "Hole",
    "counterbore": "Counterbore",
    "countersink": "Countersink",
    "revolution": "Revolution",
    "linearPattern": "Linear pattern",
    "circularPattern": "Circular pattern",
    "mirror": "Mirror",
    "chamfer": "Chamfer",
    "fillet": "Fillet",
    "importedFaceted": "Imported faceted fallback",
}
_MAX_SAMPLE_JSON_BYTES = 2 * 1024 * 1024
_MAX_THUMBNAIL_BYTES = 1024 * 1024


def _require_sample(sample_id: str) -> SampleSpec:
    try:
        return sample_spec(sample_id)
    except KeyError as exc:
        raise APIError(
            404,
            "sample_not_found",
            "Sample not found",
            f"No bundled sample has the identifier {sample_id!r}.",
            recoverable=False,
        ) from exc


def _generated_samples_root() -> Path:
    candidates = [
        *(parent / "samples" / "generated" for parent in Path(__file__).resolve().parents),
        Path.cwd() / "samples" / "generated",
    ]
    for candidate in candidates:
        try:
            if candidate.is_dir():
                return candidate.resolve(strict=True)
        except OSError:
            continue
    raise APIError(
        503,
        "sample_artifacts_unavailable",
        "Bundled samples are unavailable",
        "The generated sample artifact directory is not available to the API process.",
        recoverable=True,
        recommended_action="Regenerate or restore the bundled sample corpus.",
    )


def _sample_artifact(spec: SampleSpec, name: str) -> Path:
    root = _generated_samples_root()
    sample_directory = root / spec.slug
    candidate = sample_directory / name
    try:
        directory_status = sample_directory.lstat()
        candidate_status = candidate.lstat()
        if stat.S_ISLNK(directory_status.st_mode) or not stat.S_ISDIR(directory_status.st_mode):
            raise OSError("sample directory is not a safe directory")
        if stat.S_ISLNK(candidate_status.st_mode) or not stat.S_ISREG(candidate_status.st_mode):
            raise OSError("sample artifact is not a safe regular file")
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
        return resolved
    except (OSError, ValueError) as exc:
        raise APIError(
            503,
            "sample_artifact_unavailable",
            "Bundled sample artifact is unavailable",
            "A required generated sample artifact is missing or unsafe.",
            recoverable=True,
            recommended_action="Regenerate or restore the bundled sample corpus.",
        ) from exc


def _read_sample_json(spec: SampleSpec, name: str) -> dict[str, Any]:
    path = _sample_artifact(spec, name)
    try:
        if path.stat().st_size > _MAX_SAMPLE_JSON_BYTES:
            raise ValueError("sample metadata exceeds size limit")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("sample metadata is not an object")
        return value
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise APIError(
            500,
            "sample_metadata_invalid",
            "Bundled sample metadata is invalid",
            "A generated sample metadata document could not be validated.",
            recoverable=False,
        ) from exc


def _sample_catalog_entry(spec: SampleSpec) -> dict[str, Any]:
    metadata = _read_sample_json(spec, "metadata.json")
    graph = _read_sample_json(spec, "model.cadgraph.json")
    try:
        meshes = metadata["meshes"]
        high_mesh = meshes["high"] if isinstance(meshes, dict) else None
        triangle_count = high_mesh["triangleCount"] if isinstance(high_mesh, dict) else None
        tolerance = graph["projectTolerance"]
        tolerance_mm = tolerance["surfaceDeviation"] if isinstance(tolerance, dict) else None
        features = graph["features"]
        if (
            not isinstance(triangle_count, int)
            or isinstance(triangle_count, bool)
            or triangle_count < 1
            or not isinstance(tolerance_mm, int | float)
            or isinstance(tolerance_mm, bool)
            or float(tolerance_mm) <= 0
            or not isinstance(features, list)
        ):
            raise ValueError("sample presentation metadata is malformed")
        operations: list[str] = []
        for feature in features:
            if not isinstance(feature, dict) or not isinstance(feature.get("operation"), str):
                raise ValueError("sample feature operation is malformed")
            operation = str(feature["operation"])
            if operation not in operations:
                operations.append(operation)
        intended_operations = [
            _OPERATION_LABELS.get(operation, operation) for operation in operations
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise APIError(
            500,
            "sample_metadata_invalid",
            "Bundled sample metadata is invalid",
            "A generated sample is missing required presentation metadata.",
            recoverable=False,
        ) from exc
    return {
        "id": spec.slug,
        "name": spec.name,
        "seed": spec.seed,
        "expectedBoundingBox": list(spec.expected_bbox),
        "expectedVolume": spec.expected_volume,
        "expectedPlanarFaces": spec.expected_planar_faces,
        "expectedCylindricalFaces": spec.expected_cylindrical_faces,
        "triangleCount": triangle_count,
        "intendedOperations": intended_operations,
        "toleranceMm": float(tolerance_mm),
        "thumbnailUrl": f"/api/samples/{spec.slug}/thumbnail",
    }


@router.get("")
def list_samples(request: Request) -> JSONResponse:
    items = [_sample_catalog_entry(spec) for spec in SAMPLE_SPECS]
    return success(request, {"items": items, "total": len(items)})


@router.get("/{sample_id}/thumbnail")
def sample_thumbnail(sample_id: str) -> Response:
    spec = _require_sample(sample_id)
    path = _sample_artifact(spec, "thumbnail.svg")
    try:
        if path.stat().st_size > _MAX_THUMBNAIL_BYTES:
            raise OSError("thumbnail exceeds size limit")
        content = path.read_bytes()
    except OSError as exc:
        raise APIError(
            503,
            "sample_artifact_unavailable",
            "Bundled sample thumbnail is unavailable",
            "The generated sample thumbnail could not be read safely.",
            recoverable=True,
        ) from exc
    digest = hashlib.sha256(content).hexdigest()
    return Response(
        content=content,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
            "ETag": f'"sha256-{digest}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{sample_id}/open", status_code=202)
def open_sample(
    request: Request,
    sample_id: str,
    repo: Repository = Depends(repository),
    config: Settings = Depends(settings),
) -> JSONResponse:
    spec = _require_sample(sample_id)
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
