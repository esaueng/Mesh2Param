from __future__ import annotations

import json
from pathlib import Path

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
    CurvedPatchError,
    CurvedPatchSettings,
    reconstruct_single_patch_plate,
)
from mesh2param.parameterization import harmonic_square_parameterization
from mesh2param.surface_fit import SurfaceFitSettings, fit_bspline_patch
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
def bump_plate(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("bump-plate")
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["bspline-bump-plate"], root)
    return root / "bspline-bump-plate"


def _load(directory: Path) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(directory / FIXTURE_STL_NAME, process=True)
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


def test_surface_fit_recovers_synthetic_bump_with_exact_boundary() -> None:
    steps = 40
    u, v = np.meshgrid(np.linspace(0, 1, steps), np.linspace(0, 1, steps), indexing="ij")
    uv = np.column_stack([u.ravel(), v.ravel()])
    size = 80.0
    points = np.column_stack(
        [
            uv[:, 0] * size,
            uv[:, 1] * size,
            6.0 * np.sin(np.pi * uv[:, 0]) * np.sin(np.pi * uv[:, 1]),
        ]
    )
    corners = np.asarray([[0, 0, 0], [size, 0, 0], [size, size, 0], [0, size, 0]], dtype=np.float64)
    fitted = fit_bspline_patch(
        uv,
        points,
        np.ones(len(points)),
        0.05,
        settings=SurfaceFitSettings(),
        rectangle_corners=corners,
    )
    assert fitted.converged
    assert fitted.maximum_distance < 0.05
    # Boundary poles are pinned exactly onto the straight crease rectangle.
    boundary = np.concatenate(
        [fitted.poles[0], fitted.poles[-1], fitted.poles[:, 0], fitted.poles[:, -1]]
    )
    assert np.abs(boundary[:, 2]).max() < 1e-12
    assert np.allclose(fitted.poles[0, 0], corners[0])
    assert np.allclose(fitted.poles[-1, -1], corners[2])


def test_parameterization_is_fold_free_on_a_bumpy_grid() -> None:
    steps = 15
    x, y = np.meshgrid(np.arange(steps, dtype=np.float64), np.arange(steps, dtype=np.float64))
    z = 1.5 * np.sin(x / 3.0) * np.cos(y / 4.0)
    vertices = np.column_stack([x.ravel(), y.ravel(), z.ravel()])
    faces = []
    for row in range(steps - 1):
        for column in range(steps - 1):
            corner = row * steps + column
            faces.append((corner, corner + steps, corner + steps + 1))
            faces.append((corner, corner + steps + 1, corner + 1))
    loop = np.concatenate(
        [
            np.arange(steps - 1),
            np.arange(steps - 1, steps * steps - 1, steps),
            np.arange(steps * steps - 1, steps * steps - steps, -1),
            np.arange(steps * steps - steps, 0, -steps),
        ]
    )
    chart = harmonic_square_parameterization(vertices, np.asarray(faces, dtype=np.int64), loop)
    assert chart.flipped_triangle_count == 0
    assert chart.uv.min() >= -1e-12 and chart.uv.max() <= 1.0 + 1e-12
    corner_uv = chart.uv[list(chart.corner_vertex_ids)]
    expected = np.asarray([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float64)
    assert np.allclose(corner_uv, expected)
    assert chart.maximum_stretch < 100.0


@pytest.mark.geometry
def test_reconstructs_bump_plate_as_hybrid_curved_solid(bump_plate: Path) -> None:
    manifest = json.loads((bump_plate / FIXTURE_MANIFEST_NAME).read_text(encoding="utf-8"))
    mesh = _load(bump_plate)
    result = reconstruct_single_patch_plate(mesh, settings=SETTINGS)

    assert result.face_surfaces["bspline"] == 1
    assert result.face_surfaces["plane"] == 5
    assert len(result.solid.Faces()) == 6
    assert result.fitted.converged
    assert result.chart.flipped_triangle_count == 0
    assert result.comparison.maximum_distance_mm <= 0.3

    ground_truth_volume = manifest["groundTruth"]["volume"]
    assert result.solid.Volume() == pytest.approx(ground_truth_volume, rel=5e-3)


@pytest.mark.geometry
def test_bump_plate_step_roundtrip_retains_bspline_face(bump_plate: Path, tmp_path: Path) -> None:
    mesh = _load(bump_plate)
    result = reconstruct_single_patch_plate(mesh, settings=SETTINGS)
    report = export_step_validated(result.solid, tmp_path / "curved.step")
    assert report.valid
    reimported = import_step_shape(tmp_path / "curved.step")
    surfaces = classify_face_surfaces(reimported)
    assert surfaces["bspline"] == 1
    assert surfaces["plane"] == 5
    assert len(reimported.Faces()) == 6


@pytest.mark.geometry
def test_reconstruction_is_deterministic(bump_plate: Path, tmp_path: Path) -> None:
    mesh = _load(bump_plate)
    first = reconstruct_single_patch_plate(mesh, settings=SETTINGS)
    second = reconstruct_single_patch_plate(mesh, settings=SETTINGS)
    assert np.array_equal(first.fitted.poles, second.fitted.poles)
    shas = []
    for run in ("a", "b"):
        result = reconstruct_single_patch_plate(mesh, settings=SETTINGS)
        report = export_step_validated(result.solid, tmp_path / run / "curved.step")
        shas.append(report.sha256)
    assert shas[0] == shas[1]


@pytest.mark.geometry
def test_rejects_topology_beyond_single_patch(tmp_path: Path) -> None:
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["wavy-slab"], tmp_path)
    mesh = trimesh.load_mesh(tmp_path / "wavy-slab" / FIXTURE_STL_NAME, process=True)
    assert isinstance(mesh, trimesh.Trimesh)
    with pytest.raises(CurvedPatchError) as excinfo:
        reconstruct_single_patch_plate(mesh, settings=SETTINGS)
    assert excinfo.value.code == "curved_patch_unsupported_topology"
