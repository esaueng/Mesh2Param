"""Recognized spherical caps joined to the plate shell by kernel fusion."""

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
    rebuild_plate_solid,
    reconstruct_plate_network,
    reconstruct_single_patch_plate,
)
from mesh2param.fit_cache import CurvedFitCache
from mesh2param.segmentation import segment_mesh
from mesh2param.tessellation import Tessellation, canonicalize_tessellation
from mesh2param.validation import classify_face_surfaces, export_step_validated
from mesh2param_api.jobs.handlers import run_handler

DOME_VOLUME_EXACT = 165903.2

SETTINGS = CurvedPatchSettings(
    fit_tolerance_mm=0.25,
    surface_deviation_tolerance_mm=0.3,
    comparison_sample_count=300,
)


@pytest.fixture(scope="module")
def dome_plate(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("dome-plate")
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["bspline-dome-plate"], root)
    return root / "bspline-dome-plate" / FIXTURE_STL_NAME


def _mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(path, process=True)
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


@pytest.mark.geometry
def test_dome_segments_into_freeform_with_sphere_cap(dome_plate: Path) -> None:
    segmentation = segment_mesh(_mesh(dome_plate))
    assert segmentation.counts_by_type["sphere"] == 1
    assert segmentation.counts_by_type["freeform"] == 1
    assert segmentation.counts_by_type["plane"] == 5
    freeform = next(patch for patch in segmentation.patches if patch.kind == "freeform")
    sphere = next(patch for patch in segmentation.patches if patch.kind == "sphere")
    # The freeform top carries the dome rim as an interior loop shared with
    # the recognized sphere region.
    assert len(freeform.boundary_loops) == 2
    assert set(freeform.vertex_ids) & set(sphere.vertex_ids)
    assert sphere.sphere_radius_mm == pytest.approx(10.0, abs=1e-3)
    assert sphere.sphere_center is not None
    assert np.allclose(sphere.sphere_center, (40.0, 40.0, -3.6), atol=1e-3)


@pytest.mark.geometry
def test_cap_reconstruction_gates(dome_plate: Path) -> None:
    mesh = _mesh(dome_plate)
    result = reconstruct_plate_network(mesh, settings=SETTINGS)

    assert result.face_surfaces["bspline"] == 1
    assert result.face_surfaces["sphere"] == 1
    assert result.face_surfaces["plane"] == 5
    assert result.face_surfaces["cylinder"] == 0

    (cap,) = result.caps
    assert cap.radius == pytest.approx(10.0, abs=1e-3)
    (fuser,) = result.cap_fusers
    assert fuser.radius == cap.radius
    assert fuser.axis == (0.0, 0.0, 1.0)

    assert result.residual_maximum <= SETTINGS.fit_tolerance_mm
    assert result.comparison.maximum_distance_mm <= SETTINGS.surface_deviation_tolerance_mm
    assert abs(result.solid.Volume() - DOME_VOLUME_EXACT) / DOME_VOLUME_EXACT < 5e-3
    assert result.candidates[0]["layout"] == "single-patch"
    assert result.candidates[0]["chosen"] is True


@pytest.mark.geometry
def test_cap_artifact_rebuild_is_byte_identical(dome_plate: Path, tmp_path: Path) -> None:
    mesh = _mesh(dome_plate)
    first = reconstruct_plate_network(mesh, settings=SETTINGS)
    second = reconstruct_plate_network(mesh, settings=SETTINGS)
    assert first.artifact_sha256 == second.artifact_sha256

    payload = plate_artifact_payload(first)
    # The caps key is present only when caps exist, so cap-free artifacts
    # keep their historical bytes and hashes.
    assert len(payload["assembly"]["caps"]) == 1
    rebuilt = rebuild_plate_solid(payload)
    driver_sha = export_step_validated(first.solid, tmp_path / "driver" / "plate.step").sha256
    rebuilt_sha = export_step_validated(rebuilt, tmp_path / "rebuilt" / "plate.step").sha256
    assert rebuilt_sha == driver_sha
    assert classify_face_surfaces(rebuilt) == first.face_surfaces


@pytest.mark.geometry
def test_cap_cache_hit_reruns_gates(dome_plate: Path, tmp_path: Path) -> None:
    mesh = _mesh(dome_plate)
    cache = CurvedFitCache(tmp_path / "cache")
    stored = reconstruct_plate_network(mesh, settings=SETTINGS, fit_cache=cache)
    assert stored.cache_status == "stored"
    hit = reconstruct_plate_network(mesh, settings=SETTINGS, fit_cache=cache)
    assert hit.cache_status == "hit"
    assert hit.artifact_sha256 == stored.artifact_sha256
    assert hit.face_surfaces["sphere"] == 1


@pytest.mark.geometry
def test_caps_fail_closed_outside_the_network_path(dome_plate: Path) -> None:
    mesh = _mesh(dome_plate)

    with pytest.raises(CurvedPatchError) as single:
        reconstruct_single_patch_plate(mesh, settings=SETTINGS)
    assert single.value.code == "curved_patch_holes_unsupported"

    with pytest.raises(CurvedPatchError) as split:
        reconstruct_plate_network(
            mesh, settings=SETTINGS, network_settings=CurvedNetworkSettings(force_split=True)
        )
    assert split.value.code == "curved_patch_holes_unsupported_split"


@pytest.mark.geometry
def test_curved_job_reconstructs_dome_plate(dome_plate: Path, tmp_path: Path) -> None:
    payload = {
        "sourcePath": str(dome_plate),
        "units": "mm",
        "settings": {"mode": "curved", "fitTolerance": 0.25, "surfaceDeviationTolerance": 0.3},
        "source": {
            "format": "stl",
            "sha256": hashlib.sha256(dome_plate.read_bytes()).hexdigest(),
            "originalFileName": dome_plate.name,
            "declaredUnits": "mm",
            "scaleFactor": 1.0,
        },
        "projectState": {"patches": [], "settings": {}},
    }
    output = run_handler(
        "reconstruct", payload, tmp_path, lambda _phase, _value, _detail: None
    )
    state = output.state_patch["settings"]["curvedReconstruction"]
    assert state["faceSurfaces"]["sphere"] == 1
    assert state["faceSurfaces"]["bspline"] == 1
    plate = json.loads((tmp_path / "curved-plate.json").read_text(encoding="utf-8"))
    (fuser,) = plate["assembly"]["caps"]
    assert fuser["radiusMm"] == pytest.approx(10.0, abs=1e-3)


def test_canonical_tessellation_drops_exact_pole_degenerates() -> None:
    # OCCT's sphere pole fans emit triangles with two bitwise-identical
    # vertices: genuinely zero-area, dropped exactly.
    pole = (0.0, 0.0, 1.0)
    mesh = Tessellation(
        vertices=(pole, pole, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        triangles=((0, 1, 2), (0, 2, 3)),
        normals=(),
    )
    canonical = canonicalize_tessellation(mesh)
    assert len(canonical.triangles) == 1

    # Distinct coordinates that only collide after quantization still fail
    # closed: that is data loss, not degeneracy.
    nearly = (0.0, 0.0, 1.0 + 2e-7)
    collapsing = Tessellation(
        vertices=(pole, nearly, (1.0, 0.0, 0.0)),
        triangles=((0, 1, 2),),
        normals=(),
    )
    with pytest.raises(ValueError, match="collapsed"):
        canonicalize_tessellation(collapsing)
