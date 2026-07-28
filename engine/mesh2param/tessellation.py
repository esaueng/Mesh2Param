"""Deterministic tessellation and browser/source mesh artifact writers."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import weakref
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cadquery as cq
from OCP.Bnd import Bnd_Box
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepTools import BRepTools
from OCP.GCPnts import GCPnts_TangentialDeflection

from .tolerances import (
    DEFAULT_TESSELLATION_ANGULAR_TOLERANCE_RAD,
    DEFAULT_TESSELLATION_COORDINATE_RESOLUTION_MM,
    DEFAULT_TESSELLATION_LINEAR_TOLERANCE_MM,
    DEGENERATE_NORMAL_MAGNITUDE_EPSILON,
    DISPLAY_EDGE_ANGULAR_DEFLECTION_RAD,
    DISPLAY_TESSELLATION_ANGULAR_DEFLECTION_RAD,
    DISPLAY_TESSELLATION_RELATIVE_LINEAR_DEFLECTION,
    MAX_DISPLAY_EDGE_SEGMENTS,
    MINIMUM_OCCT_TESSELLATION_TOLERANCE,
    TESSELLATION_VALIDATION_LINEAR_TOLERANCE_MM,
)
from .validation import as_shape, validate_shape

Vertex = tuple[float, float, float]
Triangle = tuple[int, int, int]
CoordinateTriangle = tuple[Vertex, Vertex, Vertex]
EdgePolyline = tuple[Vertex, ...]


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


@dataclass(frozen=True, slots=True)
class DisplayTessellation:
    """Scale-aware, bounded viewport tessellation settings."""

    linear_tolerance: float
    angular_tolerance: float
    edge_angular_tolerance: float
    model_diagonal: float


@dataclass(slots=True)
class _CachedTessellation:
    shape: weakref.ReferenceType[cq.Shape]
    mesh: Tessellation


class TessellationCache:
    """Bounded cache for explicitly immutable shape instances.

    The key includes object identity and every tessellation tolerance. Callers
    must not reuse a cache after mutating a CadQuery/OCP shape in place.
    Weak references prevent the cache from extending shape lifetimes and guard
    against Python object-id reuse.
    """

    def __init__(self, *, max_entries: int = 32) -> None:
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries < 1:
            raise ValueError("tessellation cache max_entries must be a positive integer")
        self.max_entries = max_entries
        self._entries: OrderedDict[tuple[int, float, float], _CachedTessellation] = OrderedDict()

    def get(
        self,
        shape: cq.Shape,
        linear_tolerance: float,
        angular_tolerance: float,
    ) -> Tessellation | None:
        key = (id(shape), linear_tolerance, angular_tolerance)
        cached = self._entries.get(key)
        if cached is None:
            return None
        if cached.shape() is not shape:
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return cached.mesh

    def put(
        self,
        shape: cq.Shape,
        linear_tolerance: float,
        angular_tolerance: float,
        mesh: Tessellation,
    ) -> None:
        key = (id(shape), linear_tolerance, angular_tolerance)
        self._entries[key] = _CachedTessellation(weakref.ref(shape), mesh)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


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
    if magnitude <= DEGENERATE_NORMAL_MAGNITUDE_EPSILON:
        return (0.0, 0.0, 0.0)
    return tuple(item / magnitude for item in raw)  # type: ignore[return-value]


def tessellate_shape(
    value: cq.Shape | cq.Workplane,
    *,
    linear_tolerance: float = DEFAULT_TESSELLATION_LINEAR_TOLERANCE_MM,
    angular_tolerance: float = DEFAULT_TESSELLATION_ANGULAR_TOLERANCE_RAD,
    cache: TessellationCache | None = None,
) -> Tessellation:
    """Tessellate once and calculate stable area-weighted vertex normals."""

    shape = as_shape(value)
    linear_tolerance = float(linear_tolerance)
    angular_tolerance = float(angular_tolerance)
    if not math.isfinite(linear_tolerance) or linear_tolerance <= 0:
        raise ValueError("linear tessellation tolerance must be finite and positive")
    if not math.isfinite(angular_tolerance) or angular_tolerance <= 0:
        raise ValueError("angular tessellation tolerance must be finite and positive")
    if cache is not None:
        cached = cache.get(shape, linear_tolerance, angular_tolerance)
        if cached is not None:
            return cached
    validation = validate_shape(
        shape,
        min(linear_tolerance, TESSELLATION_VALIDATION_LINEAR_TOLERANCE_MM),
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
        max(linear_tolerance, MINIMUM_OCCT_TESSELLATION_TOLERANCE),
        max(angular_tolerance, MINIMUM_OCCT_TESSELLATION_TOLERANCE),
    )
    vertices = tuple((float(item.x), float(item.y), float(item.z)) for item in raw_vertices)
    triangles = tuple((int(item[0]), int(item[1]), int(item[2])) for item in raw_triangles)
    mesh = canonicalize_tessellation(Tessellation(vertices, triangles, ()))
    if cache is not None:
        cache.put(shape, linear_tolerance, angular_tolerance, mesh)
    return mesh


def display_tessellation(
    value: cq.Shape | cq.Workplane,
    *,
    maximum_linear_tolerance: float = DEFAULT_TESSELLATION_LINEAR_TOLERANCE_MM,
    maximum_angular_tolerance: float = DEFAULT_TESSELLATION_ANGULAR_TOLERANCE_RAD,
) -> DisplayTessellation:
    """Choose the single high-quality viewport LOD from exact shape bounds.

    The returned values affect display meshes only.  They never alter the
    authoritative B-Rep or STEP export, and callers may retain a stricter
    project-specific tolerance through either ``maximum_*`` argument.
    """

    shape = as_shape(value)
    maximum_linear_tolerance = float(maximum_linear_tolerance)
    maximum_angular_tolerance = float(maximum_angular_tolerance)
    if (
        not math.isfinite(maximum_linear_tolerance)
        or maximum_linear_tolerance <= 0
        or not math.isfinite(maximum_angular_tolerance)
        or maximum_angular_tolerance <= 0
    ):
        raise ValueError("display tessellation tolerances must be finite and positive")

    native = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, native, False, False)
    bounds = tuple(float(item) for item in native.Get())
    diagonal = math.hypot(
        bounds[3] - bounds[0],
        bounds[4] - bounds[1],
        bounds[5] - bounds[2],
    )
    if not math.isfinite(diagonal) or diagonal <= 0:
        scaled_linear = maximum_linear_tolerance
        diagonal = 0.0
    else:
        scaled_linear = max(
            diagonal * DISPLAY_TESSELLATION_RELATIVE_LINEAR_DEFLECTION,
            MINIMUM_OCCT_TESSELLATION_TOLERANCE,
        )
    return DisplayTessellation(
        linear_tolerance=min(maximum_linear_tolerance, scaled_linear),
        angular_tolerance=min(
            maximum_angular_tolerance,
            DISPLAY_TESSELLATION_ANGULAR_DEFLECTION_RAD,
        ),
        edge_angular_tolerance=min(
            maximum_angular_tolerance,
            DISPLAY_EDGE_ANGULAR_DEFLECTION_RAD,
        ),
        model_diagonal=diagonal,
    )


def _canonical_polyline(points: list[Vertex]) -> EdgePolyline:
    resolution = DEFAULT_TESSELLATION_COORDINATE_RESOLUTION_MM

    def quantize(point: Vertex) -> Vertex:
        values = tuple(round(value / resolution) * resolution for value in point)
        return tuple(0.0 if value == 0 else value for value in values)  # type: ignore[return-value]

    quantized: list[Vertex] = []
    for point in points:
        candidate = quantize(point)
        if not quantized or candidate != quantized[-1]:
            quantized.append(candidate)
    if len(quantized) < 2:
        return ()

    if quantized[0] != quantized[-1]:
        forward = tuple(quantized)
        reverse = tuple(reversed(quantized))
        return min(forward, reverse)

    ring = quantized[:-1]
    if len(ring) < 2:
        return ()
    minimum = min(ring)
    candidates: list[EdgePolyline] = []
    for oriented in (ring, list(reversed(ring))):
        for index, point in enumerate(oriented):
            if point != minimum:
                continue
            rotated = oriented[index:] + oriented[:index]
            candidates.append(tuple((*rotated, rotated[0])))
    return min(candidates)


def _bound_edge_polylines(
    polylines: list[EdgePolyline],
    maximum_segments: int = MAX_DISPLAY_EDGE_SEGMENTS,
) -> tuple[EdgePolyline, ...]:
    if maximum_segments < 1:
        raise ValueError("maximum display edge segments must be positive")
    if not polylines or len(polylines) > maximum_segments:
        return ()
    segment_counts = tuple(len(polyline) - 1 for polyline in polylines)
    total_segments = sum(segment_counts)
    if total_segments <= maximum_segments:
        return tuple(polylines)

    def sampled_segment_count(stride: int) -> int:
        return sum(math.ceil(count / stride) for count in segment_counts)

    lower = max(1, math.ceil(total_segments / maximum_segments))
    upper = max(segment_counts)
    while lower < upper:
        middle = lower + (upper - lower) // 2
        if sampled_segment_count(middle) <= maximum_segments:
            upper = middle
        else:
            lower = middle + 1

    bounded: list[EdgePolyline] = []
    for polyline in polylines:
        sampled = list(polyline[::lower])
        if sampled[-1] != polyline[-1]:
            sampled.append(polyline[-1])
        bounded.append(tuple(sampled))
    return tuple(bounded)


def sample_shape_edges(
    value: cq.Shape | cq.Workplane,
    *,
    linear_tolerance: float,
    angular_tolerance: float = DISPLAY_EDGE_ANGULAR_DEFLECTION_RAD,
) -> tuple[EdgePolyline, ...]:
    """Adaptively sample exact B-Rep curves for the viewport edge overlay."""

    shape = as_shape(value)
    if not math.isfinite(linear_tolerance) or linear_tolerance <= 0:
        raise ValueError("edge linear tolerance must be finite and positive")
    if not math.isfinite(angular_tolerance) or angular_tolerance <= 0:
        raise ValueError("edge angular tolerance must be finite and positive")

    polylines: list[EdgePolyline] = []
    for edge in shape.Edges():
        adaptor = BRepAdaptor_Curve(edge.wrapped)
        sampler = GCPnts_TangentialDeflection(
            adaptor,
            angular_tolerance,
            linear_tolerance,
            2,
            1e-9,
            max(linear_tolerance * 1e-3, 1e-12),
        )
        points = [
            (
                float(sampler.Value(index).X()),
                float(sampler.Value(index).Y()),
                float(sampler.Value(index).Z()),
            )
            for index in range(1, sampler.NbPoints() + 1)
        ]
        polyline = _canonical_polyline(points)
        if len(polyline) >= 2:
            polylines.append(polyline)
    return tuple(sorted(_bound_edge_polylines(polylines)))


def canonicalize_tessellation(
    mesh: Tessellation,
    *,
    coordinate_resolution: float = DEFAULT_TESSELLATION_COORDINATE_RESOLUTION_MM,
) -> Tessellation:
    """Canonicalize coordinates and triangle order while preserving winding."""

    if not math.isfinite(coordinate_resolution) or coordinate_resolution <= 0:
        raise ValueError("coordinate resolution must be finite and positive")

    def quantize(vertex: Vertex) -> Vertex:
        result: list[float] = []
        for value in vertex:
            if not math.isfinite(value):
                raise ValueError("tessellation contains a non-finite coordinate")
            rounded = round(value / coordinate_resolution) * coordinate_resolution
            result.append(0.0 if abs(rounded) <= coordinate_resolution * 0.5 else float(rounded))
        return (result[0], result[1], result[2])

    rounded_vertices = tuple(quantize(vertex) for vertex in mesh.vertices)
    canonical_triangles: list[CoordinateTriangle] = []
    for raw_triangle in mesh.triangles:
        if len(raw_triangle) != 3 or any(
            index < 0 or index >= len(rounded_vertices) for index in raw_triangle
        ):
            raise ValueError(f"invalid tessellation triangle: {raw_triangle!r}")
        raw_coordinates = tuple(mesh.vertices[index] for index in raw_triangle)
        if len(set(raw_coordinates)) != 3:
            # OCCT emits genuinely zero-area triangles at analytic poles: a
            # sphere pole or cone apex can map two UV corners to the identical
            # 3-D point. They carry no geometry; dropping them is exact.
            continue
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
        if magnitude <= DEGENERATE_NORMAL_MAGNITUDE_EPSILON:
            normals.append((0.0, 0.0, 0.0))
        else:
            normals.append((raw[0] / magnitude, raw[1] / magnitude, raw[2] / magnitude))
    return Tessellation(vertices, triangles, tuple(normals))


def transform_tessellation(
    mesh: Tessellation,
    transform: Callable[[Vertex], Vertex],
    *,
    coordinate_resolution: float = DEFAULT_TESSELLATION_COORDINATE_RESOLUTION_MM,
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
    linear_tolerance: float = DEFAULT_TESSELLATION_LINEAR_TOLERANCE_MM,
    angular_tolerance: float = DEFAULT_TESSELLATION_ANGULAR_TOLERANCE_RAD,
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
    linear_tolerance: float = DEFAULT_TESSELLATION_LINEAR_TOLERANCE_MM,
    angular_tolerance: float = DEFAULT_TESSELLATION_ANGULAR_TOLERANCE_RAD,
    cache: TessellationCache | None = None,
) -> MeshArtifact:
    """Tessellate once and write canonical byte-stable binary STL."""

    mesh = tessellate_shape(
        value,
        linear_tolerance=linear_tolerance,
        angular_tolerance=angular_tolerance,
        cache=cache,
    )
    return write_binary_stl(
        mesh,
        path,
        linear_tolerance=linear_tolerance,
        angular_tolerance=angular_tolerance,
    )


def _obj_float(value: float) -> str:
    # Adding positive zero normalizes negative zero without an exact floating-point comparison.
    return format(value + 0.0, ".17g")


def write_obj(
    mesh: Tessellation,
    path: str | Path,
    *,
    linear_tolerance: float = DEFAULT_TESSELLATION_LINEAR_TOLERANCE_MM,
    angular_tolerance: float = DEFAULT_TESSELLATION_ANGULAR_TOLERANCE_RAD,
) -> MeshArtifact:
    """Write an already tessellated mesh as canonical byte-stable OBJ."""

    destination = Path(path)
    if destination.suffix.lower() != ".obj":
        raise ValueError("OBJ output must use a .obj extension")
    mesh = canonicalize_tessellation(mesh)
    lines = ["# Mesh2Param deterministic OBJ", "o Mesh2Param_result"]
    lines.extend("v " + " ".join(_obj_float(value) for value in vertex) for vertex in mesh.vertices)
    lines.extend("vn " + " ".join(_obj_float(value) for value in normal) for normal in mesh.normals)
    lines.extend(
        "f " + " ".join(f"{index + 1}//{index + 1}" for index in triangle)
        for triangle in mesh.triangles
    )
    payload = ("\n".join(lines) + "\n").encode("ascii")
    return _write_artifact(
        destination,
        payload,
        "obj",
        mesh,
        linear_tolerance,
        angular_tolerance,
    )


def export_obj(
    value: cq.Shape | cq.Workplane,
    path: str | Path,
    *,
    linear_tolerance: float = DEFAULT_TESSELLATION_LINEAR_TOLERANCE_MM,
    angular_tolerance: float = DEFAULT_TESSELLATION_ANGULAR_TOLERANCE_RAD,
    cache: TessellationCache | None = None,
) -> MeshArtifact:
    """Tessellate once and write a deterministic OBJ artifact."""

    mesh = tessellate_shape(
        value,
        linear_tolerance=linear_tolerance,
        angular_tolerance=angular_tolerance,
        cache=cache,
    )
    return write_obj(
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
    linear_tolerance: float = DEFAULT_TESSELLATION_LINEAR_TOLERANCE_MM,
    angular_tolerance: float = DEFAULT_TESSELLATION_ANGULAR_TOLERANCE_RAD,
    edge_polylines: tuple[EdgePolyline, ...] = (),
) -> MeshArtifact:
    """Write a deterministic GLB, optionally with exact B-Rep edge samples."""

    destination = Path(path)
    if destination.suffix.lower() != ".glb":
        raise ValueError("GLB output must use a .glb extension")
    mesh = canonicalize_tessellation(mesh)

    positions = b"".join(struct.pack("<3f", *vertex) for vertex in mesh.vertices)
    normals = b"".join(struct.pack("<3f", *normal) for normal in mesh.normals)
    indices = b"".join(
        struct.pack("<I", index) for triangle in mesh.triangles for index in triangle
    )
    edge_vertices: list[Vertex] = []
    edge_indices: list[int] = []
    for polyline in edge_polylines:
        if len(polyline) < 2:
            continue
        base = len(edge_vertices)
        edge_vertices.extend(polyline)
        for index in range(len(polyline) - 1):
            edge_indices.extend((base + index, base + index + 1))
    edge_positions = b"".join(struct.pack("<3f", *vertex) for vertex in edge_vertices)
    edge_index_bytes = b"".join(struct.pack("<I", index) for index in edge_indices)
    position_offset = 0
    normal_offset = len(positions)
    index_offset = normal_offset + len(normals)
    edge_position_offset = index_offset + len(indices)
    edge_index_offset = edge_position_offset + len(edge_positions)
    binary = _pad4(
        positions + normals + indices + edge_positions + edge_index_bytes,
        b"\0",
    )
    mins = [min(vertex[index] for vertex in mesh.vertices) for index in range(3)]
    maxes = [max(vertex[index] for vertex in mesh.vertices) for index in range(3)]
    accessors: list[dict[str, Any]] = [
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
    ]
    buffer_views: list[dict[str, Any]] = [
        {
            "buffer": 0,
            "byteLength": len(positions),
            "byteOffset": position_offset,
            "target": 34962,
        },
        {"buffer": 0, "byteLength": len(normals), "byteOffset": normal_offset, "target": 34962},
        {"buffer": 0, "byteLength": len(indices), "byteOffset": index_offset, "target": 34963},
    ]
    primitives: list[dict[str, Any]] = [
        {
            "attributes": {"NORMAL": 1, "POSITION": 0},
            "indices": 2,
            "mode": 4,
        }
    ]
    if edge_vertices and edge_indices:
        edge_position_accessor = len(accessors)
        edge_index_accessor = edge_position_accessor + 1
        edge_position_view = len(buffer_views)
        edge_index_view = edge_position_view + 1
        edge_mins = [min(vertex[index] for vertex in edge_vertices) for index in range(3)]
        edge_maxes = [max(vertex[index] for vertex in edge_vertices) for index in range(3)]
        buffer_views.extend(
            (
                {
                    "buffer": 0,
                    "byteLength": len(edge_positions),
                    "byteOffset": edge_position_offset,
                    "target": 34962,
                },
                {
                    "buffer": 0,
                    "byteLength": len(edge_index_bytes),
                    "byteOffset": edge_index_offset,
                    "target": 34963,
                },
            )
        )
        accessors.extend(
            (
                {
                    "bufferView": edge_position_view,
                    "componentType": 5126,
                    "count": len(edge_vertices),
                    "max": edge_maxes,
                    "min": edge_mins,
                    "type": "VEC3",
                },
                {
                    "bufferView": edge_index_view,
                    "componentType": 5125,
                    "count": len(edge_indices),
                    "max": [len(edge_vertices) - 1],
                    "min": [0],
                    "type": "SCALAR",
                },
            )
        )
        primitives.append(
            {
                "attributes": {"POSITION": edge_position_accessor},
                "indices": edge_index_accessor,
                "mode": 1,
                "extras": {"mesh2paramAnalyticEdges": True},
            }
        )

    document = {
        "accessors": accessors,
        "asset": {"generator": "Mesh2Param", "version": "2.0"},
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(binary)}],
        "meshes": [
            {
                "name": "Mesh2Param result",
                "primitives": primitives,
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
    linear_tolerance: float = DEFAULT_TESSELLATION_LINEAR_TOLERANCE_MM,
    angular_tolerance: float = DEFAULT_TESSELLATION_ANGULAR_TOLERANCE_RAD,
    cache: TessellationCache | None = None,
    edge_polylines: tuple[EdgePolyline, ...] = (),
) -> MeshArtifact:
    """Tessellate once and write a deterministic GLB artifact."""

    mesh = tessellate_shape(
        value,
        linear_tolerance=linear_tolerance,
        angular_tolerance=angular_tolerance,
        cache=cache,
    )
    return write_glb(
        mesh,
        path,
        linear_tolerance=linear_tolerance,
        angular_tolerance=angular_tolerance,
        edge_polylines=edge_polylines,
    )


__all__ = [
    "DisplayTessellation",
    "EdgePolyline",
    "MeshArtifact",
    "Tessellation",
    "TessellationCache",
    "canonicalize_tessellation",
    "display_tessellation",
    "export_binary_stl",
    "export_glb",
    "export_obj",
    "sample_shape_edges",
    "tessellate_shape",
    "transform_tessellation",
    "write_binary_stl",
    "write_glb",
    "write_obj",
]
