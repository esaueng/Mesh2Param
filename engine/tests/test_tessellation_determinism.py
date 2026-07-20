from __future__ import annotations

from pathlib import Path
from typing import cast

import cadquery as cq
from mesh2param.tessellation import (
    Tessellation,
    TessellationCache,
    canonicalize_tessellation,
    tessellate_shape,
    transform_tessellation,
    write_binary_stl,
    write_glb,
    write_obj,
)


def _square_meshes() -> tuple[Tessellation, Tessellation]:
    first = Tessellation(
        vertices=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)),
        triangles=((0, 1, 2), (0, 2, 3)),
        normals=(),
    )
    # Same winding and geometry with shuffled vertices, shuffled triangles,
    # cyclic rotations, and sub-micron representation noise.
    second = Tessellation(
        vertices=(
            (1.0 + 1e-8, 1.0, 0.0),
            (0.0, 0.0, 0.0),
            (0.0, 1.0 - 1e-8, 0.0),
            (1.0, 0.0 + 1e-8, 0.0),
        ),
        triangles=((0, 2, 1), (3, 0, 1)),
        normals=(),
    )
    return first, second


def test_canonicalization_is_independent_of_vertex_and_triangle_order() -> None:
    first, second = _square_meshes()

    canonical_first = canonicalize_tessellation(first)
    canonical_second = canonicalize_tessellation(second)

    assert canonical_first == canonical_second
    for triangle in canonical_first.triangles:
        vertices = tuple(canonical_first.vertices[index] for index in triangle)
        assert vertices[0] == min(vertices)


def test_direct_stl_and_glb_writers_are_byte_stable(tmp_path: Path) -> None:
    first, second = _square_meshes()

    first_stl = write_binary_stl(first, tmp_path / "first.stl")
    second_stl = write_binary_stl(second, tmp_path / "second.stl")
    first_glb = write_glb(first, tmp_path / "first.glb")
    second_glb = write_glb(second, tmp_path / "second.glb")
    first_obj = write_obj(first, tmp_path / "first.obj")
    second_obj = write_obj(second, tmp_path / "second.obj")

    assert first_stl.sha256 == second_stl.sha256
    assert (tmp_path / "first.stl").read_bytes() == (tmp_path / "second.stl").read_bytes()
    assert first_glb.sha256 == second_glb.sha256
    assert (tmp_path / "first.glb").read_bytes() == (tmp_path / "second.glb").read_bytes()
    assert (tmp_path / "first.glb").read_bytes()[:4] == b"glTF"
    assert first_obj.sha256 == second_obj.sha256
    assert (tmp_path / "first.obj").read_bytes() == (tmp_path / "second.obj").read_bytes()
    assert (tmp_path / "first.obj").read_text(encoding="ascii").startswith(
        "# Mesh2Param deterministic OBJ\n"
    )


def test_transform_tessellation_can_be_exported_without_a_brep(tmp_path: Path) -> None:
    source, _ = _square_meshes()
    transformed = transform_tessellation(
        source,
        lambda point: (point[0] + 3.0, point[1] - 2.0, point[2] + 7.5),
    )

    artifact = write_binary_stl(transformed, tmp_path / "transformed.stl")

    assert artifact.vertex_count == 4
    assert artifact.triangle_count == 2
    assert min(vertex[0] for vertex in transformed.vertices) == 3.0
    assert min(vertex[1] for vertex in transformed.vertices) == -2.0
    assert {vertex[2] for vertex in transformed.vertices} == {7.5}


def test_lod_tessellation_is_independent_of_cached_mesh_order() -> None:
    def cylinder() -> cq.Shape:
        return cast(cq.Shape, cq.Workplane("XY").circle(10).extrude(5).val())

    shared = cylinder()
    high_after_clean = tessellate_shape(shared, linear_tolerance=0.05, angular_tolerance=0.02)
    low_after_high = tessellate_shape(shared, linear_tolerance=0.5, angular_tolerance=0.8)
    low_fresh = tessellate_shape(cylinder(), linear_tolerance=0.5, angular_tolerance=0.8)
    high_after_low = tessellate_shape(shared, linear_tolerance=0.05, angular_tolerance=0.02)

    assert low_after_high == low_fresh
    assert high_after_low == high_after_clean
    assert len(high_after_clean.triangles) > len(low_after_high.triangles) * 5


def test_explicit_tessellation_cache_is_bounded_and_tolerance_scoped() -> None:
    shape = cast(cq.Shape, cq.Workplane("XY").box(2, 3, 4).val())
    cache = TessellationCache(max_entries=1)

    first = tessellate_shape(shape, linear_tolerance=0.1, angular_tolerance=0.2, cache=cache)
    repeated = tessellate_shape(shape, linear_tolerance=0.1, angular_tolerance=0.2, cache=cache)
    different_lod = tessellate_shape(
        shape,
        linear_tolerance=0.2,
        angular_tolerance=0.2,
        cache=cache,
    )

    assert repeated is first
    assert different_lod is not first
    assert len(cache) == 1


def test_tessellation_rejects_non_physical_tolerances() -> None:
    shape = cast(cq.Shape, cq.Workplane("XY").box(1, 1, 1).val())

    for invalid in (0.0, -1.0, float("nan"), float("inf")):
        try:
            tessellate_shape(shape, linear_tolerance=invalid)
        except ValueError as exc:
            assert "finite and positive" in str(exc)
        else:
            raise AssertionError(f"accepted invalid linear tolerance {invalid!r}")
