from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import cast

import cadquery as cq
import numpy as np
import pytest
import trimesh
from mesh2param.comparison import ComparisonSettings, mesh_from_shape
from mesh2param.inference import build_prismatic_cadgraph, compile_candidate
from mesh2param.prismatic import (
    ArcPrimitive,
    LinePrimitive,
    PrismaticSettings,
    ProjectedLoop,
    detect_extrusion_candidate,
    extract_cap_boundary_loops,
    fit_arc_primitive,
    fit_closed_line_arc_chain,
    fit_extrusion_axis,
    fit_line_primitive,
    make_projection_frame,
    match_projected_loops,
    project_loop_to_plane,
    validate_prismatic_candidate,
)
from mesh2param.reconstruction import (
    PrismaticReconstructionResult,
    ReconstructionSettings,
    reconstruct_file,
)
from mesh2param.segmentation import segment_mesh
from mesh2param.validation import (
    classify_face_surfaces,
    export_step_validated,
    import_step_shape,
)
from mesh2param_contracts.models import ExtrusionFeature

STRICT_FIT = PrismaticSettings(
    line_rms_tolerance_mm=0.01,
    line_max_residual_tolerance_mm=0.02,
    arc_rms_tolerance_mm=0.01,
    arc_max_residual_tolerance_mm=0.02,
    minimum_arc_sagitta_mm=0.01,
)

_rotation_matrix: Callable[[float, tuple[float, float, float]], np.ndarray] = (
    trimesh.transformations.rotation_matrix
)


def _d_profile_shape(distance: float = 20.0) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .moveTo(0.0, 0.0)
        .lineTo(10.0, 0.0)
        .threePointArc((15.0, 5.0), (10.0, 10.0))
        .lineTo(0.0, 10.0)
        .close()
        .extrude(distance)
    )


def _d_profile_points() -> np.ndarray:
    points: list[tuple[float, float]] = []
    points.extend((x, 0.0) for x in np.linspace(0.0, 10.0, 11)[:-1])
    points.extend(
        (10.0 + 5.0 * math.sin(angle), 5.0 - 5.0 * math.cos(angle))
        for angle in np.linspace(0.0, math.pi, 31)[:-1]
    )
    points.extend((x, 10.0) for x in np.linspace(10.0, 0.0, 11)[:-1])
    points.extend((0.0, y) for y in np.linspace(10.0, 0.0, 11)[:-1])
    return np.asarray(points)


def _source(triangle_count: int) -> dict[str, object]:
    return {
        "sha256": "0" * 64,
        "format": "stl",
        "originalFileName": "synthetic.stl",
        "byteSize": 1,
        "triangleCount": triangle_count,
        "units": "mm",
        "scaleFactor": 1.0,
    }


def test_extrusion_axis_fitting_from_synthetic_side_normals() -> None:
    axis = np.asarray((1.0, 2.0, 3.0))
    axis /= np.linalg.norm(axis)
    frame = make_projection_frame(axis, np.zeros(3))
    u, v = np.asarray(frame.u), np.asarray(frame.v)
    normals = np.asarray([u, -u, v, -v, (u + v) / math.sqrt(2)])
    fitted, residual = fit_extrusion_axis(normals, np.asarray((1, 2, 3, 4, 2)))
    assert abs(float(np.dot(fitted, axis))) == pytest.approx(1.0, abs=1e-12)
    assert residual < 1e-12


def test_boundary_edge_extraction_and_ordered_traversal() -> None:
    mesh = trimesh.Trimesh(
        vertices=np.asarray(((0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0))),
        faces=np.asarray(((0, 1, 2), (0, 2, 3))),
        process=False,
    )
    loops = extract_cap_boundary_loops(mesh, (0, 1))
    assert len(loops) == 1
    assert loops[0][0] == 0
    assert set(loops[0]) == {0, 1, 2, 3}
    assert len(loops[0]) == 4


def test_projection_inverse_round_trip_for_arbitrary_plane() -> None:
    axis = np.asarray((2.0, -1.0, 3.0))
    axis /= np.linalg.norm(axis)
    origin = np.asarray((7.0, -4.0, 2.0))
    frame = make_projection_frame(axis, origin)
    planar = np.asarray(((0.0, 0.0), (3.0, 0.0), (3.0, 2.0), (0.0, 2.0)))
    world = frame.inverse(planar)
    loop = project_loop_to_plane(world, axis, origin=origin, frame=frame)
    assert np.allclose(frame.inverse(loop.array), world)


def test_line_and_arc_fitting_with_rejections() -> None:
    line_points = np.column_stack((np.linspace(0.0, 10.0, 21), np.zeros(21)))
    line = fit_line_primitive(line_points, STRICT_FIT)
    assert isinstance(line, LinePrimitive)
    assert line.length_mm == pytest.approx(10.0)

    angles = np.linspace(-0.3, 1.2, 25)
    arc_points = np.column_stack((2.0 + 4.0 * np.cos(angles), -3.0 + 4.0 * np.sin(angles)))
    arc = fit_arc_primitive(arc_points, STRICT_FIT)
    assert isinstance(arc, ArcPrimitive)
    assert arc.radius_mm == pytest.approx(4.0, abs=1e-8)
    assert arc.sweep_deg == pytest.approx(math.degrees(1.5), abs=1e-6)

    nearly_collinear = np.column_stack(
        (np.linspace(0.0, 5.0, 12), 1e-7 * np.sin(np.linspace(0.0, math.pi, 12)))
    )
    assert fit_arc_primitive(nearly_collinear, STRICT_FIT) is None

    noisy = arc_points.copy()
    noisy[12] += np.asarray((0.2, -0.2))
    assert fit_arc_primitive(noisy, STRICT_FIT) is None

    coarse_polygon = np.column_stack(
        (
            5.0 * np.cos(np.linspace(0.0, 4.0 * math.pi / 3.0, 5)),
            5.0 * np.sin(np.linspace(0.0, 4.0 * math.pi / 3.0, 5)),
        )
    )
    assert fit_arc_primitive(coarse_polygon, STRICT_FIT) is None


def test_closed_cyclic_segmentation_and_exact_endpoint_continuity() -> None:
    chain = fit_closed_line_arc_chain(_d_profile_points(), STRICT_FIT)
    assert [primitive.kind for primitive in chain].count("line") == 3
    assert [primitive.kind for primitive in chain].count("arc") == 1
    for primitive, following in zip(chain, (*chain[1:], chain[0]), strict=True):
        assert primitive.end == following.start
        assert primitive.tangent_to_next_deg is not None


def test_loop_matching_accepts_cyclic_shift_and_reversed_winding() -> None:
    frame = make_projection_frame(np.asarray((0.0, 0.0, 1.0)), np.zeros(3))
    points = ((0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0))
    left = ProjectedLoop((0, 1, 2, 3), points, frame, 8.0)
    shifted = ProjectedLoop((2, 3, 0, 1), points[2:] + points[:2], frame, 8.0)
    reversed_loop = ProjectedLoop((0, 3, 2, 1), tuple(reversed(points)), frame, -8.0)
    assert match_projected_loops(left, shifted, 1e-9)[0]
    matched, residual, _, reversed_winding = match_projected_loops(left, reversed_loop, 1e-9)
    assert matched and residual < 1e-12 and reversed_winding


@pytest.mark.geometry
def test_rotated_line_arc_extrusion_compiles_to_analytic_surfaces(tmp_path: Path) -> None:
    mesh = mesh_from_shape(_d_profile_shape(), linear_tolerance=0.05, angular_tolerance=0.08)
    rotation_matrix = cast(
        Callable[[float, tuple[float, float, float]], np.ndarray],
        trimesh.transformations.rotation_matrix,
    )
    transform = rotation_matrix(0.73, (1.0, 2.0, -0.5))
    transform[:3, 3] = np.asarray((17.0, -9.0, 4.0))
    mesh.apply_transform(transform)
    segmentation = segment_mesh(mesh)
    assert segmentation.counts_by_type["freeform"] >= 1

    candidate = validate_prismatic_candidate(detect_extrusion_candidate(mesh, segmentation.patches))
    assert candidate.accepted
    assert candidate.distance_mm == pytest.approx(20.0, abs=1e-7)
    assert candidate.axis is not None
    assert max(abs(value) for value in candidate.axis) < 0.99
    assert [primitive.kind for primitive in candidate.profiles[0]].count("line") == 3
    assert [primitive.kind for primitive in candidate.profiles[0]].count("arc") == 1

    graph = build_prismatic_cadgraph(source=_source(len(mesh.faces)), candidate=candidate)
    compiled = compile_candidate("rotated-prismatic", graph)
    assert compiled.valid and compiled.shape is not None
    surfaces = classify_face_surfaces(compiled.shape)
    assert surfaces["plane"] == 5
    assert surfaces["cylinder"] == 1
    step = export_step_validated(compiled.shape, tmp_path / "rotated.step")
    assert step.valid


@pytest.mark.geometry
def test_automatic_reconstruction_uses_prismatic_path(tmp_path: Path) -> None:
    mesh = mesh_from_shape(_d_profile_shape(), linear_tolerance=0.05, angular_tolerance=0.08)
    source = tmp_path / "d-profile.stl"
    mesh.export(source)
    result = reconstruct_file(
        source,
        tmp_path / "result",
        settings=ReconstructionSettings(
            comparison=ComparisonSettings(sample_count_each_direction=96)
        ),
    )
    assert isinstance(result, PrismaticReconstructionResult)
    assert result.prismatic.accepted
    serialized = result.to_dict()
    assert serialized["selectedCandidate"] == "analytic-prismatic"
    assert [candidate["label"] for candidate in serialized["candidates"]] == ["analytic-prismatic"]
    assert [feature.operation for feature in result.graph.features] == ["extrusion"]
    assert all(feature.operation != "importedFaceted" for feature in result.graph.features)
    entity_kinds = [entity.kind for entity in result.graph.sketches[0].entities]
    assert entity_kinds.count("line") == 3
    assert entity_kinds.count("circularArc") == 1
    assert entity_kinds.count("closedProfile") == 1
    assert result.step.valid


@pytest.mark.geometry
def test_polygonal_stl_hole_becomes_one_analytic_step_cylinder(tmp_path: Path) -> None:
    exact = cq.Workplane("XY").box(20.0, 20.0, 4.0).faces(">Z").workplane().hole(4.0)
    mesh = mesh_from_shape(exact, linear_tolerance=0.5, angular_tolerance=0.5)
    segmentation = segment_mesh(mesh)
    recovered = [
        patch
        for patch in segmentation.patches
        if patch.kind == "cylinder" and patch.recovered_from_facets
    ]
    assert len(recovered) == 1
    assert recovered[0].facet_sagitta_mm == pytest.approx(0.0145823, abs=1e-5)

    source = tmp_path / "polygonal-hole.stl"
    mesh.export(source)
    result = reconstruct_file(
        source,
        tmp_path / "polygonal-hole-result",
        settings=ReconstructionSettings(
            comparison=ComparisonSettings(sample_count_each_direction=96)
        ),
    )
    assert isinstance(result, PrismaticReconstructionResult)
    entity_kinds = [entity.kind for entity in result.graph.sketches[0].entities]
    assert entity_kinds.count("circle") == 1
    assert entity_kinds.count("circularArc") == 0
    assert entity_kinds.count("line") == 4
    assert result.step.source.face_count == 7
    assert result.selected.shape is not None
    assert classify_face_surfaces(result.selected.shape)["cylinder"] == 1
    reimported = import_step_shape(result.step.path)
    assert classify_face_surfaces(reimported)["cylinder"] == 1


def test_non_prismatic_mesh_is_rejected_with_diagnostic() -> None:
    mesh = trimesh.creation.icosphere(subdivisions=2, radius=5.0)
    candidate = detect_extrusion_candidate(mesh, segment_mesh(mesh).patches)
    assert not candidate.accepted
    assert candidate.diagnostics
    assert candidate.diagnostics[0].code == "no_opposing_planar_caps"


@pytest.mark.geometry
def test_supplied_stand_regression_when_fixture_is_available(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "stand.stl"
    if not fixture.is_file():
        pytest.skip("stand.stl was not present in the supplied attachment mount")
    result = reconstruct_file(
        fixture,
        tmp_path / "stand",
        settings=ReconstructionSettings(
            comparison=ComparisonSettings(sample_count_each_direction=256)
        ),
    )
    assert isinstance(result, PrismaticReconstructionResult)
    entities = result.graph.sketches[0].entities
    assert sum(entity.kind == "line" for entity in entities) == 6
    assert sum(entity.kind == "circularArc" for entity in entities) == 8
    assert sum(entity.kind == "closedProfile" for entity in entities) == 1
    feature = result.graph.features[0]
    assert isinstance(feature, ExtrusionFeature)
    assert feature.distance == pytest.approx(60.0, abs=0.05)
    assert result.step.source.face_count < 32
    assert result.selected.shape is not None
    surfaces = classify_face_surfaces(result.selected.shape)
    assert surfaces["plane"] >= 8
    assert surfaces["cylinder"] >= 8
    assert result.step.valid
