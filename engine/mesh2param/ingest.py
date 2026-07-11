"""Strict, non-mutating triangle-mesh ingestion and diagnostics.

The importer deliberately performs a cheap, format-specific preflight before
handing bytes to :mod:`trimesh`.  This keeps archive/executable polyglots,
non-triangle polygons, malformed indices, and over-limit inputs out of the
general-purpose parser while retaining trimesh's mature STL/OBJ/PLY support.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
import stat
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

import numpy as np
import trimesh
from numpy.typing import NDArray

MeshFormat = Literal["stl", "obj", "ply"]
SelfIntersectionStatus = Literal["unverified"]
Vertex = tuple[float, float, float]

_SUPPORTED_SUFFIXES: dict[str, MeshFormat] = {
    ".stl": "stl",
    ".obj": "obj",
    ".ply": "ply",
}
_FORBIDDEN_MAGICS: tuple[tuple[bytes, str], ...] = (
    (b"PK\x03\x04", "ZIP archive"),
    (b"PK\x05\x06", "ZIP archive"),
    (b"PK\x07\x08", "ZIP archive"),
    (b"\x1f\x8b", "gzip archive"),
    (b"7z\xbc\xaf\x27\x1c", "7-Zip archive"),
    (b"Rar!\x1a\x07", "RAR archive"),
    (b"\x7fELF", "ELF executable"),
    (b"MZ", "PE executable"),
    (b"\xfe\xed\xfa\xce", "Mach-O executable"),
    (b"\xce\xfa\xed\xfe", "Mach-O executable"),
    (b"\xfe\xed\xfa\xcf", "Mach-O executable"),
    (b"\xcf\xfa\xed\xfe", "Mach-O executable"),
)


class MeshIngestionError(ValueError):
    """A fail-closed ingestion error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class MeshLimits:
    """Resource and numeric limits applied before and after parsing."""

    max_file_bytes: int = 256 * 1024 * 1024
    max_triangles: int = 2_000_000
    max_vertices: int = 6_000_000
    max_abs_coordinate: float = 1_000_000_000.0
    max_path_characters: int = 4096
    diagnostic_weld_tolerance: float = 1e-9
    degenerate_area_tolerance: float = 1e-18
    tiny_extent_warning: float = 1e-6
    allow_symlinks: bool = False

    def __post_init__(self) -> None:
        integer_limits: dict[str, int] = {
            "max_file_bytes": self.max_file_bytes,
            "max_triangles": self.max_triangles,
            "max_vertices": self.max_vertices,
            "max_path_characters": self.max_path_characters,
        }
        for name, value in integer_limits.items():
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        numeric_limits: dict[str, float] = {
            "max_abs_coordinate": self.max_abs_coordinate,
            "diagnostic_weld_tolerance": self.diagnostic_weld_tolerance,
            "degenerate_area_tolerance": self.degenerate_area_tolerance,
            "tiny_extent_warning": self.tiny_extent_warning,
        }
        for numeric_name, numeric_value in numeric_limits.items():
            if not math.isfinite(numeric_value) or numeric_value < 0:
                raise ValueError(f"{numeric_name} must be finite and non-negative")
        if self.max_abs_coordinate == 0 or self.diagnostic_weld_tolerance == 0:
            raise ValueError("coordinate and weld limits must be positive")
        if not isinstance(self.allow_symlinks, bool):
            raise ValueError("allow_symlinks must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "maxFileBytes": self.max_file_bytes,
            "maxTriangles": self.max_triangles,
            "maxVertices": self.max_vertices,
            "maxAbsCoordinate": self.max_abs_coordinate,
            "maxPathCharacters": self.max_path_characters,
            "diagnosticWeldTolerance": self.diagnostic_weld_tolerance,
            "degenerateAreaTolerance": self.degenerate_area_tolerance,
            "tinyExtentWarning": self.tiny_extent_warning,
            "allowSymlinks": self.allow_symlinks,
        }


DEFAULT_MESH_LIMITS = MeshLimits()


@dataclass(frozen=True, slots=True)
class DiagnosticWarning:
    code: str
    message: str
    severity: Literal["warning"] = "warning"

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "severity": self.severity}


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    filename: str
    extension: str
    format: MeshFormat
    encoding: str
    byte_size: int
    sha256: str
    original_bytes_preserved: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "extension": self.extension,
            "format": self.format,
            "encoding": self.encoding,
            "byteSize": self.byte_size,
            "sha256": self.sha256,
            "originalBytesPreserved": self.original_bytes_preserved,
        }


@dataclass(frozen=True, slots=True)
class MeshDiagnostics:
    format: MeshFormat
    encoding: str
    byte_size: int
    sha256: str
    raw_vertex_count: int
    welded_vertex_count: int
    duplicate_vertex_count: int
    triangle_count: int
    connected_component_count: int
    bounds: tuple[Vertex, Vertex]
    bounding_dimensions: Vertex
    coordinate_range: tuple[float, float]
    surface_area: float
    closed_volume: float | None
    watertight: bool
    winding_consistent: bool
    degenerate_triangle_count: int
    duplicate_face_count: int
    non_manifold_edge_count: int
    open_boundary_edge_count: int
    open_boundary_count: int
    self_intersection_status: SelfIntersectionStatus
    warnings: tuple[DiagnosticWarning, ...] = field(default_factory=tuple)

    @property
    def vertex_count(self) -> int:
        """Compatibility shorthand for the source/raw vertex count."""

        return self.raw_vertex_count

    @property
    def component_count(self) -> int:
        return self.connected_component_count

    def to_dict(self) -> dict[str, object]:
        return {
            "format": self.format,
            "encoding": self.encoding,
            "byteSize": self.byte_size,
            "sha256": self.sha256,
            "rawVertexCount": self.raw_vertex_count,
            "weldedVertexCount": self.welded_vertex_count,
            "duplicateVertexCount": self.duplicate_vertex_count,
            "triangleCount": self.triangle_count,
            "connectedComponentCount": self.connected_component_count,
            "bounds": self.bounds,
            "boundingDimensions": self.bounding_dimensions,
            "coordinateRange": self.coordinate_range,
            "surfaceArea": self.surface_area,
            "closedVolume": self.closed_volume,
            "watertight": self.watertight,
            "windingConsistent": self.winding_consistent,
            "degenerateTriangleCount": self.degenerate_triangle_count,
            "duplicateFaceCount": self.duplicate_face_count,
            "nonManifoldEdgeCount": self.non_manifold_edge_count,
            "openBoundaryEdgeCount": self.open_boundary_edge_count,
            "openBoundaryCount": self.open_boundary_count,
            "selfIntersectionStatus": self.self_intersection_status,
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class IngestedMesh:
    """An imported mesh coupled to its exact, unchanged source upload."""

    source_id: str
    metadata: SourceMetadata
    diagnostics: MeshDiagnostics
    mesh: trimesh.Trimesh
    original_bytes: bytes = field(repr=False)

    def mesh_copy(self) -> trimesh.Trimesh:
        """Return a writable working copy; callers never need to mutate source."""

        return self.mesh.copy()

    def to_dict(self) -> dict[str, object]:
        return {
            "sourceId": self.source_id,
            "metadata": self.metadata.to_dict(),
            "diagnostics": self.diagnostics.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class _Preflight:
    encoding: str
    vertex_count: int
    triangle_count: int


@dataclass(frozen=True, slots=True)
class _PlyProperty:
    name: str
    scalar_type: str | None
    list_count_type: str | None = None
    list_value_type: str | None = None

    @property
    def is_list(self) -> bool:
        return self.list_count_type is not None


@dataclass(frozen=True, slots=True)
class _PlyElement:
    name: str
    count: int
    properties: tuple[_PlyProperty, ...]


_PLY_SCALARS: dict[str, tuple[str, int, bool]] = {
    "char": ("b", 1, True),
    "int8": ("b", 1, True),
    "uchar": ("B", 1, True),
    "uint8": ("B", 1, True),
    "short": ("h", 2, True),
    "int16": ("h", 2, True),
    "ushort": ("H", 2, True),
    "uint16": ("H", 2, True),
    "int": ("i", 4, True),
    "int32": ("i", 4, True),
    "uint": ("I", 4, True),
    "uint32": ("I", 4, True),
    "float": ("f", 4, False),
    "float32": ("f", 4, False),
    "double": ("d", 8, False),
    "float64": ("d", 8, False),
}


def _vertices(mesh: trimesh.Trimesh) -> NDArray[np.float64]:
    return np.asarray(mesh.vertices, dtype=np.float64)


def _faces(mesh: trimesh.Trimesh) -> NDArray[np.int64]:
    return np.asarray(mesh.faces, dtype=np.int64)


def _extension(filename: str) -> MeshFormat:
    suffix = Path(filename).suffix.lower()
    mesh_format = _SUPPORTED_SUFFIXES.get(suffix)
    if mesh_format is None:
        raise MeshIngestionError(
            "unsupported_extension",
            f"unsupported mesh extension {suffix or '<none>'!r}; expected STL, OBJ, or PLY",
        )
    return mesh_format


def _validate_upload_filename(filename: str, limits: MeshLimits) -> None:
    if not filename or "\x00" in filename:
        raise MeshIngestionError("invalid_path", "upload filename is empty or contains NUL")
    if len(filename) > limits.max_path_characters:
        raise MeshIngestionError("invalid_path", "upload filename exceeds configured path limit")
    if filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise MeshIngestionError("invalid_path", "upload filename must not contain a path")


def _reject_forbidden_content(payload: bytes) -> None:
    for magic, label in _FORBIDDEN_MAGICS:
        if payload.startswith(magic):
            raise MeshIngestionError(
                "forbidden_content", f"refusing {label} content disguised as a mesh"
            )


def _looks_like_binary_stl(payload: bytes) -> bool:
    if len(payload) < 84:
        return False
    triangle_count = int(struct.unpack_from("<I", payload, 80)[0])
    return 84 + triangle_count * 50 == len(payload)


def _sniff_format(payload: bytes) -> MeshFormat | None:
    if payload.startswith((b"ply\n", b"ply\r\n")):
        return "ply"
    if _looks_like_binary_stl(payload):
        return "stl"
    prefix = payload[: min(len(payload), 1_048_576)]
    try:
        text = prefix.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    stripped = text.lstrip().lower()
    if stripped.startswith("solid") and "facet" in stripped and "vertex" in stripped:
        return "stl"
    has_vertex = bool(re.search(r"(?m)^\s*v\s+[-+.0-9]", text))
    has_face = bool(re.search(r"(?m)^\s*f\s+[^\s]+\s+[^\s]+\s+[^\s]+", text))
    if has_vertex and has_face:
        return "obj"
    return None


def _require_count(name: str, count: int, limit: int) -> None:
    if count <= 0:
        raise MeshIngestionError("empty_geometry", f"mesh contains no {name}")
    if count > limit:
        raise MeshIngestionError(
            f"excessive_{name}", f"mesh has {count:,} {name}; configured maximum is {limit:,}"
        )


def _finite_floats(values: list[str], context: str) -> None:
    try:
        parsed = [float(value) for value in values]
    except ValueError as exc:
        raise MeshIngestionError("malformed_geometry", f"invalid number in {context}") from exc
    if not all(math.isfinite(value) for value in parsed):
        raise MeshIngestionError("non_finite_coordinate", f"non-finite number in {context}")


def _preflight_stl(payload: bytes, limits: MeshLimits) -> _Preflight:
    if _looks_like_binary_stl(payload):
        count = struct.unpack_from("<I", payload, 80)[0]
        _require_count("triangles", count, limits.max_triangles)
        _require_count("vertices", count * 3, limits.max_vertices)
        return _Preflight("binary-little-endian", count * 3, count)

    if len(payload) >= 84 and not payload.lstrip().startswith(b"solid"):
        declared = struct.unpack_from("<I", payload, 80)[0]
        expected = 84 + declared * 50
        raise MeshIngestionError(
            "malformed_geometry",
            f"binary STL length mismatch: header declares {declared} triangles "
            f"({expected} bytes), file has {len(payload)} bytes",
        )
    if b"\x00" in payload:
        raise MeshIngestionError("malformed_geometry", "ASCII STL contains NUL bytes")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MeshIngestionError(
            "malformed_geometry", "STL is neither valid binary nor UTF-8"
        ) from exc
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or not lines[0].lower().startswith("solid"):
        raise MeshIngestionError("content_mismatch", "STL content does not begin with solid")
    if not lines[-1].lower().startswith("endsolid"):
        raise MeshIngestionError("malformed_geometry", "ASCII STL is missing endsolid")

    facets = 0
    vertices = 0
    end_facets = 0
    outer_loops = 0
    end_loops = 0
    for line_number, line in enumerate(lines, start=1):
        parts = line.split()
        tokens = [part.lower() for part in parts]
        if tokens[:2] == ["facet", "normal"]:
            if len(parts) != 5:
                raise MeshIngestionError("malformed_geometry", "STL facet normal needs 3 values")
            _finite_floats(parts[2:], f"STL line {line_number}")
            facets += 1
        elif tokens == ["outer", "loop"]:
            outer_loops += 1
        elif tokens[:1] == ["vertex"]:
            if len(parts) != 4:
                raise MeshIngestionError("non_triangle_face", "STL vertex must contain 3 values")
            _finite_floats(parts[1:], f"STL line {line_number}")
            vertices += 1
        elif tokens == ["endloop"]:
            end_loops += 1
        elif tokens == ["endfacet"]:
            end_facets += 1
        elif tokens[:1] not in (["solid"], ["endsolid"]):
            raise MeshIngestionError(
                "malformed_geometry", f"unexpected ASCII STL statement on line {line_number}"
            )
    if not (facets == end_facets == outer_loops == end_loops and vertices == facets * 3):
        raise MeshIngestionError("malformed_geometry", "ASCII STL facet structure is inconsistent")
    _require_count("triangles", facets, limits.max_triangles)
    _require_count("vertices", vertices, limits.max_vertices)
    return _Preflight("ascii-utf8", vertices, facets)


def _resolve_obj_index(token: str, count: int, context: str) -> None:
    try:
        index = int(token)
    except ValueError as exc:
        raise MeshIngestionError("malformed_indices", f"invalid {context} index {token!r}") from exc
    if index == 0:
        raise MeshIngestionError("malformed_indices", f"OBJ {context} index must not be zero")
    resolved = index - 1 if index > 0 else count + index
    if resolved < 0 or resolved >= count:
        raise MeshIngestionError(
            "malformed_indices", f"OBJ {context} index {index} is out of range"
        )


def _preflight_obj(payload: bytes, limits: MeshLimits) -> _Preflight:
    if b"\x00" in payload:
        raise MeshIngestionError("malformed_geometry", "OBJ contains NUL bytes")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MeshIngestionError("malformed_geometry", "OBJ must be UTF-8 text") from exc

    vertex_count = 0
    texture_count = 0
    normal_count = 0
    triangle_count = 0
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        command = parts[0]
        values = parts[1:]
        if command == "v":
            if len(values) < 3:
                raise MeshIngestionError(
                    "malformed_geometry", f"OBJ vertex on line {line_number} needs 3 values"
                )
            _finite_floats(values[:3], f"OBJ line {line_number}")
            vertex_count += 1
            if vertex_count > limits.max_vertices:
                _require_count("vertices", vertex_count, limits.max_vertices)
        elif command == "vt":
            if not values:
                raise MeshIngestionError("malformed_geometry", "OBJ texture coordinate is empty")
            _finite_floats(values, f"OBJ line {line_number}")
            texture_count += 1
        elif command == "vn":
            if len(values) != 3:
                raise MeshIngestionError("malformed_geometry", "OBJ normal needs 3 values")
            _finite_floats(values, f"OBJ line {line_number}")
            normal_count += 1
        elif command == "f":
            if len(values) != 3:
                raise MeshIngestionError(
                    "non_triangle_face",
                    f"OBJ face on line {line_number} has {len(values)} vertices; "
                    "exactly 3 required",
                )
            for reference in values:
                fields = reference.split("/")
                if len(fields) > 3 or not fields[0]:
                    raise MeshIngestionError("malformed_indices", "malformed OBJ face reference")
                _resolve_obj_index(fields[0], vertex_count, "vertex")
                if len(fields) >= 2 and fields[1]:
                    _resolve_obj_index(fields[1], texture_count, "texture")
                if len(fields) == 3 and fields[2]:
                    _resolve_obj_index(fields[2], normal_count, "normal")
            triangle_count += 1
            if triangle_count > limits.max_triangles:
                _require_count("triangles", triangle_count, limits.max_triangles)
    _require_count("vertices", vertex_count, limits.max_vertices)
    _require_count("triangles", triangle_count, limits.max_triangles)
    return _Preflight("ascii-utf8", vertex_count, triangle_count)


def _ply_header(payload: bytes) -> tuple[str, tuple[_PlyElement, ...], int]:
    match = re.search(rb"(?m)^end_header(?:\r\n|\n|\r)", payload[:1_048_576])
    if match is None:
        raise MeshIngestionError("malformed_geometry", "PLY header is missing end_header")
    try:
        header = payload[: match.end()].decode("ascii")
    except UnicodeDecodeError as exc:
        raise MeshIngestionError("malformed_geometry", "PLY header must be ASCII") from exc
    lines = [line.strip() for line in header.splitlines() if line.strip()]
    if not lines or lines[0] != "ply":
        raise MeshIngestionError("content_mismatch", "PLY content is missing the ply signature")
    if len(lines) < 2 or not lines[1].startswith("format "):
        raise MeshIngestionError("malformed_geometry", "PLY header is missing format")
    format_parts = lines[1].split()
    if len(format_parts) != 3 or format_parts[2] != "1.0":
        raise MeshIngestionError("malformed_geometry", "only PLY format version 1.0 is supported")
    encoding = format_parts[1]
    if encoding not in {"ascii", "binary_little_endian", "binary_big_endian"}:
        raise MeshIngestionError("malformed_geometry", f"unsupported PLY encoding {encoding!r}")

    elements: list[_PlyElement] = []
    current_name: str | None = None
    current_count = 0
    current_properties: list[_PlyProperty] = []

    def finish_element() -> None:
        nonlocal current_name, current_count, current_properties
        if current_name is not None:
            elements.append(_PlyElement(current_name, current_count, tuple(current_properties)))
        current_name = None
        current_count = 0
        current_properties = []

    for line in lines[2:]:
        parts = line.split()
        if parts[0] in {"comment", "obj_info"} or parts[0] == "end_header":
            continue
        if parts[0] == "format":
            raise MeshIngestionError("malformed_geometry", "PLY declares format more than once")
        if parts[0] == "element":
            if len(parts) != 3:
                raise MeshIngestionError("malformed_geometry", "malformed PLY element declaration")
            finish_element()
            current_name = parts[1]
            try:
                current_count = int(parts[2])
            except ValueError as exc:
                raise MeshIngestionError("malformed_geometry", "invalid PLY element count") from exc
            if current_count < 0:
                raise MeshIngestionError("malformed_geometry", "negative PLY element count")
        elif parts[0] == "property":
            if current_name is None:
                raise MeshIngestionError("malformed_geometry", "PLY property has no element")
            if len(parts) == 3:
                scalar_type = parts[1].lower()
                if scalar_type not in _PLY_SCALARS:
                    raise MeshIngestionError("malformed_geometry", "unknown PLY scalar type")
                current_properties.append(_PlyProperty(parts[2], scalar_type))
            elif len(parts) == 5 and parts[1] == "list":
                count_type = parts[2].lower()
                value_type = parts[3].lower()
                if count_type not in _PLY_SCALARS or value_type not in _PLY_SCALARS:
                    raise MeshIngestionError("malformed_geometry", "unknown PLY list type")
                if not _PLY_SCALARS[count_type][2]:
                    raise MeshIngestionError(
                        "malformed_geometry", "PLY list count must be integral"
                    )
                current_properties.append(_PlyProperty(parts[4], None, count_type, value_type))
            else:
                raise MeshIngestionError("malformed_geometry", "malformed PLY property declaration")
        else:
            raise MeshIngestionError("malformed_geometry", f"unexpected PLY header line {line!r}")
    finish_element()
    return encoding, tuple(elements), match.end()


def _ply_geometry_elements(
    elements: tuple[_PlyElement, ...], limits: MeshLimits
) -> tuple[_PlyElement, _PlyElement, _PlyProperty]:
    vertices = [element for element in elements if element.name == "vertex"]
    faces = [element for element in elements if element.name == "face"]
    if len(vertices) != 1 or len(faces) != 1:
        raise MeshIngestionError("malformed_geometry", "PLY needs one vertex and one face element")
    vertex, face = vertices[0], faces[0]
    _require_count("vertices", vertex.count, limits.max_vertices)
    _require_count("triangles", face.count, limits.max_triangles)
    coordinates = {prop.name for prop in vertex.properties if not prop.is_list}
    if not {"x", "y", "z"} <= coordinates:
        raise MeshIngestionError(
            "malformed_geometry", "PLY vertices need scalar x, y, z properties"
        )
    index_properties = [
        prop
        for prop in face.properties
        if prop.name in {"vertex_indices", "vertex_index"} and prop.is_list
    ]
    if len(index_properties) != 1:
        raise MeshIngestionError("malformed_indices", "PLY faces need one vertex_indices list")
    index_property = index_properties[0]
    assert index_property.list_value_type is not None
    if not _PLY_SCALARS[index_property.list_value_type][2]:
        raise MeshIngestionError("malformed_indices", "PLY face indices must be integral")
    return vertex, face, index_property


def _parse_ascii_ply_value(token: str, scalar_type: str) -> int | float:
    try:
        if _PLY_SCALARS[scalar_type][2]:
            return int(token)
        value = float(token)
    except ValueError as exc:
        raise MeshIngestionError("malformed_geometry", "invalid ASCII PLY value") from exc
    if not math.isfinite(value):
        raise MeshIngestionError("non_finite_coordinate", "non-finite ASCII PLY value")
    return value


def _validate_ply_ascii_body(
    payload: bytes,
    offset: int,
    elements: tuple[_PlyElement, ...],
    vertex_count: int,
    face_indices: _PlyProperty,
) -> None:
    try:
        tokens = payload[offset:].decode("ascii").split()
    except UnicodeDecodeError as exc:
        raise MeshIngestionError("malformed_geometry", "ASCII PLY body must be ASCII") from exc
    position = 0
    for element in elements:
        for _ in range(element.count):
            for prop in element.properties:
                if prop.is_list:
                    assert prop.list_count_type is not None
                    assert prop.list_value_type is not None
                    if position >= len(tokens):
                        raise MeshIngestionError("malformed_geometry", "truncated ASCII PLY body")
                    count_value = _parse_ascii_ply_value(tokens[position], prop.list_count_type)
                    position += 1
                    count = int(count_value)
                    if count < 0 or count > vertex_count:
                        raise MeshIngestionError("malformed_geometry", "invalid PLY list length")
                    if position + count > len(tokens):
                        raise MeshIngestionError("malformed_geometry", "truncated ASCII PLY list")
                    values = [
                        _parse_ascii_ply_value(token, prop.list_value_type)
                        for token in tokens[position : position + count]
                    ]
                    position += count
                    if element.name == "face" and prop == face_indices:
                        if count != 3:
                            raise MeshIngestionError(
                                "non_triangle_face",
                                f"PLY face has {count} vertices; exactly 3 required",
                            )
                        if any(int(value) < 0 or int(value) >= vertex_count for value in values):
                            raise MeshIngestionError(
                                "malformed_indices", "PLY face index is out of range"
                            )
                else:
                    assert prop.scalar_type is not None
                    if position >= len(tokens):
                        raise MeshIngestionError("malformed_geometry", "truncated ASCII PLY body")
                    _parse_ascii_ply_value(tokens[position], prop.scalar_type)
                    position += 1
    if position != len(tokens):
        raise MeshIngestionError("malformed_geometry", "ASCII PLY has unexpected trailing data")


def _unpack_ply_scalar(
    payload: bytes, offset: int, scalar_type: str, endian: str
) -> tuple[int | float, int]:
    code, size, _ = _PLY_SCALARS[scalar_type]
    if offset + size > len(payload):
        raise MeshIngestionError("malformed_geometry", "truncated binary PLY body")
    value = struct.unpack_from(endian + code, payload, offset)[0]
    if isinstance(value, float) and not math.isfinite(value):
        raise MeshIngestionError("non_finite_coordinate", "non-finite binary PLY value")
    return cast(int | float, value), offset + size


def _validate_ply_binary_body(
    payload: bytes,
    offset: int,
    elements: tuple[_PlyElement, ...],
    vertex_count: int,
    face_indices: _PlyProperty,
    endian: str,
) -> None:
    position = offset
    for element in elements:
        for _ in range(element.count):
            for prop in element.properties:
                if prop.is_list:
                    assert prop.list_count_type is not None
                    assert prop.list_value_type is not None
                    raw_count, position = _unpack_ply_scalar(
                        payload, position, prop.list_count_type, endian
                    )
                    count = int(raw_count)
                    if count < 0 or count > vertex_count:
                        raise MeshIngestionError(
                            "malformed_geometry", "invalid binary PLY list length"
                        )
                    values: list[int | float] = []
                    for _ in range(count):
                        value, position = _unpack_ply_scalar(
                            payload, position, prop.list_value_type, endian
                        )
                        values.append(value)
                    if element.name == "face" and prop == face_indices:
                        if count != 3:
                            raise MeshIngestionError(
                                "non_triangle_face",
                                f"PLY face has {count} vertices; exactly 3 required",
                            )
                        if any(int(value) < 0 or int(value) >= vertex_count for value in values):
                            raise MeshIngestionError(
                                "malformed_indices", "PLY face index is out of range"
                            )
                else:
                    assert prop.scalar_type is not None
                    _, position = _unpack_ply_scalar(payload, position, prop.scalar_type, endian)
    if position != len(payload):
        raise MeshIngestionError("malformed_geometry", "binary PLY has unexpected trailing bytes")


def _preflight_ply(payload: bytes, limits: MeshLimits) -> _Preflight:
    encoding, elements, offset = _ply_header(payload)
    vertex, face, face_indices = _ply_geometry_elements(elements, limits)
    if encoding == "ascii":
        _validate_ply_ascii_body(payload, offset, elements, vertex.count, face_indices)
        public_encoding = "ascii"
    else:
        endian = "<" if encoding == "binary_little_endian" else ">"
        _validate_ply_binary_body(payload, offset, elements, vertex.count, face_indices, endian)
        public_encoding = encoding.replace("_", "-")
    return _Preflight(public_encoding, vertex.count, face.count)


def _preflight(payload: bytes, mesh_format: MeshFormat, limits: MeshLimits) -> _Preflight:
    if mesh_format == "stl":
        return _preflight_stl(payload, limits)
    if mesh_format == "obj":
        return _preflight_obj(payload, limits)
    return _preflight_ply(payload, limits)


def _face_components(faces: NDArray[np.int64]) -> int:
    if len(faces) == 0:
        return 0
    parent = np.arange(len(faces), dtype=np.int64)

    def find(index: int) -> int:
        while int(parent[index]) != index:
            parent[index] = parent[int(parent[index])]
            index = int(parent[index])
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    edge_owner: dict[tuple[int, int], int] = {}
    for face_index, face in enumerate(faces):
        for start, end in ((0, 1), (1, 2), (2, 0)):
            left, right = sorted((int(face[start]), int(face[end])))
            edge = (left, right)
            previous = edge_owner.setdefault(edge, face_index)
            union(previous, face_index)
    return len({find(index) for index in range(len(faces))})


def _open_boundary_components(open_edges: NDArray[np.int64]) -> int:
    if len(open_edges) == 0:
        return 0
    adjacency: dict[int, set[int]] = {}
    for left, right in open_edges:
        left_int, right_int = int(left), int(right)
        adjacency.setdefault(left_int, set()).add(right_int)
        adjacency.setdefault(right_int, set()).add(left_int)
    unseen = set(adjacency)
    components = 0
    while unseen:
        components += 1
        stack = [min(unseen)]
        unseen.remove(stack[0])
        while stack:
            current = stack.pop()
            for neighbor in sorted(adjacency[current]):
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    stack.append(neighbor)
    return components


def diagnose_mesh(
    mesh: trimesh.Trimesh,
    *,
    mesh_format: MeshFormat,
    encoding: str,
    byte_size: int,
    sha256: str,
    limits: MeshLimits = DEFAULT_MESH_LIMITS,
) -> MeshDiagnostics:
    """Compute deterministic topology diagnostics without modifying ``mesh``."""

    vertices = _vertices(mesh)
    faces = _faces(mesh)
    decimals = max(0, min(15, math.ceil(-math.log10(limits.diagnostic_weld_tolerance))))
    rounded = np.round(vertices, decimals=decimals)
    welded_vertices, inverse = np.unique(rounded, axis=0, return_inverse=True)
    welded_faces = inverse[faces].astype(np.int64, copy=False)

    repeated_indices = np.any(
        np.column_stack(
            (
                welded_faces[:, 0] == welded_faces[:, 1],
                welded_faces[:, 1] == welded_faces[:, 2],
                welded_faces[:, 2] == welded_faces[:, 0],
            )
        ),
        axis=1,
    )
    a = vertices[faces[:, 0]]
    b = vertices[faces[:, 1]]
    c = vertices[faces[:, 2]]
    doubled_areas = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    degenerate = repeated_indices | (doubled_areas <= limits.degenerate_area_tolerance * 2.0)

    canonical_faces = np.sort(welded_faces, axis=1)
    _, face_counts = np.unique(canonical_faces, axis=0, return_counts=True)
    duplicate_faces = int(np.sum(np.maximum(face_counts - 1, 0)))

    edges = np.vstack(
        (
            welded_faces[:, [0, 1]],
            welded_faces[:, [1, 2]],
            welded_faces[:, [2, 0]],
        )
    )
    edges = np.sort(edges, axis=1)
    edges = edges[edges[:, 0] != edges[:, 1]]
    unique_edges, edge_counts = np.unique(edges, axis=0, return_counts=True)
    open_edges = unique_edges[edge_counts == 1]
    non_manifold = int(np.count_nonzero(edge_counts > 2))
    watertight = bool(len(unique_edges) > 0 and np.all(edge_counts == 2))

    diagnostic_mesh = trimesh.Trimesh(
        vertices=welded_vertices,
        faces=welded_faces,
        process=False,
        validate=False,
    )
    try:
        winding_consistent = bool(diagnostic_mesh.is_winding_consistent)
    except (IndexError, ValueError):
        winding_consistent = False

    lower = np.min(vertices, axis=0)
    upper = np.max(vertices, axis=0)
    dimensions = upper - lower
    closed_volume = abs(float(diagnostic_mesh.volume)) if watertight else None
    warnings: list[DiagnosticWarning] = [
        DiagnosticWarning(
            "self_intersection_unverified",
            "Self-intersection was not verified because no robust detector is available.",
        )
    ]
    component_count = _face_components(welded_faces)
    if component_count > 1:
        warnings.append(
            DiagnosticWarning(
                "multiple_components",
                f"Mesh contains {component_count} disconnected triangle components.",
            )
        )
    positive_dimensions = dimensions[dimensions > 0]
    if len(positive_dimensions) and float(np.min(positive_dimensions)) < limits.tiny_extent_warning:
        warnings.append(
            DiagnosticWarning(
                "tiny_feature_scale",
                "At least one non-zero bounding extent is below the configured tiny-scale warning.",
            )
        )
    return MeshDiagnostics(
        format=mesh_format,
        encoding=encoding,
        byte_size=byte_size,
        sha256=sha256,
        raw_vertex_count=len(vertices),
        welded_vertex_count=len(welded_vertices),
        duplicate_vertex_count=len(vertices) - len(welded_vertices),
        triangle_count=len(faces),
        connected_component_count=component_count,
        bounds=(
            (float(lower[0]), float(lower[1]), float(lower[2])),
            (float(upper[0]), float(upper[1]), float(upper[2])),
        ),
        bounding_dimensions=(
            float(dimensions[0]),
            float(dimensions[1]),
            float(dimensions[2]),
        ),
        coordinate_range=(float(np.min(vertices)), float(np.max(vertices))),
        surface_area=float(np.sum(doubled_areas) * 0.5),
        closed_volume=closed_volume,
        watertight=watertight,
        winding_consistent=winding_consistent,
        degenerate_triangle_count=int(np.count_nonzero(degenerate)),
        duplicate_face_count=duplicate_faces,
        non_manifold_edge_count=non_manifold,
        open_boundary_edge_count=len(open_edges),
        open_boundary_count=_open_boundary_components(open_edges),
        self_intersection_status="unverified",
        warnings=tuple(warnings),
    )


def _parse_mesh(
    payload: bytes,
    mesh_format: MeshFormat,
    preflight: _Preflight,
    limits: MeshLimits,
) -> trimesh.Trimesh:
    try:
        loaded = trimesh.load_mesh(
            file_obj=io.BytesIO(payload),
            file_type=mesh_format,
            process=False,
            maintain_order=True,
        )
    except Exception as exc:
        raise MeshIngestionError(
            "malformed_geometry", f"trimesh could not parse {mesh_format.upper()} content: {exc}"
        ) from exc
    if not isinstance(loaded, trimesh.Trimesh):
        raise MeshIngestionError("non_triangle_mesh", "parser did not return one triangle mesh")
    vertices = _vertices(loaded)
    faces = _faces(loaded)
    if vertices.ndim != 2 or vertices.shape[1:] != (3,):
        raise MeshIngestionError("malformed_geometry", "mesh vertices must have shape (n, 3)")
    if faces.ndim != 2 or faces.shape[1:] != (3,):
        raise MeshIngestionError(
            "non_triangle_face", "mesh faces must all contain exactly 3 indices"
        )
    _require_count("vertices", len(vertices), limits.max_vertices)
    _require_count("triangles", len(faces), limits.max_triangles)
    if len(faces) != preflight.triangle_count:
        raise MeshIngestionError(
            "malformed_geometry",
            "parser triangle count differs from the format preflight count",
        )
    if mesh_format != "obj" and len(vertices) != preflight.vertex_count:
        raise MeshIngestionError(
            "malformed_geometry", "parser vertex count differs from the format preflight count"
        )
    if np.any(faces < 0) or np.any(faces >= len(vertices)):
        raise MeshIngestionError("malformed_indices", "mesh contains an out-of-range face index")
    if not np.all(np.isfinite(vertices)):
        raise MeshIngestionError("non_finite_coordinate", "mesh contains non-finite coordinates")
    maximum = float(np.max(np.abs(vertices)))
    if maximum > limits.max_abs_coordinate:
        raise MeshIngestionError(
            "extreme_coordinates",
            f"coordinate magnitude {maximum:g} exceeds configured limit "
            f"{limits.max_abs_coordinate:g}",
        )
    return loaded


def ingest_bytes(
    payload: bytes,
    filename: str,
    *,
    limits: MeshLimits = DEFAULT_MESH_LIMITS,
) -> IngestedMesh:
    """Validate and ingest uploaded bytes while preserving them exactly."""

    _validate_upload_filename(filename, limits)
    mesh_format = _extension(filename)
    if not isinstance(payload, bytes):
        raise MeshIngestionError("invalid_bytes", "mesh payload must be immutable bytes")
    if not payload:
        raise MeshIngestionError("empty_file", "mesh file is empty")
    if len(payload) > limits.max_file_bytes:
        raise MeshIngestionError(
            "excessive_bytes",
            f"mesh is {len(payload):,} bytes; configured maximum is {limits.max_file_bytes:,}",
        )
    _reject_forbidden_content(payload)
    sniffed = _sniff_format(payload)
    if sniffed != mesh_format:
        detected = sniffed.upper() if sniffed is not None else "unknown"
        raise MeshIngestionError(
            "content_mismatch",
            f"{Path(filename).suffix.upper()} extension does not match {detected} content",
        )
    preflight = _preflight(payload, mesh_format, limits)
    mesh = _parse_mesh(payload, mesh_format, preflight, limits)
    digest = hashlib.sha256(payload).hexdigest()
    metadata = SourceMetadata(
        filename=filename,
        extension=Path(filename).suffix.lower(),
        format=mesh_format,
        encoding=preflight.encoding,
        byte_size=len(payload),
        sha256=digest,
    )
    diagnostics = diagnose_mesh(
        mesh,
        mesh_format=mesh_format,
        encoding=preflight.encoding,
        byte_size=len(payload),
        sha256=digest,
        limits=limits,
    )
    return IngestedMesh(
        source_id=f"source:{digest}",
        metadata=metadata,
        diagnostics=diagnostics,
        mesh=mesh,
        original_bytes=payload,
    )


def ingest_mesh(
    path: str | Path,
    *,
    limits: MeshLimits = DEFAULT_MESH_LIMITS,
) -> IngestedMesh:
    """Read a regular local mesh file safely and pass it through ``ingest_bytes``."""

    source = Path(path)
    raw_path = str(source)
    if not raw_path or "\x00" in raw_path or len(raw_path) > limits.max_path_characters:
        raise MeshIngestionError("invalid_path", "mesh path is empty, contains NUL, or is too long")
    try:
        if source.is_symlink() and not limits.allow_symlinks:
            raise MeshIngestionError("invalid_path", "symbolic-link mesh paths are disabled")
        file_stat = source.stat()
    except MeshIngestionError:
        raise
    except OSError as exc:
        raise MeshIngestionError("invalid_path", f"cannot stat mesh path: {exc}") from exc
    if not stat.S_ISREG(file_stat.st_mode):
        raise MeshIngestionError("invalid_path", "mesh path must name a regular file")
    if file_stat.st_size == 0:
        raise MeshIngestionError("empty_file", "mesh file is empty")
    if file_stat.st_size > limits.max_file_bytes:
        raise MeshIngestionError(
            "excessive_bytes",
            f"mesh is {file_stat.st_size:,} bytes; configured maximum is {limits.max_file_bytes:,}",
        )
    try:
        with source.open("rb") as stream:
            payload = stream.read(limits.max_file_bytes + 1)
    except OSError as exc:
        raise MeshIngestionError("invalid_path", f"cannot read mesh path: {exc}") from exc
    if len(payload) > limits.max_file_bytes:
        raise MeshIngestionError("excessive_bytes", "mesh grew beyond the configured byte limit")
    return ingest_bytes(payload, source.name, limits=limits)


def load_mesh(
    path: str | Path,
    *,
    limits: MeshLimits = DEFAULT_MESH_LIMITS,
) -> IngestedMesh:
    """Compatibility alias for :func:`ingest_mesh`."""

    return ingest_mesh(path, limits=limits)


__all__ = [
    "DEFAULT_MESH_LIMITS",
    "DiagnosticWarning",
    "IngestedMesh",
    "MeshDiagnostics",
    "MeshFormat",
    "MeshIngestionError",
    "MeshLimits",
    "SourceMetadata",
    "diagnose_mesh",
    "ingest_bytes",
    "ingest_mesh",
    "load_mesh",
]
