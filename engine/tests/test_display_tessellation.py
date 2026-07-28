from __future__ import annotations

import json
import math
import struct
from itertools import pairwise
from pathlib import Path
from typing import cast

import cadquery as cq
import pytest
from mesh2param import tessellation as tessellation_module
from mesh2param.tessellation import (
    display_tessellation,
    sample_shape_edges,
    tessellate_shape,
    write_glb,
)
from mesh2param.tolerances import DISPLAY_TESSELLATION_RELATIVE_LINEAR_DEFLECTION


def _cylinder(diameter: float) -> cq.Shape:
    return cast(cq.Shape, cq.Workplane("XY").circle(diameter / 2).extrude(diameter).val())


def _maximum_angular_gap(points: list[tuple[float, float]]) -> float:
    angles = sorted({round(math.atan2(y, x) % (2 * math.pi), 12) for x, y in points})
    gaps = [right - left for left, right in pairwise(angles)]
    gaps.append(angles[0] + 2 * math.pi - angles[-1])
    return max(gaps)


def test_edge_polyline_budget_accounts_for_retained_endpoints() -> None:
    polylines = [
        tuple((float(polyline), float(point), 0.0) for point in range(segment_count + 1))
        for polyline, segment_count in enumerate((1, 3, 1, 3))
    ]

    bounded = tessellation_module._bound_edge_polylines(polylines, maximum_segments=4)

    assert sum(len(polyline) - 1 for polyline in bounded) == 4
    pairs = tuple(zip(bounded, polylines, strict=True))
    assert all(polyline[0] == source[0] for polyline, source in pairs)
    assert all(polyline[-1] == source[-1] for polyline, source in pairs)


@pytest.mark.parametrize("diameter", [1.0, 10.0, 100.0])
def test_exact_cylinders_have_smooth_scale_independent_display_lod(diameter: float) -> None:
    shape = _cylinder(diameter)
    radius = diameter / 2

    assert [face.geomType() for face in shape.Faces()].count("CYLINDER") == 1
    assert [edge.geomType() for edge in shape.Edges()].count("CIRCLE") == 2

    settings = display_tessellation(
        shape,
        maximum_linear_tolerance=diameter,
        maximum_angular_tolerance=0.2,
    )
    assert settings.linear_tolerance == pytest.approx(
        math.sqrt(3) * diameter * DISPLAY_TESSELLATION_RELATIVE_LINEAR_DEFLECTION
    )
    mesh = tessellate_shape(
        shape,
        linear_tolerance=settings.linear_tolerance,
        angular_tolerance=settings.angular_tolerance,
    )
    edges = sample_shape_edges(
        shape,
        linear_tolerance=settings.linear_tolerance,
        angular_tolerance=settings.edge_angular_tolerance,
    )

    top_ring = [
        (x, y)
        for x, y, z in mesh.vertices
        if math.isclose(z, diameter, rel_tol=0, abs_tol=1e-6) and math.hypot(x, y) >= radius * 0.99
    ]
    mesh_gap = _maximum_angular_gap(top_ring)
    circular_edges = [
        polyline
        for polyline in edges
        if len(polyline) > 2
        and all(
            math.isclose(math.hypot(x, y), radius, rel_tol=0, abs_tol=max(diameter * 1e-6, 1e-6))
            for x, y, _z in polyline
        )
    ]

    assert len(circular_edges) == 2
    assert len(mesh.triangles) < 4_000
    assert max(len(polyline) - 1 for polyline in circular_edges) <= 1_000
    assert min(len(polyline) - 1 for polyline in circular_edges) >= 700

    # A normal fit view and a 10x close view both keep the largest surface
    # chord comfortably below a tenth of a screen pixel.
    mesh_sagitta = radius * (1 - math.cos(mesh_gap / 2))
    edge_sagitta = radius * (
        1 - math.cos(_maximum_angular_gap([(x, y) for x, y, _z in circular_edges[0]]) / 2)
    )
    for pixels_per_unit in (400 / diameter, 4_000 / diameter):
        assert mesh_sagitta * pixels_per_unit < 0.1
        assert edge_sagitta * pixels_per_unit < 0.1


def test_result_glb_carries_exact_edge_lines_separately_from_triangles(tmp_path: Path) -> None:
    shape = _cylinder(10)
    settings = display_tessellation(shape)
    mesh = tessellate_shape(
        shape,
        linear_tolerance=settings.linear_tolerance,
        angular_tolerance=settings.angular_tolerance,
    )
    edges = sample_shape_edges(
        shape,
        linear_tolerance=settings.linear_tolerance,
        angular_tolerance=settings.edge_angular_tolerance,
    )

    path = tmp_path / "cylinder.glb"
    write_glb(
        mesh,
        path,
        linear_tolerance=settings.linear_tolerance,
        angular_tolerance=settings.angular_tolerance,
        edge_polylines=edges,
    )
    payload = path.read_bytes()
    json_length = struct.unpack_from("<I", payload, 12)[0]
    document = json.loads(payload[20 : 20 + json_length])
    primitives = document["meshes"][0]["primitives"]

    assert primitives[0]["mode"] == 4
    assert primitives[1]["mode"] == 1
    assert primitives[1]["extras"]["mesh2paramAnalyticEdges"] is True
    line_index_accessor = document["accessors"][primitives[1]["indices"]]
    assert line_index_accessor["count"] >= 2 * 1_400
