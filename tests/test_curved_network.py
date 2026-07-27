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
    CurvedNetworkSettings,
    CurvedPatchError,
    CurvedPatchSettings,
    reconstruct_plate_network,
)
from mesh2param.parameterization import cut_chart_midline, harmonic_square_parameterization
from mesh2param.surface_fit import (
    PatchSystem,
    PoleConstraint,
    SurfaceFitSettings,
    greville_abscissae,
    open_uniform_knots,
    patch_distances,
    rectangle_boundary_poles,
    solve_patch_network,
)
from mesh2param.surface_network import SurfaceNetwork, build_network_faces, shared_edge_evidence
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
SPLIT = CurvedNetworkSettings(force_split=True)

# A pole shared by two patches evaluates to the same point in exact arithmetic;
# in doubles the two evaluation paths can differ by a few units in the last
# place of a coordinate measured in millimetres. A picometre is far below any
# geometric meaning and still six orders of magnitude tighter than the sewing
# tolerance that decides whether an edge is actually shared.
COINCIDENT_POLE_TOLERANCE_MM = 1e-12


@pytest.fixture(scope="module")
def bump_plate(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("bump-plate-network")
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["bspline-bump-plate"], root)
    return root / "bspline-bump-plate"


def _load(directory: Path) -> trimesh.Trimesh:
    loaded = trimesh.load_mesh(directory / FIXTURE_STL_NAME, process=True)
    assert isinstance(loaded, trimesh.Trimesh)
    return loaded


def test_solver_aliases_shared_poles_and_enforces_c1() -> None:
    degree = 3
    spans = 4
    control = spans + degree
    knots = open_uniform_knots(control, degree)
    greville = greville_abscissae(knots, degree)
    size = 40.0

    def samples(x0: float) -> tuple[np.ndarray, np.ndarray]:
        steps = 25
        u, v = np.meshgrid(np.linspace(0, 1, steps), np.linspace(0, 1, steps), indexing="ij")
        uv = np.column_stack([u.ravel(), v.ravel()])
        x = x0 + uv[:, 0] * size
        y = uv[:, 1] * 2.0 * size
        z = 3.0 * np.sin(np.pi * x / (2.0 * size)) * np.sin(np.pi * uv[:, 1])
        return uv, np.column_stack([x, y, z])

    corners = (
        np.asarray([[0, 0, 0], [size, 0, 0], [size, 2 * size, 0], [0, 2 * size, 0]], float),
        np.asarray(
            [[size, 0, 0], [2 * size, 0, 0], [2 * size, 2 * size, 0], [size, 2 * size, 0]],
            float,
        ),
    )
    systems = []
    for side in range(2):
        uv, points = samples(side * size)
        fixed = rectangle_boundary_poles(corners[side], greville, greville)
        for j in range(1, control - 1):
            del fixed[(control - 1, j) if side == 0 else (0, j)]
        systems.append(
            PatchSystem(uv=uv, points=points, weights=np.ones(len(uv)), fixed_poles=fixed)
        )
    shared = [((0, (control - 1, j)), (1, (0, j))) for j in range(control)]
    constraints = [
        PoleConstraint(
            entries=((0, (control - 2, j), 1.0), (1, (1, j), 1.0), (0, (control - 1, j), -2.0)),
            target=np.zeros(3),
        )
        for j in range(control)
    ]
    poles = solve_patch_network(
        systems,
        knots,
        knots,
        3,
        shared_poles=shared,
        constraints=constraints,
        constraint_weight=10.0,
    )
    assert np.array_equal(poles[0][-1], poles[1][0])
    for side in range(2):
        residuals = patch_distances(
            systems[side].uv, systems[side].points, poles[side], knots, knots, 3
        )
        assert residuals.max() < 0.1
    # C1 mirror condition across the shared column, up to the soft penalty.
    mirror = poles[0][-2] + poles[1][1] - 2.0 * poles[0][-1]
    assert np.linalg.norm(mirror, axis=1).max() < 0.05


def test_cut_chart_midline_produces_two_disk_halves(bump_plate: Path) -> None:
    from mesh2param.curved_patch import _plate_context

    mesh = _load(bump_plate)
    context = _plate_context(mesh, SETTINGS)
    cut = cut_chart_midline(context.chart_vertices, context.chart_faces, context.chart)
    assert len(cut.path_vertex_ids) >= 3
    for half in (cut.half_a, cut.half_b):
        chart = harmonic_square_parameterization(
            half.vertices,
            half.faces,
            half.boundary_loop,
            corner_loop_positions=np.asarray(half.corner_positions, dtype=np.int64),
        )
        assert chart.flipped_triangle_count == 0
    total = len(cut.half_a.faces) + len(cut.half_b.faces)
    assert total >= len(context.chart_faces)  # edge splits add triangles


@pytest.mark.geometry
def test_single_patch_path_through_network_api(bump_plate: Path) -> None:
    mesh = _load(bump_plate)
    result = reconstruct_plate_network(mesh, settings=SETTINGS)
    assert len(result.network.patches) == 1
    assert len(result.network.curves) == 0
    assert result.face_surfaces["bspline"] == 1
    assert result.face_surfaces["plane"] == 5
    assert result.shared_evidence == ()


@pytest.mark.geometry
def test_forced_split_builds_shared_topology_network(bump_plate: Path) -> None:
    manifest = json.loads((bump_plate / FIXTURE_MANIFEST_NAME).read_text(encoding="utf-8"))
    mesh = _load(bump_plate)
    result = reconstruct_plate_network(mesh, settings=SETTINGS, network_settings=SPLIT)

    assert len(result.network.patches) == 2
    assert len(result.network.curves) == 1
    assert result.face_surfaces["bspline"] == 2
    assert result.face_surfaces["plane"] == 5
    assert len(result.solid.Faces()) == 7
    # Euler check: the shared edge is common topology, not two coincident edges.
    assert len(result.solid.Edges()) == 15
    assert result.residual_maximum <= SETTINGS.fit_tolerance_mm

    (evidence,) = result.shared_evidence
    assert evidence.continuity == "smooth"
    # Aliased poles: G0 is exact by construction, so the only permissible gap is
    # the residue of evaluating the same pole through two surface parameterisations.
    # Comparing to a literal 0.0 asserts the arithmetic, not the construction, and
    # holds only on the platform it was written on: x86-64 leaves 7.1e-15 mm here.
    assert evidence.maximum_position_gap == pytest.approx(0.0, abs=COINCIDENT_POLE_TOLERANCE_MM)
    assert evidence.maximum_normal_angle_deg <= SPLIT.g1_maximum_angle_deg

    assert result.solid.Volume() == pytest.approx(manifest["groundTruth"]["volume"], rel=5e-3)


@pytest.mark.geometry
def test_split_step_roundtrip_retains_both_bspline_faces(bump_plate: Path, tmp_path: Path) -> None:
    mesh = _load(bump_plate)
    result = reconstruct_plate_network(mesh, settings=SETTINGS, network_settings=SPLIT)
    report = export_step_validated(result.solid, tmp_path / "network.step")
    assert report.valid
    reimported = import_step_shape(tmp_path / "network.step")
    surfaces = classify_face_surfaces(reimported)
    assert surfaces["bspline"] == 2
    assert surfaces["plane"] == 5
    assert len(reimported.Faces()) == 7


@pytest.mark.geometry
def test_network_artifact_roundtrip_and_determinism(bump_plate: Path, tmp_path: Path) -> None:
    mesh = _load(bump_plate)
    first = reconstruct_plate_network(mesh, settings=SETTINGS, network_settings=SPLIT)
    second = reconstruct_plate_network(mesh, settings=SETTINGS, network_settings=SPLIT)
    assert first.artifact_sha256 == second.artifact_sha256

    rebuilt = SurfaceNetwork.from_artifact(json.loads(first.network.artifact_bytes()))
    assert rebuilt.artifact_sha256() == first.artifact_sha256
    faces, edges = build_network_faces(rebuilt)
    assert len(faces) == 2
    assert len(edges) == 1
    original = [entry.to_dict() for entry in first.shared_evidence]
    rebuilt_evidence = [entry.to_dict() for entry in shared_edge_evidence(rebuilt)]
    assert original == rebuilt_evidence

    shas = []
    for run, result in (("a", first), ("b", second)):
        report = export_step_validated(result.solid, tmp_path / run / "network.step")
        shas.append(report.sha256)
    assert shas[0] == shas[1]


@pytest.mark.geometry
def test_auto_split_falls_through_when_single_patch_budget_fails(bump_plate: Path) -> None:
    mesh = _load(bump_plate)
    # A tolerance below the tessellation chordal floor: neither layout can
    # converge, but the failure must come from the NETWORK fit, proving the
    # driver fell through from the failed single-patch attempt to the split.
    strict = CurvedPatchSettings(
        fit_tolerance_mm=0.01,
        surface_deviation_tolerance_mm=0.3,
        comparison_sample_count=200,
        fit=SurfaceFitSettings(maximum_refinements=1),
    )
    with pytest.raises(CurvedPatchError) as excinfo:
        reconstruct_plate_network(mesh, settings=strict)
    assert excinfo.value.code == "curved_patch_tolerance_not_met"
    assert "network" in str(excinfo.value)
