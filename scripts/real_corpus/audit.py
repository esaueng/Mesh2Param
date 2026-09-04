"""Audit STEP ground truth and STL meshes for the ``samples/real`` corpus.

Every number written into ``part.json`` is recomputed from the files on disk, so an
audit run is reproducible from the corpus alone without rebuilding any CadQuery part.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections.abc import Mapping, Sequence
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
from OCP.TopTools import (
    TopTools_IndexedDataMapOfShapeListOfShape,
    TopTools_IndexedMapOfShape,
)

SCHEMA_VERSION = 1
PART_JSON = "part.json"
STEP_FILE = "model.step"

#: Significant digits kept for every float written to ``part.json``. Rounding keeps the
#: serialized corpus stable against last-bit kernel jitter between runs; nine digits is
#: still nanometre resolution on a 100 mm part.
FLOAT_DIGITS = 9

#: A cylindrical face counts as "full" when its u range covers a whole revolution.
_FULL_TURN_TOLERANCE = 1e-6
#: Slack for sweeps summed across split faces, which lose slivers to boolean trimming.
_SWEEP_TOLERANCE = 1e-4

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


@dataclass
class _BoreFace:
    """One inward-facing cylindrical face, reduced to what hole grouping needs."""

    axis_point: gp_Pnt
    axis_dir: gp_Vec
    radius: float
    sweep: float
    axial_min: float
    axial_max: float


def _bore_face(face: TopoDS_Face) -> _BoreFace | None:
    """Return the bore description of ``face`` if it is a cylinder facing its own axis.

    The material side is inferred from the surface normal (flipped for a REVERSED face):
    a bore's outward-of-material normal points back toward the axis, a boss's points away.
    """

    adaptor = BRepAdaptor_Surface(face)
    if adaptor.GetType() != GeomAbs_SurfaceType.GeomAbs_Cylinder:
        return None
    u_min, u_max, v_min, v_max = BRepTools.UVBounds_s(face)

    point = gp_Pnt()
    d_u = gp_Vec()
    d_v = gp_Vec()
    adaptor.D1(0.5 * (u_min + u_max), 0.5 * (v_min + v_max), point, d_u, d_v)
    normal = d_u.Crossed(d_v)
    if face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
        normal.Reverse()

    cylinder = adaptor.Cylinder()
    axis = cylinder.Axis()
    along = gp_Vec(axis.Direction())
    offset = gp_Vec(axis.Location(), point)
    radial = offset.Subtracted(along.Multiplied(offset.Dot(along)))
    if radial.Magnitude() <= 1e-9 or normal.Dot(radial) >= 0.0:
        return None

    # Canonical axis: direction with a positive leading component, located at the point
    # of the axis nearest the origin, so split faces on one bore compare equal.
    if tuple(along.Coord()) < (0.0, 0.0, 0.0):
        along.Reverse()
    location = gp_Vec(axis.Location().XYZ())
    axis_point = gp_Pnt(location.Subtracted(along.Multiplied(location.Dot(along))).XYZ())

    box = Bnd_Box()
    BRepBndLib.Add_s(face, box, False)
    x0, y0, z0, x1, y1, z1 = box.Get()
    stations = [along.Dot(gp_Vec(x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    return _BoreFace(
        axis_point=axis_point,
        axis_dir=along,
        radius=cylinder.Radius(),
        sweep=min(u_max - u_min, 2.0 * math.pi),
        axial_min=min(stations),
        axial_max=max(stations),
    )


def _same_bore_axis(a: _BoreFace, b: _BoreFace, tolerance: float) -> bool:
    if abs(a.radius - b.radius) > tolerance:
        return False
    if abs(a.axis_dir.Dot(b.axis_dir)) < 1.0 - 1e-6:
        return False
    return bool(a.axis_point.Distance(b.axis_point) <= tolerance)


def count_holes(faces: Sequence[TopoDS_Face], *, tolerance: float = 1e-3) -> int:
    """Count cylindrical bores, treating faces split around one bore as a single hole.

    Inward-facing cylindrical faces are grouped by axis and radius. Within a group, faces
    whose axial extents overlap or touch are merged; each merged run whose angular sweeps
    add up to a full revolution counts as one hole. Coaxial bores of the same radius that
    are separated along the axis (a hole through each wall of a channel) count separately.
    Blind holes and every stage of a stepped bore count; countersinks and bosses do not.
    """

    bores = [bore for face in faces if (bore := _bore_face(face)) is not None]
    groups: list[list[_BoreFace]] = []
    for bore in bores:
        for group in groups:
            if _same_bore_axis(group[0], bore, tolerance):
                group.append(bore)
                break
        else:
            groups.append([bore])

    holes = 0
    for group in groups:
        runs: list[list[float]] = []  # [axial_min, axial_max, sweep]
        for bore in sorted(group, key=lambda item: item.axial_min):
            if runs and bore.axial_min <= runs[-1][1] + tolerance:
                runs[-1][1] = max(runs[-1][1], bore.axial_max)
                runs[-1][2] += bore.sweep
            else:
                runs.append([bore.axial_min, bore.axial_max, bore.sweep])
        holes += sum(1 for run in runs if run[2] >= 2.0 * math.pi - _SWEEP_TOLERANCE)
    return holes


#: Angular slack, in degrees, when two analytic surfaces are called the same one.
_MERGE_ANGLE_TOLERANCE_DEG = 0.5
#: Positional slack, as a fraction of the shape's bounding-box diagonal.
_MERGE_DISTANCE_FRACTION = 1e-4
#: Relative slack on radii.
_MERGE_RADIUS_FRACTION = 0.005

#: Surface types a merged inventory can collapse; everything else stays per-face.
MERGEABLE_SURFACES: tuple[str, ...] = ("plane", "cylinder", "cone", "sphere", "torus")
MERGED_INVENTORY_KEYS: tuple[str, ...] = (*MERGEABLE_SURFACES, "other")

_Vec3 = tuple[float, float, float]


def _unit(vector: _Vec3) -> _Vec3:
    length = math.sqrt(sum(value * value for value in vector))
    if length == 0.0:
        return (0.0, 0.0, 0.0)
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def _canonical_dir(vector: _Vec3) -> _Vec3:
    """Unit direction with a deterministic sign, so a flipped axis compares equal."""

    direction = _unit(vector)
    for value in direction:
        if abs(value) > 1e-9:
            if value < 0.0:
                return (-direction[0], -direction[1], -direction[2])
            return direction
    return direction


def _xyz(point: Any) -> _Vec3:
    """Coordinates of any gp point or direction as a plain tuple."""

    return (float(point.X()), float(point.Y()), float(point.Z()))


def _dot(a: _Vec3, b: _Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a: _Vec3, b: _Vec3) -> _Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _length(vector: _Vec3) -> float:
    return math.sqrt(_dot(vector, vector))


def _same_direction(a: _Vec3, b: _Vec3) -> bool:
    """True when two directions are parallel to within the merge angle, sign ignored."""

    cosine = min(1.0, abs(_dot(_unit(a), _unit(b))))
    return math.degrees(math.acos(cosine)) <= _MERGE_ANGLE_TOLERANCE_DEG


def _foot_on_axis(point: _Vec3, direction: _Vec3) -> _Vec3:
    """Point of the line through ``point`` along ``direction`` that is nearest the origin."""

    unit_dir = _unit(direction)
    along = _dot(point, unit_dir)
    return (
        point[0] - along * unit_dir[0],
        point[1] - along * unit_dir[1],
        point[2] - along * unit_dir[2],
    )


def _distance_to_axis(point: _Vec3, axis_point: _Vec3, axis_dir: _Vec3) -> float:
    relative = _sub(point, axis_point)
    unit_dir = _unit(axis_dir)
    along = _dot(relative, unit_dir)
    return _length(
        (
            relative[0] - along * unit_dir[0],
            relative[1] - along * unit_dir[1],
            relative[2] - along * unit_dir[2],
        )
    )


def _same_radius(a: float, b: float, tolerance: float) -> bool:
    """Radii agree relatively; a shared absolute floor keeps near-zero radii comparable."""

    return abs(a - b) <= max(_MERGE_RADIUS_FRACTION * max(abs(a), abs(b)), tolerance)


@dataclass(frozen=True, slots=True)
class _AnalyticSurface:
    """One face's carrier surface, reduced to the parameters that identify it."""

    kind: str
    #: Plane normal or axis of revolution, canonically signed.
    direction: _Vec3 = (0.0, 0.0, 0.0)
    #: Plane offset along ``direction``.
    offset: float = 0.0
    #: Cylinder axis foot nearest the origin, cone apex, or sphere/torus centre.
    point: _Vec3 = (0.0, 0.0, 0.0)
    #: Cylinder or sphere radius; torus major radius.
    radius: float = 0.0
    #: Torus minor radius.
    minor_radius: float = 0.0
    #: Cone half angle, in radians.
    half_angle: float = 0.0


def _analytic_surface(face: TopoDS_Face) -> _AnalyticSurface | None:
    """Return the carrier surface of ``face``, or ``None`` if its type never merges."""

    adaptor = BRepAdaptor_Surface(face)
    kind = _SURFACE_NAMES.get(adaptor.GetType(), "other")
    if kind == "plane":
        plane = adaptor.Plane()
        normal = _canonical_dir(_xyz(plane.Axis().Direction()))
        location = _xyz(plane.Axis().Location())
        return _AnalyticSurface("plane", direction=normal, offset=_dot(normal, location))
    if kind == "cylinder":
        cylinder = adaptor.Cylinder()
        axis = _canonical_dir(_xyz(cylinder.Axis().Direction()))
        return _AnalyticSurface(
            "cylinder",
            direction=axis,
            point=_foot_on_axis(_xyz(cylinder.Axis().Location()), axis),
            radius=float(cylinder.Radius()),
        )
    if kind == "cone":
        cone = adaptor.Cone()
        axis = _canonical_dir(_xyz(cone.Axis().Direction()))
        # The apex, the axis and the half angle pin the cone down completely; the
        # reference radius is not compared because it is measured at the surface's own
        # parameter origin, which two faces of one cone need not share.
        return _AnalyticSurface(
            "cone",
            direction=axis,
            point=_xyz(cone.Apex()),
            half_angle=abs(float(cone.SemiAngle())),
        )
    if kind == "sphere":
        sphere = adaptor.Sphere()
        return _AnalyticSurface(
            "sphere",
            point=_xyz(sphere.Location()),
            radius=float(sphere.Radius()),
        )
    if kind == "torus":
        torus = adaptor.Torus()
        return _AnalyticSurface(
            "torus",
            direction=_canonical_dir(_xyz(torus.Axis().Direction())),
            point=_xyz(torus.Location()),
            radius=float(torus.MajorRadius()),
            minor_radius=float(torus.MinorRadius()),
        )
    return None


def _same_analytic_surface(a: _AnalyticSurface, b: _AnalyticSurface, tolerance: float) -> bool:
    """True when two faces lie on one and the same analytic surface."""

    if a.kind != b.kind:
        return False
    if a.kind == "plane":
        if not _same_direction(a.direction, b.direction):
            return False
        # ``_canonical_dir`` can still pick opposite signs for normals that are parallel
        # only to within the angle tolerance, so compare the offsets in one frame.
        flip = 1.0 if _dot(a.direction, b.direction) >= 0.0 else -1.0
        return abs(a.offset - flip * b.offset) <= tolerance
    if a.kind == "cylinder":
        return (
            _same_direction(a.direction, b.direction)
            and _distance_to_axis(b.point, a.point, a.direction) <= tolerance
            and _same_radius(a.radius, b.radius, tolerance)
        )
    if a.kind == "cone":
        return (
            _same_direction(a.direction, b.direction)
            and _distance_to_axis(b.point, a.point, a.direction) <= tolerance
            and _length(_sub(a.point, b.point)) <= tolerance
            and math.degrees(abs(a.half_angle - b.half_angle)) <= _MERGE_ANGLE_TOLERANCE_DEG
        )
    if a.kind == "sphere":
        return _length(_sub(a.point, b.point)) <= tolerance and _same_radius(
            a.radius, b.radius, tolerance
        )
    if a.kind == "torus":
        return (
            _same_direction(a.direction, b.direction)
            and _length(_sub(a.point, b.point)) <= tolerance
            and _same_radius(a.radius, b.radius, tolerance)
            and _same_radius(a.minor_radius, b.minor_radius, tolerance)
        )
    return False


def _bbox_diagonal(shape: TopoDS_Shape) -> float:
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    box.SetGap(0.0)
    x_min, y_min, z_min, x_max, y_max, z_max = box.Get()
    return _length((x_max - x_min, y_max - y_min, z_max - z_min))


class _UnionFind:
    """Disjoint sets over face indices, with path compression."""

    __slots__ = ("_parent",)

    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, item: int) -> int:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a


def merged_surface_inventory(shape: TopoDS_Shape) -> dict[str, int]:
    """Count analytic surfaces rather than STEP faces.

    Exporters routinely split one geometric surface across several faces -- a bore
    emitted as two half cylinders, a plane cut in two by a boolean -- so a per-face
    inventory over-counts what a segmenter is expected to find. Adjacent faces (sharing
    at least one edge) that lie on the same carrier surface are unioned and each
    connected component counts once. Only faces sharing an edge merge, so two coplanar
    but disjoint pads stay two surfaces. Types with no analytic parameters (b-spline,
    Bezier, extrusion, revolution, offset) are counted per face under ``other``.
    """

    face_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_ShapeEnum.TopAbs_FACE, face_map)
    faces = [TopoDS.Face_s(face_map.FindKey(index)) for index in range(1, face_map.Extent() + 1)]
    surfaces = [_analytic_surface(face) for face in faces]
    tolerance = _MERGE_DISTANCE_FRACTION * _bbox_diagonal(shape) if faces else 0.0

    sets = _UnionFind(len(faces))
    edge_faces = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(
        shape, TopAbs_ShapeEnum.TopAbs_EDGE, TopAbs_ShapeEnum.TopAbs_FACE, edge_faces
    )
    for index in range(1, edge_faces.Extent() + 1):
        neighbours = sorted(
            {
                found - 1
                for found in (face_map.FindIndex(face) for face in edge_faces.FindFromIndex(index))
                if found > 0
            }
        )
        for left, right in itertools.combinations(neighbours, 2):
            a, b = surfaces[left], surfaces[right]
            if a is not None and b is not None and _same_analytic_surface(a, b, tolerance):
                sets.union(left, right)

    counts = dict.fromkeys(MERGED_INVENTORY_KEYS, 0)
    seen: set[int] = set()
    for index, surface in enumerate(surfaces):
        if surface is None:
            counts["other"] += 1
            continue
        root = sets.find(index)
        if root in seen:
            continue
        seen.add(root)
        counts[surface.kind] += 1
    return counts


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
    for face in faces:
        name = _surface_name(face)
        inventory[name] = inventory.get(name, 0) + 1
    hole_count = count_holes(faces)

    return {
        "step": path.name,
        "sha256": sha256_file(path),
        "solidCount": len(_sub_shapes(shape, TopAbs_ShapeEnum.TopAbs_SOLID)),
        "faceCount": len(faces),
        "edgeCount": len(_sub_shapes(shape, TopAbs_ShapeEnum.TopAbs_EDGE)),
        "vertexCount": len(_sub_shapes(shape, TopAbs_ShapeEnum.TopAbs_VERTEX)),
        "surfaceInventory": dict(sorted(inventory.items())),
        "surfaceInventoryMerged": merged_surface_inventory(shape),
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
