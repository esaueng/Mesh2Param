"""Minimal 3MF reader built on the standard library only.

The corpus needs 3MF as an *input* format for hand-supplied meshes, not a full
implementation of the spec: this reads the core mesh of ``3D/3dmodel.model`` and applies
the build transforms. Anything it does not understand raises :class:`CorpusError` rather
than guessing, because a silently mis-scaled fixture is worse than a failed ingest.

Input is a local file an operator hands to ``ingest`` on the command line, so the
standard-library parser is used deliberately: no third-party XML dependency is pulled in
for it. Do not point this at untrusted uploads without a hardened parser.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .audit import CorpusError

CORE_NAMESPACE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
MODEL_ENTRY = "3D/3dmodel.model"

#: Millimetres per 3MF unit, from the core specification's ``unit`` enumeration.
UNIT_TO_MM: dict[str, float] = {
    "micron": 0.001,
    "millimeter": 1.0,
    "centimeter": 10.0,
    "inch": 25.4,
    "foot": 304.8,
    "meter": 1000.0,
}

#: Millimetres per corpus unit, so a mesh can be emitted in the part's declared units.
CORPUS_UNIT_TO_MM: dict[str, float] = {"mm": 1.0, "in": 25.4}


@dataclass(frozen=True, slots=True)
class ThreeMFMesh:
    """A single triangle soup read out of a 3MF package, in its declared unit."""

    vertices: np.ndarray
    triangles: np.ndarray
    unit: str

    @property
    def triangle_count(self) -> int:
        return int(self.triangles.shape[0])

    @property
    def vertex_count(self) -> int:
        return int(self.vertices.shape[0])

    def scaled_to(self, corpus_unit: str) -> ThreeMFMesh:
        """Return the same mesh rescaled from its declared unit into ``corpus_unit``."""

        target = CORPUS_UNIT_TO_MM.get(corpus_unit)
        if target is None:
            raise CorpusError(f"unsupported corpus unit {corpus_unit!r}")
        factor = UNIT_TO_MM[self.unit] / target
        if factor == 1.0:
            return self
        return ThreeMFMesh(self.vertices * factor, self.triangles, self.unit)


def _tag(name: str) -> str:
    return f"{{{CORE_NAMESPACE}}}{name}"


def _float(value: str | None, *, context: str) -> float:
    try:
        return float(value if value is not None else "nan")
    except ValueError as exc:
        raise CorpusError(f"3MF {context} has a non-numeric coordinate {value!r}") from exc


def _parse_transform(raw: str | None) -> np.ndarray | None:
    """Parse a 3MF ``transform`` attribute into a 4x3 row-major matrix."""

    if raw is None or not raw.strip():
        return None
    values = raw.split()
    if len(values) != 12:
        raise CorpusError(f"3MF transform needs 12 numbers, got {len(values)}")
    try:
        numbers = [float(value) for value in values]
    except ValueError as exc:
        raise CorpusError(f"3MF transform is not numeric: {raw!r}") from exc
    return np.asarray(numbers, dtype=float).reshape(4, 3)


def _apply_transform(vertices: np.ndarray, transform: np.ndarray | None) -> np.ndarray:
    if transform is None:
        return vertices
    return np.asarray(vertices @ transform[:3, :] + transform[3, :], dtype=float)


def _read_object_mesh(obj: ElementTree.Element, object_id: str) -> tuple[np.ndarray, np.ndarray]:
    mesh = obj.find(_tag("mesh"))
    if mesh is None:
        raise CorpusError(
            f"3MF object {object_id!r} has no <mesh>; component-only objects are not supported"
        )
    vertices_node = mesh.find(_tag("vertices"))
    triangles_node = mesh.find(_tag("triangles"))
    if vertices_node is None or triangles_node is None:
        raise CorpusError(f"3MF object {object_id!r} is missing <vertices> or <triangles>")

    vertices = np.asarray(
        [
            [
                _float(vertex.get("x"), context=f"object {object_id!r} vertex"),
                _float(vertex.get("y"), context=f"object {object_id!r} vertex"),
                _float(vertex.get("z"), context=f"object {object_id!r} vertex"),
            ]
            for vertex in vertices_node.findall(_tag("vertex"))
        ],
        dtype=float,
    )
    triangles = np.asarray(
        [
            [
                int(triangle.get("v1", "-1")),
                int(triangle.get("v2", "-1")),
                int(triangle.get("v3", "-1")),
            ]
            for triangle in triangles_node.findall(_tag("triangle"))
        ],
        dtype=np.int64,
    )
    if vertices.size == 0 or triangles.size == 0:
        raise CorpusError(f"3MF object {object_id!r} has an empty mesh")
    if triangles.min() < 0 or triangles.max() >= len(vertices):
        raise CorpusError(f"3MF object {object_id!r} references vertices outside its <vertices>")
    return vertices, triangles


def read_3mf(path: Path) -> ThreeMFMesh:
    """Read the build of a 3MF package into a single triangle soup."""

    try:
        with zipfile.ZipFile(path) as archive:
            try:
                payload = archive.read(MODEL_ENTRY)
            except KeyError as exc:
                raise CorpusError(f"3MF package has no {MODEL_ENTRY}: {path}") from exc
    except zipfile.BadZipFile as exc:
        raise CorpusError(f"not a readable 3MF package: {path}") from exc

    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise CorpusError(f"invalid XML in {MODEL_ENTRY} of {path}: {exc}") from exc
    if root.tag != _tag("model"):
        raise CorpusError(f"{MODEL_ENTRY} of {path} is not a core-spec 3MF <model>")

    unit = root.get("unit", "millimeter")
    if unit not in UNIT_TO_MM:
        raise CorpusError(f"unknown 3MF unit {unit!r} in {path}")

    objects = {
        obj.get("id", ""): obj for obj in root.iter(_tag("object")) if obj.get("id") is not None
    }
    items = [item for item in root.iter(_tag("item"))]
    if not items:
        raise CorpusError(f"3MF package has an empty <build>: {path}")

    object_ids = sorted({str(item.get("objectid", "")) for item in items})
    if len(object_ids) > 1:
        raise CorpusError(
            f"3MF build references {len(object_ids)} different objects "
            f"({', '.join(object_ids)}); ingest one object per part"
        )

    object_id = object_ids[0]
    obj = objects.get(object_id)
    if obj is None:
        raise CorpusError(f"3MF build references unknown object id {object_id!r} in {path}")
    vertices, triangles = _read_object_mesh(obj, object_id)

    # Several items of the same object are instances of one part; merge them so the
    # exported STL matches what a slicer would show on the build plate.
    blocks: list[np.ndarray] = []
    faces: list[np.ndarray] = []
    for index, item in enumerate(items):
        placed = _apply_transform(vertices, _parse_transform(item.get("transform")))
        blocks.append(placed)
        faces.append(triangles + index * len(vertices))
    return ThreeMFMesh(np.vstack(blocks), np.vstack(faces), unit)
