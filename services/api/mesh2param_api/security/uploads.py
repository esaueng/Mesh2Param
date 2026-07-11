from __future__ import annotations

import hashlib
import math
import os
import re
import stat
import struct
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Literal, NoReturn, cast

from mesh2param_api.storage import UnsafeNameError, validate_display_filename

MeshFormat = Literal["stl", "obj", "ply"]
MeshEncoding = Literal["ascii", "binary", "binary_little_endian", "binary_big_endian"]


class UploadValidationError(ValueError):
    """Stable, route-friendly rejection for an untrusted upload."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class UploadLimits:
    max_bytes: int = 256 * 1024 * 1024
    max_triangles: int = 2_000_000
    max_vertices: int = 6_000_000
    max_coordinate_magnitude: float = 1_000_000_000.0
    max_header_bytes: int = 1024 * 1024
    max_line_bytes: int = 1024 * 1024
    max_face_vertices: int = 100_000
    max_properties_per_element: int = 128

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_bytes,
            self.max_triangles,
            self.max_vertices,
            self.max_header_bytes,
            self.max_line_bytes,
            self.max_face_vertices,
            self.max_properties_per_element,
        )
        if any(isinstance(value, bool) or value <= 0 for value in integer_limits):
            raise ValueError("upload integer limits must be positive")
        if not math.isfinite(self.max_coordinate_magnitude) or self.max_coordinate_magnitude <= 0:
            raise ValueError("max_coordinate_magnitude must be finite and positive")


@dataclass(frozen=True, slots=True)
class MeshPreflight:
    format: MeshFormat
    encoding: MeshEncoding
    byte_size: int
    sha256: str
    display_filename: str
    vertex_count: int
    face_count: int
    triangle_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "format": self.format,
            "encoding": self.encoding,
            "byteSize": self.byte_size,
            "sha256": self.sha256,
            "displayFilename": self.display_filename,
            "vertexCount": self.vertex_count,
            "faceCount": self.face_count,
            "triangleCount": self.triangle_count,
        }


_EXTENSIONS: dict[str, MeshFormat] = {".stl": "stl", ".obj": "obj", ".ply": "ply"}
_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
_OBJ_EXTERNAL_DIRECTIVES = {
    "call",
    "csh",
    "include",
    "mtllib",
    "shadow_obj",
    "trace_obj",
}
_OBJ_METADATA_DIRECTIVES = {"g", "o", "s", "usemtl"}
_PLY_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,127}\Z")


def _reject(code: str, detail: str) -> NoReturn:
    raise UploadValidationError(code, detail)


@contextmanager
def _open_regular_file(path: Path) -> Iterator[tuple[BinaryIO, os.stat_result]]:
    try:
        path_status = path.lstat()
    except FileNotFoundError:
        _reject("upload_missing", "upload staging file does not exist")
    if stat.S_ISLNK(path_status.st_mode):
        _reject("symlink_not_allowed", "upload staging path cannot be a symlink")
    if not stat.S_ISREG(path_status.st_mode):
        _reject("non_regular_file", "upload staging path must be a regular file")
    try:
        descriptor = os.open(path, _OPEN_FLAGS)
    except OSError as error:
        raise UploadValidationError(
            "unsafe_upload_path", "upload staging path cannot be opened without following links"
        ) from error
    try:
        opened_status = os.fstat(descriptor)
        if not stat.S_ISREG(opened_status.st_mode):
            _reject("non_regular_file", "opened upload must be a regular file")
        if (path_status.st_dev, path_status.st_ino) != (
            opened_status.st_dev,
            opened_status.st_ino,
        ):
            _reject("upload_changed", "upload changed while it was being opened")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            yield stream, opened_status
    finally:
        os.close(descriptor)


def _read_prefix(stream: BinaryIO, size: int = 512) -> bytes:
    stream.seek(0)
    prefix = stream.read(size)
    if not isinstance(prefix, bytes):
        raise TypeError("binary stream read() must return bytes")
    stream.seek(0)
    return prefix


def _sha256(stream: BinaryIO, *, max_bytes: int) -> str:
    stream.seek(0)
    digest = hashlib.sha256()
    observed = 0
    while True:
        chunk = stream.read(min(1024 * 1024, max_bytes - observed + 1))
        if not chunk:
            break
        observed += len(chunk)
        if observed > max_bytes:
            _reject("file_size_limit", "mesh upload exceeds the configured byte limit")
        digest.update(chunk)
    stream.seek(0)
    return digest.hexdigest()


def _reject_forbidden_magic(prefix: bytes) -> None:
    archive_signatures = {
        b"PK\x03\x04": "ZIP",
        b"PK\x05\x06": "ZIP",
        b"PK\x07\x08": "ZIP",
        b"\x1f\x8b": "gzip",
        b"7z\xbc\xaf\x27\x1c": "7-Zip",
        b"Rar!\x1a\x07": "RAR",
        b"BZh": "bzip2",
        b"\xfd7zXZ\x00": "XZ",
    }
    for signature, label in archive_signatures.items():
        if prefix.startswith(signature):
            _reject("archive_not_allowed", f"{label} archives are not accepted as mesh uploads")
    if len(prefix) >= 262 and prefix[257:262] == b"ustar":
        _reject("archive_not_allowed", "tar archives are not accepted as mesh uploads")

    executable_signatures = (
        b"\x7fELF",
        b"MZ",
        b"\xfe\xed\xfa\xce",
        b"\xce\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe",
        b"\xbe\xba\xfe\xca",
        b"#!",
    )
    if any(prefix.startswith(signature) for signature in executable_signatures):
        _reject("executable_not_allowed", "executable or script content is not a mesh upload")


def _binary_stl_size(prefix: bytes, byte_size: int) -> bool:
    if len(prefix) < 84:
        return False
    triangle_count = cast(int, struct.unpack_from("<I", prefix, 80)[0])
    return byte_size == 84 + triangle_count * 50


def _detect_format(prefix: bytes, byte_size: int) -> MeshFormat | None:
    if _binary_stl_size(prefix, byte_size):
        return "stl"
    stripped = prefix.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped.startswith((b"ply\n", b"ply\r\n")):
        return "ply"
    first_word = stripped.split(None, 1)[0].lower() if stripped else b""
    if first_word == b"solid":
        return "stl"
    try:
        text = stripped.decode("utf-8")
    except UnicodeDecodeError:
        return None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        directive = line.split(None, 1)[0]
        if directive in {"v", "vn", "vt", "f", *_OBJ_METADATA_DIRECTIVES}:
            return "obj"
        break
    return None


def _checked_float(token: str, *, coordinate: bool, limits: UploadLimits) -> float:
    try:
        value = float(token)
    except ValueError:
        _reject("malformed_mesh", f"invalid floating-point value: {token!r}")
    if not math.isfinite(value):
        _reject("malformed_mesh", "mesh coordinates and vectors must be finite")
    if coordinate and abs(value) > limits.max_coordinate_magnitude:
        _reject(
            "coordinate_limit",
            f"coordinate magnitude exceeds {limits.max_coordinate_magnitude:g}",
        )
    return value


def _bounded_line(stream: BinaryIO, limits: UploadLimits) -> bytes:
    line = stream.readline(limits.max_line_bytes + 1)
    if len(line) > limits.max_line_bytes:
        _reject("malformed_mesh", "mesh contains an unreasonably long line")
    if b"\0" in line:
        _reject("malformed_mesh", "text mesh formats cannot contain NUL bytes")
    return line


def _parse_binary_stl(
    stream: BinaryIO, byte_size: int, limits: UploadLimits
) -> tuple[MeshEncoding, int, int, int]:
    stream.seek(80)
    count_bytes = stream.read(4)
    if len(count_bytes) != 4:
        _reject("malformed_mesh", "binary STL is missing its triangle count")
    triangle_count = struct.unpack("<I", count_bytes)[0]
    if triangle_count <= 0:
        _reject("malformed_mesh", "STL must contain at least one triangle")
    expected_size = 84 + triangle_count * 50
    if expected_size != byte_size:
        _reject("malformed_mesh", "binary STL triangle count does not match file size")
    vertex_count = triangle_count * 3
    if triangle_count > limits.max_triangles:
        _reject("triangle_limit", "STL triangle count exceeds the configured limit")
    if vertex_count > limits.max_vertices:
        _reject("vertex_limit", "STL expanded vertex count exceeds the configured limit")

    for _ in range(triangle_count):
        record = stream.read(50)
        if len(record) != 50:
            _reject("malformed_mesh", "binary STL ended inside a triangle record")
        values = struct.unpack("<12fH", record)
        if not all(math.isfinite(value) for value in values[:12]):
            _reject("malformed_mesh", "binary STL contains non-finite values")
        if any(abs(value) > limits.max_coordinate_magnitude for value in values[3:12]):
            _reject("coordinate_limit", "binary STL coordinate magnitude is unreasonable")
    if stream.read(1):
        _reject("malformed_mesh", "binary STL has unexpected trailing bytes")
    return "binary", vertex_count, triangle_count, triangle_count


def _parse_ascii_stl(
    stream: BinaryIO, limits: UploadLimits
) -> tuple[MeshEncoding, int, int, int]:
    stream.seek(0)
    state = "header"
    triangle_count = 0
    vertex_count = 0
    vertices_in_facet = 0
    ended = False

    while True:
        raw_line = _bounded_line(stream, limits)
        if not raw_line:
            break
        try:
            line = raw_line.decode("ascii").strip()
        except UnicodeDecodeError:
            _reject("malformed_mesh", "ASCII STL contains non-ASCII or binary content")
        if not line:
            continue
        tokens = line.split()
        keyword = tokens[0].casefold()

        if ended:
            _reject("malformed_mesh", "ASCII STL has content after endsolid")
        if state == "header":
            if keyword != "solid":
                _reject("format_mismatch", "STL text must begin with 'solid'")
            state = "facet_or_end"
        elif state == "facet_or_end":
            if keyword == "endsolid":
                ended = True
            elif len(tokens) == 5 and keyword == "facet" and tokens[1].casefold() == "normal":
                for token in tokens[2:]:
                    _checked_float(token, coordinate=False, limits=limits)
                state = "outer_loop"
                vertices_in_facet = 0
            else:
                _reject("malformed_mesh", "ASCII STL expected a facet or endsolid")
        elif state == "outer_loop":
            if len(tokens) != 2 or keyword != "outer" or tokens[1].casefold() != "loop":
                _reject("malformed_mesh", "ASCII STL facet is missing 'outer loop'")
            state = "vertices"
        elif state == "vertices":
            if len(tokens) == 4 and keyword == "vertex":
                for token in tokens[1:]:
                    _checked_float(token, coordinate=True, limits=limits)
                vertices_in_facet += 1
                vertex_count += 1
                if vertex_count > limits.max_vertices:
                    _reject("vertex_limit", "STL vertex count exceeds the configured limit")
                if vertices_in_facet == 3:
                    state = "endloop"
            else:
                _reject("malformed_mesh", "ASCII STL facet must contain exactly three vertices")
        elif state == "endloop":
            if len(tokens) != 1 or keyword != "endloop":
                _reject("malformed_mesh", "ASCII STL facet is missing endloop")
            state = "endfacet"
        elif state == "endfacet":
            if len(tokens) != 1 or keyword != "endfacet":
                _reject("malformed_mesh", "ASCII STL facet is missing endfacet")
            triangle_count += 1
            if triangle_count > limits.max_triangles:
                _reject("triangle_limit", "STL triangle count exceeds the configured limit")
            state = "facet_or_end"

    if not ended or state != "facet_or_end" or triangle_count <= 0:
        _reject("malformed_mesh", "ASCII STL is incomplete or contains no triangles")
    return "ascii", vertex_count, triangle_count, triangle_count


def _parse_stl(
    stream: BinaryIO, byte_size: int, limits: UploadLimits
) -> tuple[MeshEncoding, int, int, int]:
    prefix = _read_prefix(stream, 84)
    if _binary_stl_size(prefix, byte_size):
        return _parse_binary_stl(stream, byte_size, limits)
    return _parse_ascii_stl(stream, limits)


def _parse_obj_index(token: str, *, count_seen: int, kind: str) -> int:
    try:
        value = int(token, 10)
    except ValueError:
        _reject("malformed_mesh", f"OBJ {kind} index is not an integer")
    if value == 0:
        _reject("malformed_mesh", f"OBJ {kind} indices are one-based and cannot be zero")
    if value < 0 and -value > count_seen:
        _reject("malformed_mesh", f"OBJ relative {kind} index is out of range")
    return value


def _parse_obj(
    stream: BinaryIO, limits: UploadLimits
) -> tuple[MeshEncoding, int, int, int]:
    stream.seek(0)
    vertex_count = 0
    texture_count = 0
    normal_count = 0
    face_count = 0
    triangle_count = 0
    max_positive_vertex = 0
    max_positive_texture = 0
    max_positive_normal = 0
    first_line = True

    while True:
        raw_line = _bounded_line(stream, limits)
        if not raw_line:
            break
        try:
            line = raw_line.decode("utf-8")
        except UnicodeDecodeError:
            _reject("malformed_mesh", "OBJ must be UTF-8 text")
        if first_line:
            line = line.removeprefix("\ufeff")
            first_line = False
        line = line.partition("#")[0].strip()
        if not line:
            continue
        if line.endswith("\\"):
            _reject("malformed_mesh", "OBJ line continuations are not accepted")
        tokens = line.split()
        directive = tokens[0]

        if directive in _OBJ_EXTERNAL_DIRECTIVES:
            _reject("external_reference_not_allowed", f"OBJ directive {directive!r} is disabled")
        if directive == "v":
            if len(tokens) not in {4, 5}:
                _reject("malformed_mesh", "OBJ vertex must contain x, y, z and optional w")
            for token in tokens[1:4]:
                _checked_float(token, coordinate=True, limits=limits)
            if len(tokens) == 5:
                _checked_float(tokens[4], coordinate=False, limits=limits)
            vertex_count += 1
            if vertex_count > limits.max_vertices:
                _reject("vertex_limit", "OBJ vertex count exceeds the configured limit")
        elif directive == "vt":
            if not 2 <= len(tokens) <= 4:
                _reject("malformed_mesh", "OBJ texture coordinate has the wrong arity")
            for token in tokens[1:]:
                _checked_float(token, coordinate=False, limits=limits)
            texture_count += 1
            if texture_count > limits.max_vertices:
                _reject("vertex_limit", "OBJ texture coordinate count is unreasonable")
        elif directive == "vn":
            if len(tokens) != 4:
                _reject("malformed_mesh", "OBJ normal must contain exactly three values")
            for token in tokens[1:]:
                _checked_float(token, coordinate=False, limits=limits)
            normal_count += 1
            if normal_count > limits.max_vertices:
                _reject("vertex_limit", "OBJ normal count is unreasonable")
        elif directive == "f":
            face_vertex_count = len(tokens) - 1
            if face_vertex_count < 3:
                _reject("malformed_mesh", "OBJ face must contain at least three vertices")
            if face_vertex_count > limits.max_face_vertices:
                _reject("triangle_limit", "OBJ face has too many vertices")
            for reference in tokens[1:]:
                components = reference.split("/")
                if len(components) > 3 or not components[0]:
                    _reject("malformed_mesh", "OBJ face reference has invalid syntax")
                vertex_index = _parse_obj_index(
                    components[0], count_seen=vertex_count, kind="vertex"
                )
                if vertex_index > 0:
                    max_positive_vertex = max(max_positive_vertex, vertex_index)
                if len(components) >= 2 and components[1]:
                    texture_index = _parse_obj_index(
                        components[1], count_seen=texture_count, kind="texture"
                    )
                    if texture_index > 0:
                        max_positive_texture = max(max_positive_texture, texture_index)
                if len(components) == 3 and components[2]:
                    normal_index = _parse_obj_index(
                        components[2], count_seen=normal_count, kind="normal"
                    )
                    if normal_index > 0:
                        max_positive_normal = max(max_positive_normal, normal_index)
                if len(components) == 2 and not components[1]:
                    _reject("malformed_mesh", "OBJ face reference cannot end with a slash")
                if len(components) == 3 and not components[2]:
                    _reject("malformed_mesh", "OBJ face reference cannot end with a slash")
            face_count += 1
            triangle_count += face_vertex_count - 2
            if triangle_count > limits.max_triangles:
                _reject(
                    "triangle_limit",
                    "triangulated OBJ face count exceeds the configured limit",
                )
        elif directive not in _OBJ_METADATA_DIRECTIVES:
            _reject("unsupported_obj_directive", f"OBJ directive {directive!r} is not allowed")

    if vertex_count < 3 or face_count <= 0:
        _reject("malformed_mesh", "OBJ must contain vertices and at least one face")
    if max_positive_vertex > vertex_count:
        _reject("malformed_mesh", "OBJ face references a missing vertex")
    if max_positive_texture > texture_count:
        _reject("malformed_mesh", "OBJ face references a missing texture coordinate")
    if max_positive_normal > normal_count:
        _reject("malformed_mesh", "OBJ face references a missing normal")
    return "ascii", vertex_count, face_count, triangle_count


@dataclass(frozen=True, slots=True)
class _PlyType:
    struct_code: str
    integer: bool
    minimum: int | None = None
    maximum: int | None = None


_PLY_TYPES: dict[str, _PlyType] = {
    "char": _PlyType("b", True, -128, 127),
    "int8": _PlyType("b", True, -128, 127),
    "uchar": _PlyType("B", True, 0, 255),
    "uint8": _PlyType("B", True, 0, 255),
    "short": _PlyType("h", True, -32768, 32767),
    "int16": _PlyType("h", True, -32768, 32767),
    "ushort": _PlyType("H", True, 0, 65535),
    "uint16": _PlyType("H", True, 0, 65535),
    "int": _PlyType("i", True, -(2**31), 2**31 - 1),
    "int32": _PlyType("i", True, -(2**31), 2**31 - 1),
    "uint": _PlyType("I", True, 0, 2**32 - 1),
    "uint32": _PlyType("I", True, 0, 2**32 - 1),
    "float": _PlyType("f", False),
    "float32": _PlyType("f", False),
    "double": _PlyType("d", False),
    "float64": _PlyType("d", False),
}


@dataclass(frozen=True, slots=True)
class _PlyProperty:
    name: str
    scalar_type: str | None = None
    count_type: str | None = None
    item_type: str | None = None

    @property
    def is_list(self) -> bool:
        return self.count_type is not None


@dataclass(slots=True)
class _PlyElement:
    name: str
    count: int
    properties: list[_PlyProperty] = field(default_factory=list)


def _decode_header_line(raw_line: bytes) -> str:
    try:
        return raw_line.decode("ascii").strip()
    except UnicodeDecodeError:
        _reject("malformed_mesh", "PLY header must be ASCII")


def _parse_ply_header(
    stream: BinaryIO, limits: UploadLimits
) -> tuple[MeshEncoding, list[_PlyElement]]:
    stream.seek(0)
    header_bytes = 0
    first = _bounded_line(stream, limits)
    header_bytes += len(first)
    if first.rstrip(b"\r\n") != b"ply":
        _reject("format_mismatch", "PLY must begin with its magic header")

    encoding: MeshEncoding | None = None
    elements: list[_PlyElement] = []
    names: set[str] = set()
    current: _PlyElement | None = None
    total_records = 0

    while True:
        raw_line = _bounded_line(stream, limits)
        if not raw_line:
            _reject("malformed_mesh", "PLY header is missing end_header")
        header_bytes += len(raw_line)
        if header_bytes > limits.max_header_bytes:
            _reject("malformed_mesh", "PLY header exceeds the configured byte limit")
        line = _decode_header_line(raw_line)
        if not line:
            _reject("malformed_mesh", "PLY header cannot contain blank directives")
        tokens = line.split()
        directive = tokens[0]
        if directive == "end_header":
            if len(tokens) != 1:
                _reject("malformed_mesh", "PLY end_header cannot have arguments")
            break
        if directive == "format":
            if len(tokens) != 3 or tokens[2] != "1.0" or encoding is not None:
                _reject("malformed_mesh", "PLY requires one supported format declaration")
            formats: dict[str, MeshEncoding] = {
                "ascii": "ascii",
                "binary_little_endian": "binary_little_endian",
                "binary_big_endian": "binary_big_endian",
            }
            if tokens[1] not in formats:
                _reject("malformed_mesh", "PLY encoding is not supported")
            encoding = formats[tokens[1]]
        elif directive in {"comment", "obj_info"}:
            metadata = " ".join(tokens[1:]).casefold()
            if metadata.startswith(("texturefile ", "include ")):
                _reject("external_reference_not_allowed", "PLY external references are disabled")
        elif directive == "element":
            if encoding is None or len(tokens) != 3 or not _PLY_NAME.fullmatch(tokens[1]):
                _reject("malformed_mesh", "invalid PLY element declaration")
            try:
                count = int(tokens[2], 10)
            except ValueError:
                _reject("malformed_mesh", "PLY element count is not an integer")
            if count < 0:
                _reject("malformed_mesh", "PLY element count cannot be negative")
            name = tokens[1]
            if name in names:
                _reject("malformed_mesh", "PLY element names must be unique")
            if name == "vertex" and count > limits.max_vertices:
                _reject("vertex_limit", "PLY vertex count exceeds the configured limit")
            if name == "face" and count > limits.max_triangles:
                _reject("triangle_limit", "PLY face count exceeds the configured limit")
            total_records += count
            if total_records > limits.max_vertices + limits.max_triangles:
                _reject("allocation_limit", "PLY declares too many total records")
            current = _PlyElement(name=name, count=count)
            elements.append(current)
            names.add(name)
        elif directive == "property":
            if current is None:
                _reject("malformed_mesh", "PLY property appears before an element")
            if len(current.properties) >= limits.max_properties_per_element:
                _reject("allocation_limit", "PLY element declares too many properties")
            if len(tokens) == 3:
                scalar_type, property_name = tokens[1:]
                if scalar_type not in _PLY_TYPES or not _PLY_NAME.fullmatch(property_name):
                    _reject("malformed_mesh", "invalid PLY scalar property")
                new_property = _PlyProperty(name=property_name, scalar_type=scalar_type)
            elif len(tokens) == 5 and tokens[1] == "list":
                count_type, item_type, property_name = tokens[2:]
                if (
                    count_type not in _PLY_TYPES
                    or item_type not in _PLY_TYPES
                    or not _PLY_TYPES[count_type].integer
                    or not _PLY_NAME.fullmatch(property_name)
                ):
                    _reject("malformed_mesh", "invalid PLY list property")
                new_property = _PlyProperty(
                    name=property_name,
                    count_type=count_type,
                    item_type=item_type,
                )
            else:
                _reject("malformed_mesh", "invalid PLY property declaration")
            if any(item.name == new_property.name for item in current.properties):
                _reject("malformed_mesh", "PLY property names must be unique within an element")
            current.properties.append(new_property)
        else:
            _reject("malformed_mesh", f"unsupported PLY header directive: {directive!r}")

    if encoding is None:
        _reject("malformed_mesh", "PLY header is missing its format")
    by_name = {element.name: element for element in elements}
    if "vertex" not in by_name or "face" not in by_name:
        _reject("malformed_mesh", "PLY must declare vertex and face elements")
    vertex_properties = {item.name: item for item in by_name["vertex"].properties}
    if any(
        name not in vertex_properties or vertex_properties[name].is_list
        for name in ("x", "y", "z")
    ):
        _reject("malformed_mesh", "PLY vertex element must have scalar x, y, z properties")
    face_property = _face_index_property(by_name["face"])
    if face_property.item_type is None or not _PLY_TYPES[face_property.item_type].integer:
        _reject("malformed_mesh", "PLY face vertex indices must use an integer type")
    return encoding, elements


def _face_index_property(element: _PlyElement) -> _PlyProperty:
    matches = [
        item
        for item in element.properties
        if item.name in {"vertex_index", "vertex_indices"} and item.is_list
    ]
    if len(matches) != 1:
        _reject("malformed_mesh", "PLY face requires one vertex_indices list property")
    return matches[0]


def _parse_ascii_scalar(token: str, type_name: str, limits: UploadLimits) -> int | float:
    type_info = _PLY_TYPES[type_name]
    if type_info.integer:
        try:
            value = int(token, 10)
        except ValueError:
            _reject("malformed_mesh", "PLY integer property contains a non-integer")
        if (
            type_info.minimum is not None
            and type_info.maximum is not None
            and not type_info.minimum <= value <= type_info.maximum
        ):
            _reject("malformed_mesh", "PLY integer property is outside its declared type range")
        return value
    return _checked_float(token, coordinate=False, limits=limits)


def _check_ply_coordinate(value: int | float, limits: UploadLimits) -> None:
    numeric = float(value)
    if not math.isfinite(numeric):
        _reject("malformed_mesh", "PLY coordinate is not finite")
    if abs(numeric) > limits.max_coordinate_magnitude:
        _reject("coordinate_limit", "PLY coordinate magnitude exceeds the configured limit")


def _parse_ascii_ply_payload(
    stream: BinaryIO, elements: list[_PlyElement], limits: UploadLimits
) -> tuple[int, int, int]:
    by_name = {element.name: element for element in elements}
    vertex_count = by_name["vertex"].count
    face_count = by_name["face"].count
    triangle_count = 0
    face_property = _face_index_property(by_name["face"])

    for element in elements:
        for _ in range(element.count):
            raw_line = _bounded_line(stream, limits)
            if not raw_line:
                _reject("malformed_mesh", "ASCII PLY ended before all declared records")
            try:
                tokens = raw_line.decode("ascii").split()
            except UnicodeDecodeError:
                _reject("malformed_mesh", "ASCII PLY payload contains non-ASCII bytes")
            cursor = 0
            coordinates: dict[str, int | float] = {}
            face_indices: list[int] | None = None

            for item in element.properties:
                if item.is_list:
                    if cursor >= len(tokens) or item.count_type is None or item.item_type is None:
                        _reject("malformed_mesh", "PLY list property is truncated")
                    count_value = _parse_ascii_scalar(tokens[cursor], item.count_type, limits)
                    cursor += 1
                    if not isinstance(count_value, int) or count_value < 0:
                        _reject("malformed_mesh", "PLY list count must be a non-negative integer")
                    if count_value > limits.max_face_vertices:
                        _reject("allocation_limit", "PLY list count is unreasonable")
                    if cursor + count_value > len(tokens):
                        _reject("malformed_mesh", "PLY list property is truncated")
                    capture = element.name == "face" and item.name == face_property.name
                    captured: list[int] = []
                    for token in tokens[cursor : cursor + count_value]:
                        value = _parse_ascii_scalar(token, item.item_type, limits)
                        if capture:
                            if not isinstance(value, int):
                                _reject("malformed_mesh", "PLY face index is not an integer")
                            captured.append(value)
                    if capture:
                        face_indices = captured
                    cursor += count_value
                else:
                    if cursor >= len(tokens) or item.scalar_type is None:
                        _reject("malformed_mesh", "PLY scalar property is truncated")
                    value = _parse_ascii_scalar(tokens[cursor], item.scalar_type, limits)
                    cursor += 1
                    if element.name == "vertex" and item.name in {"x", "y", "z"}:
                        coordinates[item.name] = value
            if cursor != len(tokens):
                _reject("malformed_mesh", "PLY record contains extra values")
            if element.name == "vertex":
                for coordinate in ("x", "y", "z"):
                    _check_ply_coordinate(coordinates[coordinate], limits)
            if element.name == "face":
                if face_indices is None or len(face_indices) < 3:
                    _reject("malformed_mesh", "PLY face must contain at least three indices")
                if any(index < 0 or index >= vertex_count for index in face_indices):
                    _reject("malformed_mesh", "PLY face references a missing vertex")
                triangle_count += len(face_indices) - 2
                if triangle_count > limits.max_triangles:
                    _reject("triangle_limit", "triangulated PLY face count exceeds the limit")

    while True:
        trailing = _bounded_line(stream, limits)
        if not trailing:
            break
        if trailing.strip():
            _reject("malformed_mesh", "ASCII PLY contains trailing records")
    if vertex_count < 3 or face_count <= 0 or triangle_count <= 0:
        _reject("malformed_mesh", "PLY must contain vertices and faces")
    return vertex_count, face_count, triangle_count


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        _reject("malformed_mesh", "binary PLY ended inside a declared property")
    return data


def _read_binary_scalar(stream: BinaryIO, type_name: str, endian: str) -> int | float:
    type_info = _PLY_TYPES[type_name]
    size = struct.calcsize(type_info.struct_code)
    value = cast(
        int | float,
        struct.unpack(endian + type_info.struct_code, _read_exact(stream, size))[0],
    )
    if isinstance(value, float) and not math.isfinite(value):
        _reject("malformed_mesh", "binary PLY contains a non-finite floating-point value")
    return value


def _parse_binary_ply_payload(
    stream: BinaryIO,
    elements: list[_PlyElement],
    encoding: MeshEncoding,
    limits: UploadLimits,
) -> tuple[int, int, int]:
    endian = "<" if encoding == "binary_little_endian" else ">"
    by_name = {element.name: element for element in elements}
    vertex_count = by_name["vertex"].count
    face_count = by_name["face"].count
    face_property = _face_index_property(by_name["face"])
    triangle_count = 0

    for element in elements:
        for _ in range(element.count):
            coordinates: dict[str, int | float] = {}
            face_indices: list[int] | None = None
            for item in element.properties:
                if item.is_list:
                    if item.count_type is None or item.item_type is None:
                        _reject("malformed_mesh", "invalid binary PLY list declaration")
                    count_value = _read_binary_scalar(stream, item.count_type, endian)
                    if not isinstance(count_value, int) or count_value < 0:
                        _reject("malformed_mesh", "binary PLY list count is invalid")
                    if count_value > limits.max_face_vertices:
                        _reject("allocation_limit", "binary PLY list count is unreasonable")
                    capture = element.name == "face" and item.name == face_property.name
                    captured: list[int] = []
                    for _ in range(count_value):
                        value = _read_binary_scalar(stream, item.item_type, endian)
                        if capture:
                            if not isinstance(value, int):
                                _reject("malformed_mesh", "PLY face index is not an integer")
                            captured.append(value)
                    if capture:
                        face_indices = captured
                else:
                    if item.scalar_type is None:
                        _reject("malformed_mesh", "invalid binary PLY scalar declaration")
                    value = _read_binary_scalar(stream, item.scalar_type, endian)
                    if element.name == "vertex" and item.name in {"x", "y", "z"}:
                        coordinates[item.name] = value
            if element.name == "vertex":
                for coordinate in ("x", "y", "z"):
                    _check_ply_coordinate(coordinates[coordinate], limits)
            if element.name == "face":
                if face_indices is None or len(face_indices) < 3:
                    _reject("malformed_mesh", "PLY face must contain at least three indices")
                if any(index < 0 or index >= vertex_count for index in face_indices):
                    _reject("malformed_mesh", "PLY face references a missing vertex")
                triangle_count += len(face_indices) - 2
                if triangle_count > limits.max_triangles:
                    _reject("triangle_limit", "triangulated PLY face count exceeds the limit")

    if stream.read(1):
        _reject("malformed_mesh", "binary PLY contains trailing bytes")
    if vertex_count < 3 or face_count <= 0 or triangle_count <= 0:
        _reject("malformed_mesh", "PLY must contain vertices and faces")
    return vertex_count, face_count, triangle_count


def _parse_ply(
    stream: BinaryIO, limits: UploadLimits
) -> tuple[MeshEncoding, int, int, int]:
    encoding, elements = _parse_ply_header(stream, limits)
    if encoding == "ascii":
        vertex_count, face_count, triangle_count = _parse_ascii_ply_payload(
            stream, elements, limits
        )
    else:
        vertex_count, face_count, triangle_count = _parse_binary_ply_payload(
            stream, elements, encoding, limits
        )
    return encoding, vertex_count, face_count, triangle_count


def preflight_mesh_upload(
    path: Path,
    display_filename: str,
    *,
    limits: UploadLimits | None = None,
    max_bytes: int | None = None,
    max_triangles: int | None = None,
    max_vertices: int | None = None,
    max_coordinate_magnitude: float | None = None,
) -> MeshPreflight:
    """Safely validate an STL/OBJ/PLY staged upload before parser or worker use.

    Optional scalar limit arguments support route configuration without requiring callers to
    construct ``UploadLimits``. They override the corresponding values on ``limits``.
    """

    active_limits = limits or UploadLimits()
    if any(
        value is not None
        for value in (max_bytes, max_triangles, max_vertices, max_coordinate_magnitude)
    ):
        active_limits = UploadLimits(
            max_bytes=active_limits.max_bytes if max_bytes is None else max_bytes,
            max_triangles=(
                active_limits.max_triangles if max_triangles is None else max_triangles
            ),
            max_vertices=active_limits.max_vertices if max_vertices is None else max_vertices,
            max_coordinate_magnitude=(
                active_limits.max_coordinate_magnitude
                if max_coordinate_magnitude is None
                else max_coordinate_magnitude
            ),
            max_header_bytes=active_limits.max_header_bytes,
            max_line_bytes=active_limits.max_line_bytes,
            max_face_vertices=active_limits.max_face_vertices,
            max_properties_per_element=active_limits.max_properties_per_element,
        )

    try:
        safe_filename = validate_display_filename(display_filename)
    except UnsafeNameError as error:
        raise UploadValidationError("unsafe_filename", str(error)) from error
    suffix = Path(safe_filename).suffix.casefold()
    try:
        expected_format = _EXTENSIONS[suffix]
    except KeyError as error:
        raise UploadValidationError(
            "unsupported_extension", "only .stl, .obj, and .ply mesh uploads are accepted"
        ) from error

    with _open_regular_file(Path(path)) as (stream, initial_status):
        if initial_status.st_size <= 0:
            _reject("empty_upload", "mesh upload cannot be empty")
        if initial_status.st_size > active_limits.max_bytes:
            _reject("file_size_limit", "mesh upload exceeds the configured byte limit")
        prefix = _read_prefix(stream)
        _reject_forbidden_magic(prefix)
        detected_format = _detect_format(prefix, initial_status.st_size)
        if detected_format is not None and detected_format != expected_format:
            _reject(
                "format_mismatch",
                f"filename declares {expected_format.upper()} but content looks like "
                f"{detected_format.upper()}",
            )
        digest = _sha256(stream, max_bytes=active_limits.max_bytes)
        if expected_format == "stl":
            encoding, vertex_count, face_count, triangle_count = _parse_stl(
                stream, initial_status.st_size, active_limits
            )
        elif expected_format == "obj":
            encoding, vertex_count, face_count, triangle_count = _parse_obj(
                stream, active_limits
            )
        else:
            encoding, vertex_count, face_count, triangle_count = _parse_ply(
                stream, active_limits
            )
        final_status = os.fstat(stream.fileno())
        if (
            final_status.st_size != initial_status.st_size
            or final_status.st_mtime_ns != initial_status.st_mtime_ns
        ):
            _reject("upload_changed", "upload changed during structural validation")

    return MeshPreflight(
        format=expected_format,
        encoding=encoding,
        byte_size=initial_status.st_size,
        sha256=digest,
        display_filename=safe_filename,
        vertex_count=vertex_count,
        face_count=face_count,
        triangle_count=triangle_count,
    )


__all__ = [
    "MeshEncoding",
    "MeshFormat",
    "MeshPreflight",
    "UploadLimits",
    "UploadValidationError",
    "preflight_mesh_upload",
]
