"""Audit STEP ground truth and STL meshes for the ``samples/real`` corpus.

Every number written into ``part.json`` is recomputed from the files on disk, so an
audit run is reproducible from the corpus alone without rebuilding any CadQuery part.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cadquery as cq
import numpy as np
import trimesh
from OCP.Bnd import Bnd_Box
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.gp import gp_Pnt, gp_Vec
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_Orientation, TopAbs_ShapeEnum
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS, TopoDS_Face, TopoDS_Shape
from OCP.TopTools import TopTools_IndexedMapOfShape

SCHEMA_VERSION = 1
PART_JSON = "part.json"
STEP_FILE = "model.step"

#: Significant digits kept for every float written to ``part.json``. Rounding keeps the
#: serialized corpus stable against last-bit kernel jitter between runs; nine digits is
#: still nanometre resolution on a 100 mm part.
FLOAT_DIGITS = 9

#: A cylindrical face counts as "full" when its u range covers a whole revolution.
_FULL_TURN_TOLERANCE = 1e-6

ORIGINS = ("generated", "user-design", "user-export", "public")

#: Mesh-entry keys that record where a mesh came from rather than what it contains.
PROVENANCE_KEYS = ("sourceFormat", "sourceSha256", "sourceUnit")

_SURFACE_NAMES: dict[Any, str] = {
    GeomAbs_SurfaceType.GeomAbs_Plane: "plane",
    GeomAbs_SurfaceType.GeomAbs_Cylinder: "cylinder",
    GeomAbs_SurfaceType.GeomAbs_Cone: "cone",
    GeomAbs_SurfaceType.GeomAbs_Sphere: "sphere",
    GeomAbs_SurfaceType.GeomAbs_Torus: "torus",
    GeomAbs_SurfaceType.GeomAbs_BSplineSurface: "bspline",
    GeomAbs_SurfaceType.GeomAbs_BezierSurface: "bezier",
    GeomAbs_SurfaceType.GeomAbs_SurfaceOfExtrusion: "extrusion",
    GeomAbs_SurfaceType.GeomAbs_SurfaceOfRevolution: "revolution",
    GeomAbs_SurfaceType.GeomAbs_OffsetSurface: "offset",
    GeomAbs_SurfaceType.GeomAbs_OtherSurface: "other",
}


class CorpusError(RuntimeError):
    """Raised for any recoverable corpus tooling failure surfaced on the CLI."""


@dataclass(frozen=True, slots=True)
class MeshRole:
    """One tessellation slot: its filename and the tolerances used to produce it."""

    tessellation: str
    filename: str
    linear_tolerance: float | None
    angular_tolerance: float | None


#: Tessellation ladder written next to every STEP ground truth.
GENERATED_MESH_ROLES: tuple[MeshRole, ...] = (
    MeshRole("coarse", "mesh-coarse.stl", 0.5, 0.5),
    MeshRole("default", "mesh-default.stl", 0.1, 0.1),
)

#: Opt-in dense tier (``--with-fine``); kept out of the committed corpus for size.
FINE_MESH_ROLE = MeshRole("fine", "mesh-fine.stl", 0.01, 0.05)

#: Slots used for user-supplied meshes; one per accepted source format.
EXPORT_MESH_ROLE = MeshRole("export", "mesh-export.stl", None, None)
EXPORT_3MF_MESH_ROLE = MeshRole("export", "mesh-export-3mf.stl", None, None)

#: Source format recorded for a mesh, keyed by the file extension it was ingested from.
SOURCE_FORMATS: dict[str, str] = {".stl": "stl", ".3mf": "3mf", ".step": "step", ".stp": "step"}
EXPORT_ROLE_BY_FORMAT: dict[str, MeshRole] = {
    "stl": EXPORT_MESH_ROLE,
    "3mf": EXPORT_3MF_MESH_ROLE,
}

MESH_ROLES: tuple[MeshRole, ...] = (
    *GENERATED_MESH_ROLES,
    FINE_MESH_ROLE,
    EXPORT_MESH_ROLE,
    EXPORT_3MF_MESH_ROLE,
)
_MESH_ROLES_BY_FILENAME: dict[str, MeshRole] = {role.filename: role for role in MESH_ROLES}
_MESH_ROLE_RANK: dict[str, int] = {role.filename: index for index, role in enumerate(MESH_ROLES)}


@dataclass(frozen=True, slots=True)
class PartMetadata:
    """The human-authored half of ``part.json``; never derived from geometry."""

    slug: str
    title: str
    origin: str
    license: str
    units: str = "mm"
    tags: tuple[str, ...] = ()
    notes: str = ""
    featured: bool = False

    def __post_init__(self) -> None:
        if self.origin not in ORIGINS:
            raise CorpusError(f"unknown origin {self.origin!r}; expected one of {ORIGINS}")


def _round(value: float) -> float:
    # ``+ 0.0`` normalizes the negative zero that rounding can produce.
    return float(f"{float(value):.{FLOAT_DIGITS}g}") + 0.0


def _round_all(values: Any) -> list[float]:
    return [_round(float(value)) for value in values]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sub_shapes(shape: TopoDS_Shape, kind: TopAbs_ShapeEnum) -> list[TopoDS_Shape]:
    """Return the unique sub-shapes of ``kind`` in deterministic traversal order."""

    mapped = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, mapped)
    return [mapped.FindKey(index) for index in range(1, mapped.Extent() + 1)]


def _bounding_box(shape: TopoDS_Shape) -> dict[str, list[float]]:
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    # BRepBndLib inflates the box by the shape tolerance; drop it so repeated audits of
    # the same solid report the nominal extents.
    box.SetGap(0.0)
    x_min, y_min, z_min, x_max, y_max, z_max = box.Get()
    return {
        "min": _round_all((x_min, y_min, z_min)),
        "max": _round_all((x_max, y_max, z_max)),
    }


def _volume(shape: TopoDS_Shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return _round(props.Mass())


def _surface_name(face: TopoDS_Face) -> str:
    return _SURFACE_NAMES.get(BRepAdaptor_Surface(face).GetType(), "other")


def is_hole_face(face: TopoDS_Face) -> bool:
    """Heuristic: does this face bound a cylindrical hole through the material?

    A face qualifies when it is a cylinder whose u range spans a full revolution and
    whose material side faces inward -- that is, the outward-of-material normal (the
    surface normal flipped for a REVERSED face) points back toward the cylinder axis.
    See ``samples/real/README.md`` for the caveats this simplification accepts.
    """

    adaptor = BRepAdaptor_Surface(face)
    if adaptor.GetType() != GeomAbs_SurfaceType.GeomAbs_Cylinder:
        return False
    u_min, u_max, v_min, v_max = BRepTools.UVBounds_s(face)
    if abs((u_max - u_min) - 2.0 * math.pi) > _FULL_TURN_TOLERANCE:
        return False

    point = gp_Pnt()
    d_u = gp_Vec()
    d_v = gp_Vec()
    adaptor.D1(0.5 * (u_min + u_max), 0.5 * (v_min + v_max), point, d_u, d_v)
    normal = d_u.Crossed(d_v)
    if face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
        normal.Reverse()

    axis = adaptor.Cylinder().Axis()
    offset = gp_Vec(axis.Location(), point)
    along = gp_Vec(axis.Direction())
    radial = offset.Subtracted(along.Multiplied(offset.Dot(along)))
    if radial.Magnitude() <= 1e-9:
        return False
    return bool(normal.Dot(radial) < 0.0)


def load_step_shape(path: Path) -> TopoDS_Shape:
    """Import a STEP file and return its raw OCCT shape."""

    try:
        imported = cq.importers.importStep(str(path))
    except Exception as exc:
        raise CorpusError(f"cannot import STEP {path}: {exc}") from exc
    value = imported.val()
    if not isinstance(value, cq.Shape):
        raise CorpusError(f"STEP file contains no shape: {path}")
    shape: TopoDS_Shape | None = value.wrapped
    if shape is None:
        raise CorpusError(f"STEP file contains no shape: {path}")
    return shape


def audit_step(path: Path) -> dict[str, Any]:
    """Return the ``groundTruth`` block for a STEP file."""

    shape = load_step_shape(path)
    faces = [TopoDS.Face_s(face) for face in _sub_shapes(shape, TopAbs_ShapeEnum.TopAbs_FACE)]

    inventory: dict[str, int] = {}
    hole_count = 0
    for face in faces:
        name = _surface_name(face)
        inventory[name] = inventory.get(name, 0) + 1
        if is_hole_face(face):
            hole_count += 1

    return {
        "step": path.name,
        "sha256": sha256_file(path),
        "solidCount": len(_sub_shapes(shape, TopAbs_ShapeEnum.TopAbs_SOLID)),
        "faceCount": len(faces),
        "edgeCount": len(_sub_shapes(shape, TopAbs_ShapeEnum.TopAbs_EDGE)),
        "vertexCount": len(_sub_shapes(shape, TopAbs_ShapeEnum.TopAbs_VERTEX)),
        "surfaceInventory": dict(sorted(inventory.items())),
        "holeCount": hole_count,
        "volume": _volume(shape),
        "bbox": _bounding_box(shape),
    }


def audit_mesh(path: Path, role: MeshRole) -> dict[str, Any]:
    """Return one ``meshes`` entry for an STL file."""

    try:
        raw = trimesh.load(str(path), file_type="stl", process=False)
    except Exception as exc:
        raise CorpusError(f"cannot load STL {path}: {exc}") from exc
    if not hasattr(raw, "faces"):
        raise CorpusError(f"STL did not load as a single mesh: {path}")

    # STL stores every triangle independently; connectivity only exists after a merge.
    mesh = raw.copy()
    mesh.merge_vertices()

    _, edge_counts = np.unique(mesh.edges_sorted, axis=0, return_counts=True)
    edge_manifold = bool(np.all(edge_counts == 2))
    face_keys = np.sort(np.asarray(mesh.faces), axis=1)
    unique_faces = int(np.unique(face_keys, axis=0).shape[0])
    watertight = bool(mesh.is_watertight)
    bounds = np.asarray(mesh.bounds, dtype=float)

    return {
        "file": path.name,
        "tessellation": role.tessellation,
        "linearTolerance": role.linear_tolerance,
        "angularTolerance": role.angular_tolerance,
        "sha256": sha256_file(path),
        "triangles": len(mesh.faces),
        "vertices": len(mesh.vertices),
        "watertight": watertight,
        "windingConsistent": bool(mesh.is_winding_consistent),
        "edgeManifold": edge_manifold,
        "degenerateFaces": int(np.count_nonzero(np.asarray(mesh.area_faces) < 1e-12)),
        "duplicateFaces": len(mesh.faces) - unique_faces,
        "volume": _round(mesh.volume) if watertight else None,
        "bbox": {"min": _round_all(bounds[0]), "max": _round_all(bounds[1])},
    }


def mesh_role_for(path: Path) -> MeshRole:
    """Map an STL filename onto its tessellation slot, defaulting to ``export``."""

    known = _MESH_ROLES_BY_FILENAME.get(path.name)
    if known is not None:
        return known
    return MeshRole("export", path.name, None, None)


def discover_meshes(directory: Path) -> list[Path]:
    """Return the STL files of a part directory in tessellation order."""

    return sorted(
        directory.glob("*.stl"),
        key=lambda path: (_MESH_ROLE_RANK.get(path.name, len(MESH_ROLES)), path.name),
    )


def read_mesh_provenance(directory: Path) -> dict[str, dict[str, Any]]:
    """Recover per-mesh provenance from an existing ``part.json``, keyed by filename.

    Geometry is always recomputed from disk, but where a mesh *came from* (a 3MF, say,
    whose original bytes are not kept in the corpus) cannot be re-derived, so an audit
    carries the recorded provenance forward.
    """

    if not (directory / PART_JSON).is_file():
        return {}
    payload = read_part_json(directory)
    recorded: dict[str, dict[str, Any]] = {}
    for entry in payload.get("meshes", []):
        if not isinstance(entry, dict) or "file" not in entry:
            continue
        recorded[str(entry["file"])] = {key: entry[key] for key in PROVENANCE_KEYS if key in entry}
    return recorded


def audit_directory(
    directory: Path,
    metadata: PartMetadata,
    provenance: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the complete ``part.json`` payload from the files in ``directory``.

    ``provenance`` overrides the recorded source of individual mesh files (used by
    ``ingest``); when omitted, whatever the existing ``part.json`` recorded is kept.
    """

    step_path = directory / STEP_FILE
    ground_truth = audit_step(step_path) if step_path.is_file() else None
    recorded = dict(read_mesh_provenance(directory))
    if provenance is not None:
        recorded.update({name: dict(values) for name, values in provenance.items()})

    meshes: list[dict[str, Any]] = []
    for path in discover_meshes(directory):
        role = mesh_role_for(path)
        entry = audit_mesh(path, role)
        source = recorded.get(path.name, {})
        default_format = "step" if role.tessellation != "export" else "stl"
        entry["sourceFormat"] = source.get("sourceFormat", default_format)
        entry["sourceSha256"] = source.get("sourceSha256")
        entry["sourceUnit"] = source.get("sourceUnit")
        meshes.append(entry)

    if ground_truth is None and not meshes:
        raise CorpusError(f"part directory has no model.step and no STL: {directory}")
    return {
        "schemaVersion": SCHEMA_VERSION,
        "slug": metadata.slug,
        "title": metadata.title,
        "origin": metadata.origin,
        "license": metadata.license,
        "units": metadata.units,
        "tags": list(metadata.tags),
        "notes": metadata.notes,
        "featured": metadata.featured,
        "groundTruth": ground_truth,
        "meshes": meshes,
    }


def dump_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def write_part_json(directory: Path, payload: dict[str, Any]) -> Path:
    path = directory / PART_JSON
    path.write_text(dump_json(payload), encoding="utf-8")
    return path


def read_part_json(directory: Path) -> dict[str, Any]:
    path = directory / PART_JSON
    if not path.is_file():
        raise CorpusError(f"missing {PART_JSON} in {directory}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusError(f"invalid {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CorpusError(f"invalid {path}: expected a JSON object")
    return payload


def read_part_metadata(directory: Path) -> PartMetadata:
    """Recover the authored metadata of an existing part so an audit can preserve it."""

    payload = read_part_json(directory)
    try:
        return PartMetadata(
            slug=str(payload["slug"]),
            title=str(payload["title"]),
            origin=str(payload["origin"]),
            license=str(payload["license"]),
            units=str(payload.get("units", "mm")),
            tags=tuple(str(tag) for tag in payload.get("tags", ())),
            notes=str(payload.get("notes", "")),
            featured=bool(payload.get("featured", False)),
        )
    except KeyError as exc:
        raise CorpusError(f"{directory / PART_JSON} is missing key {exc}") from exc
