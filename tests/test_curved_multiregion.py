"""Multi-region crease networks: two freeform regions sharing one real crease."""

from __future__ import annotations

import hashlib
from dataclasses import replace
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
    ReconstructionBudget,
    plate_artifact_payload,
    rebuild_plate_solid,
    reconstruct_plate_network,
)
from mesh2param.fit_cache import CurvedFitCache
from mesh2param.segmentation import segment_mesh
from mesh2param.validation import classify_face_surfaces, export_step_validated
from mesh2param_api.jobs.handlers import run_handler

GABLE_VOLUME_EXACT = 205295.30524937797

SETTINGS = CurvedPatchSettings(
    fit_tolerance_mm=0.25,
    surface_deviation_tolerance_mm=0.3,
    comparison_sample_count=300,
)


@pytest.fixture(scope="module")
def gable_plate(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("gable-plate")
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["bspline-gable-plate"], root)
    return root / "bspline-gable-plate" / FIXTURE_STL_NAME


def _mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(path, process=True)
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


@pytest.mark.geometry
def test_gable_segments_into_two_adjacent_freeform_regions(gable_plate: Path) -> None:
    segmentation = segment_mesh(_mesh(gable_plate))
    assert segmentation.counts_by_type["freeform"] == 2
    assert segmentation.counts_by_type["plane"] == 5
    regions = [patch for patch in segmentation.patches if patch.kind == "freeform"]
    assert regions[0].id in regions[1].neighbor_ids
    for region in regions:
        assert len(region.boundary_loops) == 1
        assert region.boundary_loops[0].closed


@pytest.mark.geometry
def test_crease_network_reconstruction_gates(gable_plate: Path) -> None:
    mesh = _mesh(gable_plate)
    result = reconstruct_plate_network(mesh, settings=SETTINGS)

    # The network is two patches on one shared crease curve: 7 faces total.
    assert len(result.network.patches) == 2
    assert [curve.continuity for curve in result.network.curves] == ["crease"]
    assert result.face_surfaces["bspline"] == 2
    assert result.face_surfaces["plane"] == 5

    # G0 is exact by pole aliasing; the crease stays sharp along its length.
    (edge,) = result.shared_evidence
    assert edge.continuity == "crease"
    assert edge.maximum_position_gap == 0.0
    assert edge.minimum_normal_angle_deg > CurvedNetworkSettings().crease_minimum_angle_deg
    assert edge.maximum_normal_angle_deg < 45.0

    assert result.residual_maximum <= SETTINGS.fit_tolerance_mm
    assert result.comparison.maximum_distance_mm <= SETTINGS.surface_deviation_tolerance_mm
    assert abs(result.solid.Volume() - GABLE_VOLUME_EXACT) / GABLE_VOLUME_EXACT < 5e-3
    assert [candidate["layout"] for candidate in result.candidates] == ["crease-network"]
    assert result.candidates[0]["chosen"] is True


@pytest.mark.geometry
def test_crease_network_is_deterministic_and_rebuildable(
    gable_plate: Path, tmp_path: Path
) -> None:
    mesh = _mesh(gable_plate)
    first = reconstruct_plate_network(mesh, settings=SETTINGS)
    second = reconstruct_plate_network(mesh, settings=SETTINGS)
    assert first.artifact_sha256 == second.artifact_sha256

    # The self-sufficient plate artifact rebuilds a byte-identical STEP body.
    payload = plate_artifact_payload(first)
    rebuilt = rebuild_plate_solid(payload)
    driver_sha = export_step_validated(first.solid, tmp_path / "driver" / "plate.step").sha256
    rebuilt_sha = export_step_validated(rebuilt, tmp_path / "rebuilt" / "plate.step").sha256
    assert rebuilt_sha == driver_sha
    assert classify_face_surfaces(rebuilt) == first.face_surfaces


@pytest.mark.geometry
def test_crease_network_cache_hit_reruns_gates(gable_plate: Path, tmp_path: Path) -> None:
    mesh = _mesh(gable_plate)
    cache = CurvedFitCache(tmp_path / "cache")
    stored = reconstruct_plate_network(mesh, settings=SETTINGS, fit_cache=cache)
    assert stored.cache_status == "stored"
    hit = reconstruct_plate_network(mesh, settings=SETTINGS, fit_cache=cache)
    assert hit.cache_status == "hit"
    assert hit.artifact_sha256 == stored.artifact_sha256
    stored_sha = export_step_validated(stored.solid, tmp_path / "stored" / "plate.step").sha256
    hit_sha = export_step_validated(hit.solid, tmp_path / "hit" / "plate.step").sha256
    assert hit_sha == stored_sha


@pytest.mark.geometry
def test_crease_network_fails_closed(gable_plate: Path) -> None:
    mesh = _mesh(gable_plate)

    # forceSplit only applies to single-region plates.
    with pytest.raises(CurvedPatchError) as force_split:
        reconstruct_plate_network(
            mesh, settings=SETTINGS, network_settings=CurvedNetworkSettings(force_split=True)
        )
    assert force_split.value.code == "curved_patch_force_split_unsupported"

    # A single-patch budget cannot hold a two-patch network.
    with pytest.raises(CurvedPatchError) as budget:
        reconstruct_plate_network(
            mesh,
            settings=replace(SETTINGS, budget=ReconstructionBudget(maximum_patches=1)),
        )
    assert budget.value.code == "curved_patch_patch_budget"

    # An impossible sharpness gate reports the crease as lost, not smoothed.
    with pytest.raises(CurvedPatchError) as lost:
        reconstruct_plate_network(
            mesh,
            settings=SETTINGS,
            network_settings=CurvedNetworkSettings(crease_minimum_angle_deg=85.0),
        )
    assert lost.value.code == "curved_patch_crease_lost"


@pytest.mark.geometry
def test_curved_job_reconstructs_gable_plate(gable_plate: Path, tmp_path: Path) -> None:
    payload = {
        "sourcePath": str(gable_plate),
        "units": "mm",
        "settings": {"mode": "curved", "fitTolerance": 0.25, "surfaceDeviationTolerance": 0.3},
        "source": {
            "format": "stl",
            "sha256": hashlib.sha256(gable_plate.read_bytes()).hexdigest(),
            "originalFileName": gable_plate.name,
            "declaredUnits": "mm",
            "scaleFactor": 1.0,
        },
        "projectState": {"patches": [], "settings": {}},
    }
    output = run_handler(
        "reconstruct", payload, tmp_path, lambda _phase, _value, _detail: None
    )
    state = output.state_patch["settings"]["curvedReconstruction"]
    assert state["approximate"] is True
    assert state["faceSurfaces"]["bspline"] == 2
    assert state["faceSurfaces"]["plane"] == 5
    assert (tmp_path / "curved-plate.json").exists()
    assert (tmp_path / "model.step").exists()
