from __future__ import annotations

import json
import math
from pathlib import Path

import cadquery as cq
import numpy as np
import pytest
import trimesh
from mesh2param.comparison import tessellation_to_mesh
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
    reconstruct_plate_network,
    reconstruct_single_patch_plate,
)
from mesh2param.segmentation import segment_mesh
from mesh2param.tessellation import tessellate_shape
from mesh2param.validation import (
    classify_face_surfaces,
    export_step_validated,
    import_step_shape,
)

SETTINGS = CurvedPatchSettings(
    fit_tolerance_mm=0.25,
    surface_deviation_tolerance_mm=0.3,
    comparison_sample_count=500,
)


@pytest.fixture(scope="module")
def hole_plate(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("bump-plate-hole")
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["bspline-bump-plate-hole"], root)
    return root / "bspline-bump-plate-hole"


def _load(directory: Path) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(directory / FIXTURE_STL_NAME, process=True)
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


@pytest.mark.geometry
def test_segmentation_recognizes_sphere() -> None:
    mesh = trimesh.creation.icosphere(subdivisions=3, radius=20.0)
    patches = segment_mesh(mesh).patches
    assert {patch.kind for patch in patches} == {"sphere"}
    (sphere,) = patches
    assert sphere.sphere_radius_mm == pytest.approx(20.0, abs=1e-6)
    assert sphere.sphere_center is not None
    assert np.allclose(sphere.sphere_center, (0.0, 0.0, 0.0), atol=1e-6)


@pytest.mark.geometry
def test_segmentation_recognizes_truncated_cone() -> None:
    solid = cq.Solid.makeCone(20.0, 5.0, 30.0)
    tessellation = tessellate_shape(
        cq.Shape.cast(solid.wrapped), linear_tolerance=0.002, angular_tolerance=0.2
    )
    raw = tessellation_to_mesh(tessellation)
    mesh = trimesh.Trimesh(vertices=raw.vertices, faces=raw.faces, process=True)
    patches = segment_mesh(mesh).patches
    kinds = sorted(patch.kind for patch in patches)
    assert kinds == ["cone", "plane", "plane"]
    (cone,) = [patch for patch in patches if patch.kind == "cone"]
    expected = math.degrees(math.atan((20.0 - 5.0) / 30.0))
    assert cone.cone_half_angle_deg == pytest.approx(expected, abs=1e-3)
    assert cone.cone_apex is not None
    assert np.allclose(cone.cone_apex, (0.0, 0.0, 40.0), atol=1e-3)


@pytest.mark.geometry
def test_segmentation_recognizes_torus() -> None:
    mesh = trimesh.creation.torus(
        major_radius=25.0, minor_radius=6.0, major_sections=96, minor_sections=48
    )
    patches = segment_mesh(mesh).patches
    assert {patch.kind for patch in patches} == {"torus"}
    (torus,) = patches
    assert torus.torus_major_radius_mm == pytest.approx(25.0, abs=1e-6)
    assert torus.torus_minor_radius_mm == pytest.approx(6.0, abs=1e-6)


@pytest.mark.geometry
def test_hybrid_plate_with_hole(hole_plate: Path) -> None:
    manifest = json.loads((hole_plate / FIXTURE_MANIFEST_NAME).read_text(encoding="utf-8"))
    mesh = _load(hole_plate)
    result = reconstruct_plate_network(mesh, settings=SETTINGS)

    assert len(result.solid.Faces()) == 7
    assert result.face_surfaces["bspline"] == 1
    assert result.face_surfaces["cylinder"] == 1
    assert result.face_surfaces["plane"] == 5

    (hole,) = result.holes
    assert hole.radius == pytest.approx(8.0, abs=1e-3)
    assert result.comparison.maximum_distance_mm <= 0.3
    assert result.solid.Volume() == pytest.approx(manifest["groundTruth"]["volume"], rel=5e-3)


@pytest.mark.geometry
def test_hybrid_step_roundtrip_keeps_all_surface_kinds(hole_plate: Path, tmp_path: Path) -> None:
    mesh = _load(hole_plate)
    result = reconstruct_plate_network(mesh, settings=SETTINGS)
    report = export_step_validated(result.solid, tmp_path / "hybrid.step")
    assert report.valid
    surfaces = classify_face_surfaces(import_step_shape(tmp_path / "hybrid.step"))
    assert surfaces["bspline"] == 1
    assert surfaces["cylinder"] == 1
    assert surfaces["plane"] == 5


@pytest.mark.geometry
def test_hybrid_reconstruction_is_deterministic(hole_plate: Path, tmp_path: Path) -> None:
    mesh = _load(hole_plate)
    shas = []
    for run in ("a", "b"):
        result = reconstruct_plate_network(mesh, settings=SETTINGS)
        report = export_step_validated(result.solid, tmp_path / run / "hybrid.step")
        shas.append((result.artifact_sha256, report.sha256))
    assert shas[0] == shas[1]


@pytest.mark.geometry
def test_layout_candidates_are_scored_and_retained(tmp_path: Path) -> None:
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["bspline-bump-plate"], tmp_path)
    mesh = trimesh.load_mesh(tmp_path / "bspline-bump-plate" / FIXTURE_STL_NAME, process=True)
    assert isinstance(mesh, trimesh.Trimesh)
    result = reconstruct_plate_network(
        mesh, settings=SETTINGS, network_settings=CurvedNetworkSettings(force_split=True)
    )
    layouts = {candidate["layout"]: candidate for candidate in result.candidates}
    assert set(layouts) == {"single-patch", "split-network"}
    # The rejected single-patch candidate keeps its full score.
    assert layouts["single-patch"]["converged"] is True
    assert layouts["single-patch"]["chosen"] is False
    assert layouts["single-patch"]["residualMaximum"] > 0.0
    assert layouts["split-network"]["chosen"] is True


@pytest.mark.geometry
def test_single_patch_driver_rejects_holes(hole_plate: Path) -> None:
    mesh = _load(hole_plate)
    with pytest.raises(CurvedPatchError) as excinfo:
        reconstruct_single_patch_plate(mesh, settings=SETTINGS)
    assert excinfo.value.code == "curved_patch_holes_unsupported"


@pytest.mark.geometry
def test_split_with_holes_fails_closed(hole_plate: Path) -> None:
    mesh = _load(hole_plate)
    with pytest.raises(CurvedPatchError) as excinfo:
        reconstruct_plate_network(
            mesh,
            settings=SETTINGS,
            network_settings=CurvedNetworkSettings(force_split=True),
        )
    assert excinfo.value.code == "curved_patch_holes_unsupported_split"
