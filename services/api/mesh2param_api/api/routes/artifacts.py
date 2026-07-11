from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ...db import Repository
from ...schemas import ArtifactListEnvelope
from ...security import attachment_content_disposition
from ...storage import LocalCAS, validate_artifact_name
from ..core import APIError, success
from ..dependencies import repository, storage

router = APIRouter(prefix="/api/projects/{project_id}/artifacts", tags=["artifacts"])


@router.get("", response_model=ArtifactListEnvelope)
def list_artifacts(
    request: Request,
    project_id: str,
    repo: Repository = Depends(repository),
) -> JSONResponse:
    artifacts = repo.list_artifacts(project_id)
    return success(request, {"items": artifacts, "total": len(artifacts)})


@router.get("/{name}")
def download_artifact(
    project_id: str,
    name: str,
    repo: Repository = Depends(repository),
    store: LocalCAS = Depends(storage),
) -> StreamingResponse:
    logical_name = validate_artifact_name(name)
    artifact = repo.get_artifact(project_id, logical_name)
    digest = str(artifact["sha256"])
    if not store.contains(digest):
        raise APIError(
            410,
            "artifact_blob_missing",
            "Artifact content is unavailable",
            "The artifact metadata exists but its immutable blob is missing.",
            project_id=project_id,
            recoverable=True,
            recommended_action="Rerun the operation that produced this artifact.",
        )
    def content() -> Iterator[bytes]:
        with store.open_blob(digest) as source:
            while chunk := source.read(1024 * 1024):
                yield chunk

    return StreamingResponse(
        content(),
        media_type=str(artifact["mediaType"]),
        headers={
            "Content-Disposition": attachment_content_disposition(logical_name),
            "Content-Length": str(artifact["byteSize"]),
            "ETag": f'"sha256-{digest}"',
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )


__all__ = ["router"]
