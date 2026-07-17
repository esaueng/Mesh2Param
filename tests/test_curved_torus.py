"""Recognized torus beads fused into near-planar reconstructed plates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
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
    plate_artifact_payload,
    plate_artifact_sha256,
    rebuild_plate_solid,
    reconstruct_plate_network,
    reconstruct_single_patch_plate,
)
from mesh2param.fit_cache import CurvedFitCache
from mesh2param.segmentation import segment_mesh
from mesh2param.validation import classify_face_surfaces, export_step_validated
from mesh2param_api.jobs.handlers import run_handler

TORUS_PLATE_VOLUME_EXACT = 162131.35160458478

SETTINGS = CurvedPatchSettings(
    fit_tolerance_mm=0.25,
    surface_deviation_tolerance_mm=0.3,
    comparison_sample_count=300,
)


@pytest.fixture(scope="module")
def torus_plate(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("torus-bead-plate")
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["bspline-torus-bead-plate"], root)
    return root / "bspline-torus-bead-plate" / FIXTURE_STL_NAME


def _mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(path, process=True)
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


@pytest.mark.geometry
def test_torus_bead_segments_into_two_freeform_regions(torus_plate: Path) -> None:
    segmentation = segment_mesh(_mesh(torus_plate))
    assert segmentation.counts_by_type["torus"] == 1
    assert segmentation.counts_by_type["freeform"] == 2
    assert segmentation.counts_by_type["plane"] == 5

    torus = next(patch for patch in segmentation.patches if patch.kind == "torus")
    freeforms = [patch for patch in segmentation.patches if patch.kind == "freeform"]
    assert all(torus.id in patch.neighbor_ids for patch in freeforms)
    assert sorted(len(patch.boundary_loops) for patch in freeforms) == [1, 2]
    assert torus.torus_major_radius_mm == pytest.approx(14.0, abs=1e-3)
    assert torus.torus_minor_radius_mm == pytest.approx(4.0, abs=1e-3)
    assert torus.torus_center is not None
    assert np.allclose(torus.torus_center, (40.0, 40.0, -1.35), atol=1e-3)
    assert torus.torus_axis is not None
    assert np.allclose(torus.torus_axis, (0.0, 0.0, 1.0), atol=1e-8)


@pytest.mark.geometry
def test_torus_reconstruction_and_artifact_are_deterministic(
    torus_plate: Path, tmp_path: Path
) -> None:
    mesh = _mesh(torus_plate)
    first = reconstruct_plate_network(mesh, settings=SETTINGS)
    second = reconstruct_plate_network(mesh, settings=SETTINGS)

    assert first.face_surfaces == {
        "plane": 5,
        "cylinder": 0,
        "cone": 0,
        "sphere": 0,
        "torus": 1,
        "bspline": 2,
        "other": 0,
    }
    assert first.residual_maximum <= SETTINGS.fit_tolerance_mm
    assert first.comparison.maximum_distance_mm <= SETTINGS.surface_deviation_tolerance_mm
    assert abs(first.solid.Volume() - TORUS_PLATE_VOLUME_EXACT) / TORUS_PLATE_VOLUME_EXACT < 5e-3
    assert first.candidates[0]["layout"] == "torus-single-patch"
    assert first.candidates[0]["chosen"] is True

    (torus,) = first.tori
    assert torus.major_radius == pytest.approx(14.0, abs=1e-3)
    assert torus.minor_radius == pytest.approx(4.0, abs=1e-3)
    (fuser,) = first.torus_fusers
    assert fuser.major_radius == torus.major_radius
    assert fuser.minor_radius == torus.minor_radius
    assert fuser.axis == (0.0, 0.0, 1.0)

    first_payload = plate_artifact_payload(first)
    second_payload = plate_artifact_payload(second)
    assert plate_artifact_sha256(first_payload) == plate_artifact_sha256(second_payload)
    assert first_payload["assembly"]["tori"] == second_payload["assembly"]["tori"]
    rebuilt = rebuild_plate_solid(first_payload)

    first_step = export_step_validated(first.solid, tmp_path / "first" / "plate.step")
    second_step = export_step_validated(second.solid, tmp_path / "second" / "plate.step")
    rebuilt_step = export_step_validated(rebuilt, tmp_path / "rebuilt" / "plate.step")
    assert first_step.sha256 == second_step.sha256 == rebuilt_step.sha256
    assert classify_face_surfaces(rebuilt) == first.face_surfaces


@pytest.mark.geometry
def test_torus_cache_hit_replays_identical_fuser(torus_plate: Path, tmp_path: Path) -> None:
    mesh = _mesh(torus_plate)
    cache = CurvedFitCache(tmp_path / "cache")
    stored = reconstruct_plate_network(mesh, settings=SETTINGS, fit_cache=cache)
    assert stored.cache_status == "stored"
    hit = reconstruct_plate_network(mesh, settings=SETTINGS, fit_cache=cache)
    assert hit.cache_status == "hit"
    assert plate_artifact_payload(hit) == plate_artifact_payload(stored)
    stored_step = export_step_validated(stored.solid, tmp_path / "stored" / "plate.step")
    hit_step = export_step_validated(hit.solid, tmp_path / "hit" / "plate.step")
    assert hit_step.sha256 == stored_step.sha256


@pytest.mark.geometry
def test_torus_bead_fails_closed_outside_supported_network_path(torus_plate: Path) -> None:
    mesh = _mesh(torus_plate)

    with pytest.raises(CurvedPatchError) as single:
        reconstruct_single_patch_plate(mesh, settings=SETTINGS)
    assert single.value.code == "curved_patch_unsupported_topology"

    with pytest.raises(CurvedPatchError) as split:
        reconstruct_plate_network(
            mesh,
            settings=SETTINGS,
            network_settings=CurvedNetworkSettings(force_split=True),
        )
    assert split.value.code == "curved_patch_holes_unsupported_split"


@pytest.mark.geometry
def test_curved_job_reconstructs_torus_bead(torus_plate: Path, tmp_path: Path) -> None:
    payload = {
        "sourcePath": str(torus_plate),
        "units": "mm",
        "settings": {"mode": "curved", "fitTolerance": 0.25, "surfaceDeviationTolerance": 0.3},
        "source": {
            "format": "stl",
            "sha256": hashlib.sha256(torus_plate.read_bytes()).hexdigest(),
            "originalFileName": torus_plate.name,
            "declaredUnits": "mm",
            "scaleFactor": 1.0,
        },
        "projectState": {"patches": [], "settings": {}},
    }
    output = run_handler("reconstruct", payload, tmp_path, lambda _phase, _value, _detail: None)
    state = output.state_patch["settings"]["curvedReconstruction"]
    assert state["faceSurfaces"]["torus"] == 1
    assert state["faceSurfaces"]["bspline"] == 2
    plate = json.loads((tmp_path / "curved-plate.json").read_text(encoding="utf-8"))
    (fuser,) = plate["assembly"]["tori"]
    assert fuser["majorRadiusMm"] == pytest.approx(14.0, abs=1e-3)
    assert fuser["minorRadiusMm"] == pytest.approx(4.0, abs=1e-3)
    assert fuser["axis"] == [0.0, 0.0, 1.0]
