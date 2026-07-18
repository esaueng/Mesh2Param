"""Recognized conical bosses joined to a fitted plate by raw kernel fusion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import mesh2param.curved_patch as curved_patch_module
import numpy as np
import pytest
import trimesh
from mesh2param.curved_fixtures import (
    CURVED_FIXTURES_BY_SLUG,
    FIXTURE_MANIFEST_NAME,
    FIXTURE_STL_NAME,
    generate_curved_fixture,
)
from mesh2param.curved_patch import (
    CurvedNetworkSettings,
    CurvedPatchError,
    CurvedPatchSettings,
    plate_artifact_bytes,
    plate_artifact_payload,
    rebuild_plate_solid,
    reconstruct_plate_network,
    reconstruct_single_patch_plate,
)
from mesh2param.fit_cache import CurvedFitCache
from mesh2param.segmentation import SegmentationResult, segment_mesh
from mesh2param.validation import classify_face_surfaces, export_step_validated
from mesh2param_api.jobs.handlers import run_handler

SETTINGS = CurvedPatchSettings(
    fit_tolerance_mm=0.25,
    surface_deviation_tolerance_mm=0.3,
    comparison_sample_count=300,
)


@pytest.fixture(scope="module")
def cone_plate(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("cone-plate")
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["bspline-cone-plate"], root)
    return root / "bspline-cone-plate"


def _mesh(directory: Path) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(directory / FIXTURE_STL_NAME, process=True)
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


@pytest.mark.geometry
def test_cone_fixture_is_watertight_and_segments_before_driver(cone_plate: Path) -> None:
    mesh = _mesh(cone_plate)
    assert mesh.is_watertight
    assert mesh.is_winding_consistent

    segmentation = segment_mesh(mesh)
    assert segmentation.counts_by_type["cone"] == 1
    assert segmentation.counts_by_type["freeform"] == 1
    assert segmentation.counts_by_type["plane"] == 5
    freeform = next(patch for patch in segmentation.patches if patch.kind == "freeform")
    cone = next(patch for patch in segmentation.patches if patch.kind == "cone")
    assert len(freeform.boundary_loops) == 2
    assert set(freeform.vertex_ids) & set(cone.vertex_ids)
    assert cone.cone_apex is not None
    assert cone.cone_axis is not None
    assert np.allclose(cone.cone_apex, (40.0, 40.0, 12.0), atol=1e-3)
    assert cone.cone_half_angle_deg == pytest.approx(35.0, abs=1e-3)


@pytest.mark.geometry
def test_cone_reconstruction_gates(cone_plate: Path) -> None:
    manifest = json.loads((cone_plate / FIXTURE_MANIFEST_NAME).read_text(encoding="utf-8"))
    result = reconstruct_plate_network(_mesh(cone_plate), settings=SETTINGS)

    assert len(result.solid.Faces()) == 7
    assert result.face_surfaces["bspline"] == 1
    assert result.face_surfaces["cone"] == 1
    assert result.face_surfaces["plane"] == 5
    assert result.face_surfaces["cylinder"] == 0
    assert result.face_surfaces["sphere"] == 0

    (cone,) = result.cones
    assert cone.half_angle_deg == pytest.approx(35.0, abs=1e-3)
    assert np.allclose(cone.apex, (40.0, 40.0, 12.0), atol=1e-3)
    (fuser,) = result.cone_fusers
    assert fuser.apex == pytest.approx(tuple(cone.apex), abs=1e-12)
    assert fuser.axis == pytest.approx((0.0, 0.0, -1.0), abs=1e-6)
    assert fuser.half_angle_deg == cone.half_angle_deg
    assert fuser.height > cone.visible_height

    assert result.residual_maximum <= SETTINGS.fit_tolerance_mm
    assert result.comparison.maximum_distance_mm <= SETTINGS.surface_deviation_tolerance_mm
    assert result.solid.Volume() == pytest.approx(manifest["groundTruth"]["volume"], rel=5e-3)
    assert result.candidates[0]["layout"] == "single-patch"
    assert result.candidates[0]["chosen"] is True


@pytest.mark.geometry
def test_cone_reconstruction_is_byte_deterministic(cone_plate: Path, tmp_path: Path) -> None:
    mesh = _mesh(cone_plate)
    observations: list[tuple[str, bytes, str]] = []
    for run in ("a", "b"):
        result = reconstruct_plate_network(mesh, settings=SETTINGS)
        payload = plate_artifact_payload(result)
        step = export_step_validated(result.solid, tmp_path / run / "plate.step")
        observations.append((result.artifact_sha256, plate_artifact_bytes(payload), step.sha256))
    assert observations[0] == observations[1]


@pytest.mark.geometry
def test_cone_artifact_rebuild_is_byte_identical(cone_plate: Path, tmp_path: Path) -> None:
    result = reconstruct_plate_network(_mesh(cone_plate), settings=SETTINGS)
    payload = plate_artifact_payload(result)
    assert "caps" not in payload["assembly"]
    assert len(payload["assembly"]["cones"]) == 1

    rebuilt = rebuild_plate_solid(payload)
    driver_sha = export_step_validated(result.solid, tmp_path / "driver" / "plate.step").sha256
    rebuilt_sha = export_step_validated(rebuilt, tmp_path / "rebuilt" / "plate.step").sha256
    assert rebuilt_sha == driver_sha
    assert classify_face_surfaces(rebuilt) == result.face_surfaces


@pytest.mark.geometry
def test_cone_cache_hit_reruns_gates(cone_plate: Path, tmp_path: Path) -> None:
    mesh = _mesh(cone_plate)
    cache = CurvedFitCache(tmp_path / "cache")
    stored = reconstruct_plate_network(mesh, settings=SETTINGS, fit_cache=cache)
    assert stored.cache_status == "stored"
    hit = reconstruct_plate_network(mesh, settings=SETTINGS, fit_cache=cache)
    assert hit.cache_status == "hit"
    assert hit.artifact_sha256 == stored.artifact_sha256
    assert plate_artifact_bytes(plate_artifact_payload(hit)) == plate_artifact_bytes(
        plate_artifact_payload(stored)
    )
    assert hit.face_surfaces["cone"] == 1
    assert len(hit.solid.Faces()) == 7


@pytest.mark.geometry
def test_cones_fail_closed_outside_supported_network_path(cone_plate: Path) -> None:
    mesh = _mesh(cone_plate)

    with pytest.raises(CurvedPatchError) as single:
        reconstruct_single_patch_plate(mesh, settings=SETTINGS)
    assert single.value.code == "curved_patch_holes_unsupported"

    with pytest.raises(CurvedPatchError) as split:
        reconstruct_plate_network(
            mesh, settings=SETTINGS, network_settings=CurvedNetworkSettings(force_split=True)
        )
    assert split.value.code == "curved_patch_holes_unsupported_split"


@pytest.mark.geometry
def test_multiregion_cone_fails_closed(cone_plate: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mesh = _mesh(cone_plate)
    segmentation = segment_mesh(mesh)
    freeform = next(patch for patch in segmentation.patches if patch.kind == "freeform")
    duplicated = SegmentationResult(
        patches=(*segmentation.patches, freeform),
        settings=segmentation.settings,
        warnings=segmentation.warnings,
    )

    def duplicate_freeform(
        _mesh_value: trimesh.Trimesh,
        _settings: CurvedPatchSettings,
        _patch_overrides: dict[str, dict[str, Any]] | None,
    ) -> tuple[SegmentationResult, set[frozenset[str]]]:
        return duplicated, set()

    monkeypatch.setattr(curved_patch_module, "_segment_with_overrides", duplicate_freeform)
    with pytest.raises(CurvedPatchError) as excinfo:
        reconstruct_plate_network(mesh, settings=SETTINGS)
    assert excinfo.value.code == "curved_patch_cone_multiregion_unsupported"


@pytest.mark.geometry
def test_curved_job_reconstructs_cone_plate(cone_plate: Path, tmp_path: Path) -> None:
    source = cone_plate / FIXTURE_STL_NAME
    payload = {
        "sourcePath": str(source),
        "units": "mm",
        "settings": {
            "mode": "curved",
            "fitTolerance": 0.25,
            "surfaceDeviationTolerance": 0.3,
        },
        "source": {
            "format": "stl",
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "originalFileName": source.name,
            "declaredUnits": "mm",
            "scaleFactor": 1.0,
        },
        "projectState": {"patches": [], "settings": {}},
    }
    output = run_handler("reconstruct", payload, tmp_path, lambda _phase, _value, _detail: None)
    state = output.state_patch["settings"]["curvedReconstruction"]
    assert state["faceSurfaces"]["cone"] == 1
    assert state["faceSurfaces"]["bspline"] == 1
    plate = json.loads((tmp_path / "curved-plate.json").read_text(encoding="utf-8"))
    (fuser,) = plate["assembly"]["cones"]
    assert fuser["apex"] == pytest.approx([40.0, 40.0, 12.0], abs=1e-3)
    assert fuser["halfAngleDeg"] == pytest.approx(35.0, abs=1e-3)
