"""User crease-classification override: declaring a region join smooth."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import trimesh
from mesh2param.curved_fixtures import (
    CURVED_FIXTURES_BY_SLUG,
    FIXTURE_STL_NAME,
    generate_curved_fixture,
)
from mesh2param.curved_patch import (
    CurvedNetworkSettings,
    CurvedPatchError,
    CurvedPatchSettings,
    reconstruct_plate_network,
)
from mesh2param.segmentation import segment_mesh
from mesh2param_api.api.core import APIError
from mesh2param_api.api.routes.patches import _apply_smooth_boundaries
from mesh2param_api.jobs.handlers import run_handler

SETTINGS = CurvedPatchSettings(
    fit_tolerance_mm=0.25,
    surface_deviation_tolerance_mm=0.3,
    comparison_sample_count=300,
)


@pytest.fixture(scope="module")
def soft_gable(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("soft-gable")
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["bspline-soft-gable-plate"], root)
    return root / "bspline-soft-gable-plate" / FIXTURE_STL_NAME


def _mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(path, process=True)
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


def _freeform_ids(mesh: trimesh.Trimesh) -> list[str]:
    segmentation = segment_mesh(mesh)
    return sorted(patch.id for patch in segmentation.patches if patch.kind == "freeform")


@pytest.mark.geometry
def test_soft_gable_defaults_to_a_sharp_crease(soft_gable: Path) -> None:
    result = reconstruct_plate_network(_mesh(soft_gable), settings=SETTINGS)
    (curve,) = result.network.curves
    assert curve.id == "crease-0"
    assert curve.continuity == "crease"
    (edge,) = result.shared_evidence
    assert edge.minimum_normal_angle_deg > CurvedNetworkSettings().crease_minimum_angle_deg


@pytest.mark.geometry
def test_smooth_override_produces_a_smooth_join(soft_gable: Path) -> None:
    mesh = _mesh(soft_gable)
    regions = _freeform_ids(mesh)
    sharp = reconstruct_plate_network(mesh, settings=SETTINGS)
    smooth = reconstruct_plate_network(
        mesh,
        settings=SETTINGS,
        patch_overrides={regions[0]: {"smooth_boundaries": [regions[1]]}},
    )

    (curve,) = smooth.network.curves
    assert curve.id == "smooth-0"
    assert curve.continuity == "smooth"
    assert [candidate["layout"] for candidate in smooth.candidates] == ["smooth-join-network"]

    # G0 stays exact; the interior of the join is tangent-continuous. The
    # curve's two endpoints remain C0 corners because the plate's straight
    # boundary chains meet at an angle there -- forced by the walls, and
    # reported honestly in the full-range statistic.
    (edge,) = smooth.shared_evidence
    assert edge.maximum_position_gap == 0.0
    assert edge.interior_maximum_normal_angle_deg <= CurvedNetworkSettings().g1_maximum_angle_deg
    assert edge.maximum_normal_angle_deg > 10.0

    assert smooth.residual_maximum <= SETTINGS.fit_tolerance_mm
    assert smooth.comparison.maximum_distance_mm <= SETTINGS.surface_deviation_tolerance_mm
    assert smooth.artifact_sha256 != sharp.artifact_sha256

    repeat = reconstruct_plate_network(
        mesh,
        settings=SETTINGS,
        patch_overrides={regions[1]: {"smooth_boundaries": [regions[0]]}},
    )
    # Declaring the boundary from either side is the same override.
    assert repeat.artifact_sha256 == smooth.artifact_sha256


@pytest.mark.geometry
def test_smooth_override_fails_closed_on_invalid_pairs(soft_gable: Path) -> None:
    mesh = _mesh(soft_gable)
    segmentation = segment_mesh(mesh)
    regions = sorted(p.id for p in segmentation.patches if p.kind == "freeform")
    freeform = regions[0]
    wall = next(
        patch.id
        for patch in segmentation.patches
        if patch.kind == "plane" and freeform in patch.neighbor_ids
    )
    bottom = next(
        patch.id
        for patch in segmentation.patches
        if patch.kind == "plane"
        and not {regions[0], regions[1]} & set(patch.neighbor_ids)
    )

    with pytest.raises(CurvedPatchError) as unknown:
        reconstruct_plate_network(
            mesh,
            settings=SETTINGS,
            patch_overrides={freeform: {"smooth_boundaries": ["patch.missing"]}},
        )
    assert unknown.value.code == "curved_patch_override_unknown"

    with pytest.raises(CurvedPatchError) as detached:
        reconstruct_plate_network(
            mesh,
            settings=SETTINGS,
            patch_overrides={freeform: {"smooth_boundaries": [bottom]}},
        )
    assert detached.value.code == "curved_patch_override_rejected"

    with pytest.raises(CurvedPatchError) as kinds:
        reconstruct_plate_network(
            mesh,
            settings=SETTINGS,
            patch_overrides={freeform: {"smooth_boundaries": [wall]}},
        )
    assert kinds.value.code == "curved_patch_override_rejected"


@pytest.mark.geometry
def test_handler_applies_persisted_smooth_boundary(soft_gable: Path, tmp_path: Path) -> None:
    mesh = _mesh(soft_gable)
    regions = _freeform_ids(mesh)
    payload = {
        "sourcePath": str(soft_gable),
        "units": "mm",
        "settings": {"mode": "curved", "fitTolerance": 0.25, "surfaceDeviationTolerance": 0.3},
        "source": {
            "format": "stl",
            "sha256": hashlib.sha256(soft_gable.read_bytes()).hexdigest(),
            "originalFileName": soft_gable.name,
            "declaredUnits": "mm",
            "scaleFactor": 1.0,
        },
        "projectState": {
            "patches": [
                {"id": regions[0], "type": "freeform", "smoothBoundaryIds": [regions[1]]},
                {"id": regions[1], "type": "freeform", "smoothBoundaryIds": [regions[0]]},
            ],
            "settings": {},
        },
    }
    output = run_handler(
        "reconstruct", payload, tmp_path, lambda _phase, _value, _detail: None
    )
    state = output.state_patch["settings"]["curvedReconstruction"]
    assert state["appliedSmoothBoundaries"] == ["|".join(regions)]
    plate = json.loads((tmp_path / "curved-plate.json").read_text(encoding="utf-8"))
    (curve,) = plate["network"]["curves"]
    assert curve["id"] == "smooth-0"
    assert curve["continuity"] == "smooth"


def _patch_dict(patch_id: str, **overrides: object) -> dict[str, object]:
    return {
        "id": patch_id,
        "type": "freeform",
        "locked": False,
        "neighborIds": [],
        "smoothBoundaryIds": [],
        **overrides,
    }


def test_route_helper_mirrors_declarations_symmetrically() -> None:
    a = _patch_dict("patch.a", neighborIds=["patch.b", "patch.c"])
    b = _patch_dict("patch.b", neighborIds=["patch.a"])
    c = _patch_dict("patch.c", neighborIds=["patch.a"])
    patches = [a, b, c]

    _apply_smooth_boundaries(a, ["patch.b"], patches, "project")
    assert a["smoothBoundaryIds"] == ["patch.b"]
    assert b["smoothBoundaryIds"] == ["patch.a"]
    assert c["smoothBoundaryIds"] == []

    # Clearing from the mirrored side removes the declaration on both.
    _apply_smooth_boundaries(b, [], patches, "project")
    assert a["smoothBoundaryIds"] == []
    assert b["smoothBoundaryIds"] == []


def test_route_helper_fails_closed() -> None:
    a = _patch_dict("patch.a", neighborIds=["patch.b"])
    b = _patch_dict("patch.b", neighborIds=["patch.a"])
    stranger = _patch_dict("patch.d")
    patches = [a, b, stranger]

    with pytest.raises(APIError) as non_neighbor:
        _apply_smooth_boundaries(a, ["patch.d"], patches, "project")
    assert non_neighbor.value.code == "invalid_boundary_override"

    b["locked"] = True
    with pytest.raises(APIError) as locked:
        _apply_smooth_boundaries(a, ["patch.b"], patches, "project")
    assert locked.value.code == "patch_locked"
    assert a["smoothBoundaryIds"] == []
