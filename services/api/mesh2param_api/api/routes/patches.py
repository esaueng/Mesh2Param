from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from ...db import Repository
from ...schemas import (
    PatchEnvelope,
    PatchListEnvelope,
    PatchMergeRequest,
    PatchSplitRequest,
    PatchUpdate,
)
from ..core import APIError, parse_if_match, request_id, revision_headers, success
from ..dependencies import repository

router = APIRouter(prefix="/api/projects/{project_id}/patches", tags=["patches"])


def _patches(
    repo: Repository, project_id: str
) -> tuple[int, dict[str, Any], list[dict[str, Any]]]:
    revision, document = repo.get_state(project_id)
    raw = document.get("patches", [])
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise APIError(
            500,
            "invalid_patch_state",
            "Patch state is invalid",
            "The authoritative patch collection is malformed.",
            project_id=project_id,
        )
    return revision, document, raw


def _apply_smooth_boundaries(
    patch: dict[str, Any],
    requested: list[str],
    patches: list[dict[str, Any]],
    project_id: str,
) -> None:
    """Replace a patch's smooth-boundary declarations, mirrored symmetrically.

    A smooth join is a property of the shared boundary, so the neighbor's own
    list is kept in sync: reading either patch shows the same declaration and
    the reconstruction sees one consistent pair.
    """

    by_id = {item.get("id"): item for item in patches}
    neighbor_ids = set(patch.get("neighborIds", []))
    current = set(patch.get("smoothBoundaryIds", []))
    changed = set(requested) ^ current
    for neighbor_id in sorted(set(requested)):
        if neighbor_id not in by_id or neighbor_id not in neighbor_ids:
            raise APIError(
                422,
                "invalid_boundary_override",
                "Boundary override references a non-neighbor",
                f"Patch {neighbor_id!r} does not share a boundary with this patch.",
                project_id=project_id,
                recoverable=True,
            )
    locked = [
        item
        for item in [patch, *(by_id[n] for n in sorted(changed) if n in by_id)]
        if item.get("locked")
    ]
    if locked:
        raise APIError(
            409,
            "patch_locked",
            "Patch is locked",
            "Unlock both sides of the boundary before changing its continuity.",
            project_id=project_id,
            recoverable=True,
        )
    patch["smoothBoundaryIds"] = sorted(requested)
    patch_id = patch.get("id")
    for neighbor_id in sorted(changed):
        neighbor = by_id.get(neighbor_id)
        if neighbor is None:
            continue
        mirrored = set(neighbor.get("smoothBoundaryIds", []))
        if neighbor_id in requested:
            mirrored.add(patch_id)
        else:
            mirrored.discard(patch_id)
        neighbor["smoothBoundaryIds"] = sorted(mirrored)


@router.get("", response_model=PatchListEnvelope)
def get_patches(
    request: Request,
    project_id: str,
    repo: Repository = Depends(repository),
) -> JSONResponse:
    revision, _, patches = _patches(repo, project_id)
    return success(
        request,
        {"items": patches, "total": len(patches)},
        headers=revision_headers(revision),
    )


@router.patch("/{patch_id}", response_model=PatchEnvelope)
def update_patch(
    request: Request,
    project_id: str,
    patch_id: str,
    body: PatchUpdate,
    if_match: str | None = Header(default=None, alias="If-Match"),
    repo: Repository = Depends(repository),
) -> JSONResponse:
    expected = parse_if_match(if_match)
    _, document, patches = _patches(repo, project_id)
    patch = next((item for item in patches if item.get("id") == patch_id), None)
    if patch is None:
        raise APIError(
            404,
            "patch_not_found",
            "Patch not found",
            "No patch has this identifier.",
            project_id=project_id,
        )
    if body.name is not None:
        patch["name"] = body.name
    if body.hidden is not None:
        patch["hidden"] = body.hidden
    if body.locked is not None:
        patch["locked"] = body.locked
    if body.classification is not None:
        patch["type"] = body.classification
        patch["userOverriddenClassification"] = True
    if body.parameters is not None:
        patch["fit"] = body.parameters
        patch["userOverriddenClassification"] = True
    if body.smooth_boundary_ids is not None:
        _apply_smooth_boundaries(patch, sorted(set(body.smooth_boundary_ids)), patches, project_id)
    revision, _ = repo.replace_state(project_id, expected, document)
    repo.record_audit(
        request_id(request), "patch.update", "success", project_id=project_id
    )
    return success(request, patch, headers=revision_headers(revision))


@router.post("/merge", response_model=PatchEnvelope)
def merge_patches(
    request: Request,
    project_id: str,
    body: PatchMergeRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
    repo: Repository = Depends(repository),
) -> JSONResponse:
    expected = parse_if_match(if_match)
    _, document, patches = _patches(repo, project_id)
    selected = [item for item in patches if item.get("id") in body.patch_ids]
    if len(selected) != 2:
        raise APIError(
            404,
            "patch_not_found",
            "Patch not found",
            "Both patch IDs must exist.",
            project_id=project_id,
        )
    if selected[0].get("locked") or selected[1].get("locked"):
        raise APIError(
            409,
            "patch_locked",
            "Patch is locked",
            "Unlock both patches before merging.",
            project_id=project_id,
            recoverable=True,
        )
    if (
        selected[0].get("type") != selected[1].get("type")
        or selected[0].get("fit") != selected[1].get("fit")
    ):
        raise APIError(
            422,
            "incompatible_patches",
            "Patches are not analytically compatible",
            "M3 only merges patches with the same classification and identical fitted "
            "parameters; no refit is fabricated.",
            project_id=project_id,
            recoverable=True,
            recommended_action="Refit or edit the patches to compatible parameters before merging.",
        )
    merged_from = sorted(body.patch_ids)
    digest = hashlib.sha256(json.dumps(merged_from).encode()).hexdigest()[:16]
    merged = dict(selected[0])
    merged["id"] = f"patch.merge.{digest}"
    merged["mergedFrom"] = merged_from
    merged["triangleIds"] = sorted(
        set(selected[0].get("triangleIds", [])) | set(selected[1].get("triangleIds", []))
    )
    merged["triangleCount"] = len(merged["triangleIds"])
    merged["areaMm2"] = float(selected[0].get("areaMm2", 0)) + float(selected[1].get("areaMm2", 0))
    merged["confidence"] = min(
        float(selected[0].get("confidence", 0)), float(selected[1].get("confidence", 0))
    )
    document["patches"] = [item for item in patches if item not in selected] + [merged]
    revision, _ = repo.replace_state(project_id, expected, document)
    repo.record_audit(request_id(request), "patch.merge", "success", project_id=project_id)
    return success(request, merged, headers=revision_headers(revision))


@router.post("/split")
def split_patch(
    request: Request,
    project_id: str,
    body: PatchSplitRequest,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> JSONResponse:
    del request, body, if_match
    raise APIError(
        501,
        "unsupported_operation",
        "Patch splitting is not implemented",
        "Triangle-selection patch splitting is explicitly P1 and is not fabricated by M3.",
        project_id=project_id,
        recoverable=False,
    )


__all__ = ["router"]
