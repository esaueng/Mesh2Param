"""Recognized through holes on multi-region crease plates."""

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
    CurvedPatchSettings,
    plate_artifact_payload,
    rebuild_plate_solid,
    reconstruct_plate_network,
)
from mesh2param.fit_cache import CurvedFitCache
from mesh2param.segmentation import segment_mesh
from mesh2param.validation import classify_face_surfaces, export_step_validated
from mesh2param_api.jobs.handlers import run_handler

GABLE_HOLE_VOLUME_EXACT = 201476.3

SETTINGS = CurvedPatchSettings(
    fit_tolerance_mm=0.25,
    surface_deviation_tolerance_mm=0.3,
    comparison_sample_count=300,
)


@pytest.fixture(scope="module")
def gable_hole(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("gable-hole")
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["bspline-gable-plate-hole"], root)
    return root / "bspline-gable-plate-hole" / FIXTURE_STL_NAME


def _mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(path, process=True)
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


@pytest.mark.geometry
def test_pierced_gable_segments_with_hole_rim_on_one_roof(gable_hole: Path) -> None:
    segmentation = segment_mesh(_mesh(gable_hole))
    assert segmentation.counts_by_type["freeform"] == 2
    assert segmentation.counts_by_type["cylinder"] == 1
    assert segmentation.counts_by_type["plane"] == 5
    loop_counts = sorted(
        len(patch.boundary_loops)
        for patch in segmentation.patches
        if patch.kind == "freeform"
    )
    # One roof carries the hole rim as a second closed loop.
    assert loop_counts == [1, 2]


@pytest.mark.geometry
def test_pierced_gable_reconstruction_gates(gable_hole: Path) -> None:
    mesh = _mesh(gable_hole)
    result = reconstruct_plate_network(mesh, settings=SETTINGS)

    assert result.face_surfaces["bspline"] == 2
    assert result.face_surfaces["cylinder"] == 1
    assert result.face_surfaces["plane"] == 5

    (hole,) = result.holes
    assert hole.radius == pytest.approx(6.0, abs=1e-3)
    assert len(result.hole_cutters) == 1

    (edge,) = result.shared_evidence
    assert edge.continuity == "crease"
    assert edge.maximum_position_gap == 0.0
    assert edge.minimum_normal_angle_deg > CurvedNetworkSettings().crease_minimum_angle_deg

    assert result.residual_maximum <= SETTINGS.fit_tolerance_mm
    assert result.comparison.maximum_distance_mm <= SETTINGS.surface_deviation_tolerance_mm
    assert (
        abs(result.solid.Volume() - GABLE_HOLE_VOLUME_EXACT) / GABLE_HOLE_VOLUME_EXACT < 5e-3
    )
    assert [candidate["layout"] for candidate in result.candidates] == ["crease-network"]


@pytest.mark.geometry
def test_pierced_gable_is_deterministic_and_rebuildable(
    gable_hole: Path, tmp_path: Path
) -> None:
    mesh = _mesh(gable_hole)
    first = reconstruct_plate_network(mesh, settings=SETTINGS)
    second = reconstruct_plate_network(mesh, settings=SETTINGS)
    assert first.artifact_sha256 == second.artifact_sha256

    payload = plate_artifact_payload(first)
    assert len(payload["assembly"]["holes"]) == 1
    rebuilt = rebuild_plate_solid(payload)
    driver_sha = export_step_validated(first.solid, tmp_path / "driver" / "plate.step").sha256
    rebuilt_sha = export_step_validated(rebuilt, tmp_path / "rebuilt" / "plate.step").sha256
    assert rebuilt_sha == driver_sha
    assert classify_face_surfaces(rebuilt) == first.face_surfaces


@pytest.mark.geometry
def test_pierced_gable_cache_hit_reruns_gates(gable_hole: Path, tmp_path: Path) -> None:
    mesh = _mesh(gable_hole)
    cache = CurvedFitCache(tmp_path / "cache")
    stored = reconstruct_plate_network(mesh, settings=SETTINGS, fit_cache=cache)
    assert stored.cache_status == "stored"
    hit = reconstruct_plate_network(mesh, settings=SETTINGS, fit_cache=cache)
    assert hit.cache_status == "hit"
    assert hit.artifact_sha256 == stored.artifact_sha256
    assert hit.face_surfaces["cylinder"] == 1


@pytest.mark.geometry
def test_smooth_override_composes_with_holes(gable_hole: Path) -> None:
    mesh = _mesh(gable_hole)
    regions = sorted(
        patch.id for patch in segment_mesh(mesh).patches if patch.kind == "freeform"
    )
    result = reconstruct_plate_network(
        mesh,
        settings=SETTINGS,
        patch_overrides={regions[0]: {"smooth_boundaries": [regions[1]]}},
    )
    (curve,) = result.network.curves
    assert curve.continuity == "smooth"
    assert result.face_surfaces["cylinder"] == 1
    (edge,) = result.shared_evidence
    assert edge.interior_maximum_normal_angle_deg <= CurvedNetworkSettings().g1_maximum_angle_deg


@pytest.mark.geometry
def test_curved_job_reconstructs_pierced_gable(gable_hole: Path, tmp_path: Path) -> None:
    payload = {
        "sourcePath": str(gable_hole),
        "units": "mm",
        "settings": {"mode": "curved", "fitTolerance": 0.25, "surfaceDeviationTolerance": 0.3},
        "source": {
            "format": "stl",
            "sha256": hashlib.sha256(gable_hole.read_bytes()).hexdigest(),
            "originalFileName": gable_hole.name,
            "declaredUnits": "mm",
            "scaleFactor": 1.0,
        },
        "projectState": {"patches": [], "settings": {}},
    }
    output = run_handler(
        "reconstruct", payload, tmp_path, lambda _phase, _value, _detail: None
    )
    state = output.state_patch["settings"]["curvedReconstruction"]
    assert state["faceSurfaces"]["bspline"] == 2
    assert state["faceSurfaces"]["cylinder"] == 1
    plate = json.loads((tmp_path / "curved-plate.json").read_text(encoding="utf-8"))
    (cutter,) = plate["assembly"]["holes"]
    assert cutter["radiusMm"] == pytest.approx(6.0, abs=1e-3)
