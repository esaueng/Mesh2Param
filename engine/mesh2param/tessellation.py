"""Deterministic tessellation and browser/source mesh artifact writers."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cadquery as cq
from OCP.BRepTools import BRepTools

from .validation import as_shape, validate_shape

Vertex = tuple[float, float, float]
Triangle = tuple[int, int, int]
CoordinateTriangle = tuple[Vertex, Vertex, Vertex]


@dataclass(frozen=True, slots=True)
class Tessellation:
    vertices: tuple[Vertex, ...]
    triangles: tuple[Triangle, ...]
    normals: tuple[Vertex, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MeshArtifact:
    path: str
    format: str
    byte_size: int
    sha256: str
    vertex_count: int
    triangle_count: int
    linear_tolerance: float
    angular_tolerance: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normal(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
) -> tuple[float, float, float]:
    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    raw = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    magnitude = math.sqrt(sum(item * item for item in raw))
    if magnitude <= 1e-30:
        return (0.0, 0.0, 0.0)
    return tuple(item / magnitude for item in raw)  # type: ignore[return-value]


def tessellate_shape(
    value: cq.Shape | cq.Workplane,
    *,
    linear_tolerance: float = 0.1,
    angular_tolerance: float = 0.1,
) -> Tessellation:
    """Tessellate once and calculate stable area-weighted vertex normals."""

    shape = as_shape(value)
    validation = validate_shape(
        shape,
        min(linear_tolerance, 1e-3),
        angular_tolerance,
        require_tessellation=False,
    )
    if not validation.valid:
        raise ValueError("refusing to tessellate invalid B-Rep: " + "; ".join(validation.errors))
    # Feature validation and an earlier LOD may have populated OCCT's polygon
    # cache.  Clear only cached triangulation so this call honors the requested
    # deflection and remains independent of export order.
    BRepTools.Clean_s(shape.wrapped)
    raw_vertices, raw_triangles = shape.tessellate(
        max(float(linear_tolerance), 1e-6),
        max(float(angular_tolerance), 1e-6),
    )
    vertices = tuple((float(item.x), float(item.y), float(item.z)) for item in raw_vertices)
    triangles = tuple((int(item[0]), int(item[1]), int(item[2])) for item in raw_triangles)
    return canonicalize_tessellation(Tessellation(vertices, triangles, ()))


def canonicalize_tessellation(
    mesh: Tessellation,
    *,
    coordinate_resolution: float = 1e-6,
) -> Tessellation:
    """Canonicalize coordinates and triangle order while preserving winding."""

    if coordinate_resolution <= 0:
        raise ValueError("coordinate resolution must be positive")

    def quantize(vertex: Vertex) -> Vertex:
        result: list[float] = []
        for value in vertex:
            if not math.isfinite(value):
                raise ValueError("tessellation contains a non-finite coordinate")
            rounded = round(value / coordinate_resolution) * coordinate_resolution
            result.append(0.0 if rounded == 0 else float(rounded))
        return (result[0], result[1], result[2])

    rounded_vertices = tuple(quantize(vertex) for vertex in mesh.vertices)
    canonical_triangles: list[CoordinateTriangle] = []
    for raw_triangle in mesh.triangles:
        if len(raw_triangle) != 3 or any(
            index < 0 or index >= len(rounded_vertices) for index in raw_triangle
        ):
            raise ValueError(f"invalid tessellation triangle: {raw_triangle!r}")
        coordinate_triangle: CoordinateTriangle = (
            rounded_vertices[raw_triangle[0]],
            rounded_vertices[raw_triangle[1]],
            rounded_vertices[raw_triangle[2]],
        )
        if len(set(coordinate_triangle)) != 3:
            raise ValueError(
                "coordinate canonicalization collapsed a triangle; request a finer resolution"
            )
        rotations = (
            coordinate_triangle,
            (coordinate_triangle[1], coordinate_triangle[2], coordinate_triangle[0]),
            (coordinate_triangle[2], coordinate_triangle[0], coordinate_triangle[1]),
        )
        canonical_triangles.append(min(rotations))
    canonical_triangles.sort()

    vertices = tuple(sorted({vertex for triangle in canonical_triangles for vertex in triangle}))
    vertex_index = {vertex: index for index, vertex in enumerate(vertices)}
    triangles: tuple[Triangle, ...] = tuple(
        (
            vertex_index[triangle[0]],
            vertex_index[triangle[1]],
            vertex_index[triangle[2]],
        )
        for triangle in canonical_triangles
    )
    accumulators = [[0.0, 0.0, 0.0] for _ in vertices]
    for index_triangle in triangles:
        a, b, c = (vertices[index] for index in index_triangle)
        ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        area_normal = (
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        )
        for index in index_triangle:
            for component in range(3):
                accumulators[index][component] += area_normal[component]
    normals: list[tuple[float, float, float]] = []
    for raw in accumulators:
        magnitude = math.sqrt(sum(item * item for item in raw))
        if magnitude <= 1e-30:
            normals.append((0.0, 0.0, 0.0))
        else:
            normals.append((raw[0] / magnitude, raw[1] / magnitude, raw[2] / magnitude))
    return Tessellation(vertices, triangles, tuple(normals))


def transform_tessellation(
    mesh: Tessellation,
    transform: Callable[[Vertex], Vertex],
    *,
    coordinate_resolution: float = 1e-6,
) -> Tessellation:
    """Transform an existing mesh and recanonicalize it for direct artifact export."""

    transformed_vertices: list[Vertex] = []
    for vertex in mesh.vertices:
        raw = transform(vertex)
        transformed_vertices.append((float(raw[0]), float(raw[1]), float(raw[2])))
    transformed = Tessellation(tuple(transformed_vertices), mesh.triangles, ())
    return canonicalize_tessellation(transformed, coordinate_resolution=coordinate_resolution)


def _write_artifact(
    destination: Path,
    payload: bytes,
    artifact_format: str,
    mesh: Tessellation,
    linear_tolerance: float,
    angular_tolerance: float,
) -> MeshArtifact:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return MeshArtifact(
        path=str(destination),
        format=artifact_format,
        byte_size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        vertex_count=len(mesh.vertices),
        triangle_count=len(mesh.triangles),
        linear_tolerance=linear_tolerance,
        angular_tolerance=angular_tolerance,
    )


def write_binary_stl(
    mesh: Tessellation,
    path: str | Path,
    *,
    linear_tolerance: float = 0.1,
    angular_tolerance: float = 0.1,
) -> MeshArtifact:
    """Write an already tessellated mesh as canonical byte-stable binary STL."""

    destination = Path(path)
    if destination.suffix.lower() != ".stl":
        raise ValueError("STL output must use a .stl extension")
    mesh = canonicalize_tessellation(mesh)
    payload = bytearray(b"Mesh2Param deterministic binary STL".ljust(80, b"\0"))
    payload.extend(struct.pack("<I", len(mesh.triangles)))
    for triangle in mesh.triangles:
        a, b, c = (mesh.vertices[index] for index in triangle)
        normal = _normal(a, b, c)
        payload.extend(struct.pack("<12fH", *normal, *a, *b, *c, 0))
    return _write_artifact(
        destination,
        bytes(payload),
        "stl",
        mesh,
        linear_tolerance,
        angular_tolerance,
    )


def export_binary_stl(
    value: cq.Shape | cq.Workplane,
    path: str | Path,
    *,
    linear_tolerance: float = 0.1,
    angular_tolerance: float = 0.1,
) -> MeshArtifact:
    """Tessellate once and write canonical byte-stable binary STL."""

    mesh = tessellate_shape(
        value,
        linear_tolerance=linear_tolerance,
        angular_tolerance=angular_tolerance,
    )
    return write_binary_stl(
        mesh,
        path,
        linear_tolerance=linear_tolerance,
        angular_tolerance=angular_tolerance,
    )


def _pad4(payload: bytes, byte: bytes) -> bytes:
    remainder = len(payload) % 4
    return payload if remainder == 0 else payload + byte * (4 - remainder)


def write_glb(
    mesh: Tessellation,
    path: str | Path,
    *,
    linear_tolerance: float = 0.1,
    angular_tolerance: float = 0.1,
) -> MeshArtifact:
    """Write an already tessellated mesh as minimal deterministic glTF 2.0."""

    destination = Path(path)
    if destination.suffix.lower() != ".glb":
        raise ValueError("GLB output must use a .glb extension")
    mesh = canonicalize_tessellation(mesh)

    positions = b"".join(struct.pack("<3f", *vertex) for vertex in mesh.vertices)
    normals = b"".join(struct.pack("<3f", *normal) for normal in mesh.normals)
    indices = b"".join(
        struct.pack("<I", index) for triangle in mesh.triangles for index in triangle
    )
    position_offset = 0
    normal_offset = len(positions)
    index_offset = normal_offset + len(normals)
    binary = _pad4(positions + normals + indices, b"\0")
    mins = [min(vertex[index] for vertex in mesh.vertices) for index in range(3)]
    maxes = [max(vertex[index] for vertex in mesh.vertices) for index in range(3)]
    document = {
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": len(mesh.vertices),
                "max": maxes,
                "min": mins,
                "type": "VEC3",
            },
            {
                "bufferView": 1,
                "componentType": 5126,
                "count": len(mesh.normals),
                "type": "VEC3",
            },
            {
                "bufferView": 2,
                "componentType": 5125,
                "count": len(mesh.triangles) * 3,
                "max": [len(mesh.vertices) - 1],
                "min": [0],
                "type": "SCALAR",
            },
        ],
        "asset": {"generator": "Mesh2Param", "version": "2.0"},
        "bufferViews": [
            {
                "buffer": 0,
                "byteLength": len(positions),
                "byteOffset": position_offset,
                "target": 34962,
            },
            {"buffer": 0, "byteLength": len(normals), "byteOffset": normal_offset, "target": 34962},
            {"buffer": 0, "byteLength": len(indices), "byteOffset": index_offset, "target": 34963},
        ],
        "buffers": [{"byteLength": len(binary)}],
        "meshes": [
            {
                "name": "Mesh2Param result",
                "primitives": [
                    {
                        "attributes": {"NORMAL": 1, "POSITION": 0},
                        "indices": 2,
                        "mode": 4,
                    }
                ],
            }
        ],
        "nodes": [{"mesh": 0, "name": "Mesh2Param result"}],
        "scene": 0,
        "scenes": [{"nodes": [0]}],
    }
    json_chunk = _pad4(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        b" ",
    )
    total_length = 12 + 8 + len(json_chunk) + 8 + len(binary)
    payload = b"".join(
        (
            struct.pack("<4sII", b"glTF", 2, total_length),
            struct.pack("<I4s", len(json_chunk), b"JSON"),
            json_chunk,
            struct.pack("<I4s", len(binary), b"BIN\0"),
            binary,
        )
    )
    return _write_artifact(
        destination,
        payload,
        "glb",
        mesh,
        linear_tolerance,
        angular_tolerance,
    )


def export_glb(
    value: cq.Shape | cq.Workplane,
    path: str | Path,
    *,
    linear_tolerance: float = 0.1,
    angular_tolerance: float = 0.1,
) -> MeshArtifact:
    """Tessellate once and write a deterministic GLB artifact."""

    mesh = tessellate_shape(
        value,
        linear_tolerance=linear_tolerance,
        angular_tolerance=angular_tolerance,
    )
    return write_glb(
        mesh,
        path,
        linear_tolerance=linear_tolerance,
        angular_tolerance=angular_tolerance,
    )


__all__ = [
    "MeshArtifact",
    "Tessellation",
    "canonicalize_tessellation",
    "export_binary_stl",
    "export_glb",
    "tessellate_shape",
    "transform_tessellation",
    "write_binary_stl",
    "write_glb",
]
