"""Shared-topology surface networks for curved reconstruction (Milestone 2).

A surface network is the explicit, content-addressed record of a fitted patch
layout: shared vertices, shared boundary B-spline curves with declared
continuity intent, and tensor-product patches whose boundary pole rows equal
the shared curve poles exactly. Faces are built on common OCCT edges with
exact iso-line pcurves -- G0 is by construction, never by healing -- and the
whole network serializes to a canonical JSON artifact whose SHA-256 identifies
the geometry. Rebuilding from the artifact reproduces the same shape.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeEdge,
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakeVertex,
    BRepBuilderAPI_MakeWire,
)
from OCP.Geom import Geom_BSplineCurve
from OCP.Geom2d import Geom2d_Line
from OCP.gp import gp_Dir2d, gp_Pnt, gp_Pnt2d, gp_Vec
from OCP.TColgp import TColgp_Array1OfPnt
from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Edge, TopoDS_Face, TopoDS_Vertex

from .surface_fit import build_occt_bspline_surface

IsoSide = Literal["u0", "u1", "v0", "v1"]
CurveContinuity = Literal["crease", "smooth"]

ARTIFACT_SCHEMA = "mesh2param/surface-network/1"


class SurfaceNetworkError(ValueError):
    """A fail-closed surface-network construction error with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class NetworkVertex:
    id: str
    point: np.ndarray = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "point": [float(value) for value in self.point]}


@dataclass(frozen=True, slots=True)
class NetworkCurve:
    """One shared boundary curve, fitted once and referenced by both sides."""

    id: str
    degree: int
    knots: np.ndarray = field(repr=False)
    poles: np.ndarray = field(repr=False)
    start_vertex_id: str
    end_vertex_id: str
    continuity: CurveContinuity

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "degree": self.degree,
            "knots": [float(value) for value in self.knots],
            "poles": [[float(value) for value in pole] for pole in self.poles],
            "startVertexId": self.start_vertex_id,
            "endVertexId": self.end_vertex_id,
            "continuity": self.continuity,
        }


@dataclass(frozen=True, slots=True)
class NetworkPatch:
    """A clamped tensor-product patch and its shared-boundary attachments."""

    id: str
    degree: int
    knots_u: np.ndarray = field(repr=False)
    knots_v: np.ndarray = field(repr=False)
    poles: np.ndarray = field(repr=False)
    # Corner vertex ids at uv (0,0), (1,0), (1,1), (0,1).
    corner_vertex_ids: tuple[str, str, str, str]
    # Iso side -> shared curve id, for boundaries owned by the network.
    shared_boundaries: dict[IsoSide, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "degree": self.degree,
            "knotsU": [float(value) for value in self.knots_u],
            "knotsV": [float(value) for value in self.knots_v],
            "poles": [[[float(value) for value in pole] for pole in row] for row in self.poles],
            "cornerVertexIds": list(self.corner_vertex_ids),
            "sharedBoundaries": {
                iso: self.shared_boundaries[iso] for iso in sorted(self.shared_boundaries)
            },
        }

    def boundary_poles(self, iso: IsoSide) -> np.ndarray:
        if iso == "u0":
            return np.asarray(self.poles[0], dtype=np.float64)
        if iso == "u1":
            return np.asarray(self.poles[-1], dtype=np.float64)
        if iso == "v0":
            return np.asarray(self.poles[:, 0], dtype=np.float64)
        return np.asarray(self.poles[:, -1], dtype=np.float64)


@dataclass(frozen=True, slots=True)
class SurfaceNetwork:
    units: str
    vertices: tuple[NetworkVertex, ...]
    curves: tuple[NetworkCurve, ...]
    patches: tuple[NetworkPatch, ...]
    algorithm: str = ARTIFACT_SCHEMA

    def vertex(self, vertex_id: str) -> NetworkVertex:
        for vertex in self.vertices:
            if vertex.id == vertex_id:
                return vertex
        raise SurfaceNetworkError("network_missing_vertex", f"unknown vertex {vertex_id!r}")

    def curve(self, curve_id: str) -> NetworkCurve:
        for curve in self.curves:
            if curve.id == curve_id:
                return curve
        raise SurfaceNetworkError("network_missing_curve", f"unknown curve {curve_id!r}")

    def validate(self) -> None:
        vertex_ids = [vertex.id for vertex in self.vertices]
        curve_ids = [curve.id for curve in self.curves]
        patch_ids = [patch.id for patch in self.patches]
        for label, ids in (("vertex", vertex_ids), ("curve", curve_ids), ("patch", patch_ids)):
            if len(ids) != len(set(ids)):
                raise SurfaceNetworkError("network_duplicate_id", f"duplicate {label} id")
        for curve in self.curves:
            self.vertex(curve.start_vertex_id)
            self.vertex(curve.end_vertex_id)
            if len(curve.poles) != len(curve.knots) - curve.degree - 1:
                raise SurfaceNetworkError(
                    "network_curve_inconsistent",
                    f"curve {curve.id!r} pole count does not match its knots",
                )
        for patch in self.patches:
            for corner in patch.corner_vertex_ids:
                self.vertex(corner)
            for iso, curve_id in patch.shared_boundaries.items():
                curve = self.curve(curve_id)
                boundary = patch.boundary_poles(iso)
                if boundary.shape != curve.poles.shape or not np.allclose(
                    boundary, curve.poles, atol=1e-12
                ):
                    raise SurfaceNetworkError(
                        "network_boundary_mismatch",
                        (
                            f"patch {patch.id!r} iso {iso} poles do not equal shared "
                            f"curve {curve_id!r} poles"
                        ),
                    )

    def to_artifact(self) -> dict[str, Any]:
        return {
            "schema": ARTIFACT_SCHEMA,
            "units": self.units,
            "vertices": [vertex.to_dict() for vertex in self.vertices],
            "curves": [curve.to_dict() for curve in self.curves],
            "patches": [patch.to_dict() for patch in self.patches],
        }

    def artifact_bytes(self) -> bytes:
        return json.dumps(self.to_artifact(), sort_keys=True, separators=(",", ":")).encode("utf-8")

    def artifact_sha256(self) -> str:
        return hashlib.sha256(self.artifact_bytes()).hexdigest()

    @classmethod
    def from_artifact(cls, payload: dict[str, Any]) -> SurfaceNetwork:
        if payload.get("schema") != ARTIFACT_SCHEMA:
            raise SurfaceNetworkError(
                "network_unsupported_schema",
                f"unsupported surface-network schema {payload.get('schema')!r}",
            )
        vertices = tuple(
            NetworkVertex(id=item["id"], point=np.asarray(item["point"], dtype=np.float64))
            for item in payload["vertices"]
        )
        curves = tuple(
            NetworkCurve(
                id=item["id"],
                degree=int(item["degree"]),
                knots=np.asarray(item["knots"], dtype=np.float64),
                poles=np.asarray(item["poles"], dtype=np.float64),
                start_vertex_id=item["startVertexId"],
                end_vertex_id=item["endVertexId"],
                continuity=item["continuity"],
            )
            for item in payload["curves"]
        )
        patches = tuple(
            NetworkPatch(
                id=item["id"],
                degree=int(item["degree"]),
                knots_u=np.asarray(item["knotsU"], dtype=np.float64),
                knots_v=np.asarray(item["knotsV"], dtype=np.float64),
                poles=np.asarray(item["poles"], dtype=np.float64),
                corner_vertex_ids=(
                    item["cornerVertexIds"][0],
                    item["cornerVertexIds"][1],
                    item["cornerVertexIds"][2],
                    item["cornerVertexIds"][3],
                ),
                shared_boundaries=dict(item["sharedBoundaries"]),
            )
            for item in payload["patches"]
        )
        network = cls(units=payload["units"], vertices=vertices, curves=curves, patches=patches)
        network.validate()
        return network


def _occt_bspline_curve(poles: np.ndarray, knots: np.ndarray, degree: int) -> Geom_BSplineCurve:
    array = TColgp_Array1OfPnt(1, len(poles))
    for index, (x, y, z) in enumerate(poles, start=1):
        array.SetValue(index, gp_Pnt(float(x), float(y), float(z)))
    unique, counts = np.unique(np.round(knots, 12), return_counts=True)
    occt_knots = TColStd_Array1OfReal(1, len(unique))
    occt_mults = TColStd_Array1OfInteger(1, len(unique))
    for index, (value, count) in enumerate(zip(unique, counts, strict=True), start=1):
        occt_knots.SetValue(index, float(value))
        occt_mults.SetValue(index, int(count))
    return Geom_BSplineCurve(array, occt_knots, occt_mults, degree)


_ISO_PCURVES: dict[IsoSide, tuple[tuple[float, float], tuple[float, float]]] = {
    "v0": ((0.0, 0.0), (1.0, 0.0)),
    "u1": ((1.0, 0.0), (0.0, 1.0)),
    "v1": ((0.0, 1.0), (1.0, 0.0)),
    "u0": ((0.0, 0.0), (0.0, 1.0)),
}

# Wire traversal order around the uv square and each side's corner endpoints
# (start, end) in the corner tuple (0,0), (1,0), (1,1), (0,1).
_ISO_ORDER: tuple[tuple[IsoSide, int, int], ...] = (
    ("v0", 0, 1),
    ("u1", 1, 2),
    ("v1", 3, 2),
    ("u0", 0, 3),
)


def _iso_curve_poles(patch: NetworkPatch, iso: IsoSide) -> tuple[np.ndarray, np.ndarray]:
    if iso in ("v0", "v1"):
        return patch.boundary_poles(iso), np.asarray(patch.knots_u, dtype=np.float64)
    return patch.boundary_poles(iso), np.asarray(patch.knots_v, dtype=np.float64)


def build_network_faces(
    network: SurfaceNetwork, *, tolerance: float = 1e-9
) -> tuple[list[TopoDS_Face], dict[str, TopoDS_Edge]]:
    """Build every patch face on common vertices, edges, and exact pcurves.

    Shared boundary curves become one ``TopoDS_Edge`` reused by both adjacent
    faces; every edge's pcurve is the exact uv iso line, so the 3-D curve and
    pcurve agree with identical parameterization (SameParameter by
    construction, not by approximation).
    """

    network.validate()
    builder = BRep_Builder()
    occt_vertices: dict[str, TopoDS_Vertex] = {}
    for vertex in network.vertices:
        x, y, z = (float(value) for value in vertex.point)
        occt_vertices[vertex.id] = BRepBuilderAPI_MakeVertex(gp_Pnt(x, y, z)).Vertex()

    shared_edges: dict[str, TopoDS_Edge] = {}
    for curve in network.curves:
        geometry = _occt_bspline_curve(curve.poles, curve.knots, curve.degree)
        shared_edges[curve.id] = BRepBuilderAPI_MakeEdge(
            geometry,
            occt_vertices[curve.start_vertex_id],
            occt_vertices[curve.end_vertex_id],
        ).Edge()

    faces: list[TopoDS_Face] = []
    location = TopLoc_Location()
    for patch in network.patches:
        surface = build_occt_bspline_surface(
            np.asarray(patch.poles, dtype=np.float64),
            np.asarray(patch.knots_u, dtype=np.float64),
            np.asarray(patch.knots_v, dtype=np.float64),
            patch.degree,
        )
        wire_maker = BRepBuilderAPI_MakeWire()
        for iso, start_corner, end_corner in _ISO_ORDER:
            curve_id = patch.shared_boundaries.get(iso)
            if curve_id is not None:
                edge = shared_edges[curve_id]
            else:
                poles, knots = _iso_curve_poles(patch, iso)
                geometry = _occt_bspline_curve(poles, knots, patch.degree)
                edge = BRepBuilderAPI_MakeEdge(
                    geometry,
                    occt_vertices[patch.corner_vertex_ids[start_corner]],
                    occt_vertices[patch.corner_vertex_ids[end_corner]],
                ).Edge()
            (px, py), (dx, dy) = _ISO_PCURVES[iso]
            pcurve = Geom2d_Line(gp_Pnt2d(px, py), gp_Dir2d(dx, dy))
            builder.UpdateEdge(edge, pcurve, surface, location, float(tolerance))
            builder.SameParameter(edge, True)
            builder.SameRange(edge, True)
            wire_maker.Add(edge)
        if not wire_maker.IsDone():
            raise SurfaceNetworkError(
                "network_wire_failed", f"patch {patch.id!r} boundary wire did not close"
            )
        face_maker = BRepBuilderAPI_MakeFace(surface, wire_maker.Wire())
        if not face_maker.IsDone():
            raise SurfaceNetworkError(
                "network_face_failed", f"patch {patch.id!r} face construction failed"
            )
        faces.append(face_maker.Face())
    return faces, shared_edges


@dataclass(frozen=True, slots=True)
class SharedEdgeEvidence:
    curve_id: str
    continuity: CurveContinuity
    maximum_position_gap: float
    mean_normal_angle_deg: float
    p95_normal_angle_deg: float
    maximum_normal_angle_deg: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "curveId": self.curve_id,
            "continuity": self.continuity,
            "maximumPositionGap": self.maximum_position_gap,
            "meanNormalAngleDeg": self.mean_normal_angle_deg,
            "p95NormalAngleDeg": self.p95_normal_angle_deg,
            "maximumNormalAngleDeg": self.maximum_normal_angle_deg,
        }


def _patch_frame_along_iso(
    patch: NetworkPatch, iso: IsoSide, parameters: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Points and unit normals of the patch surface along one iso side."""

    surface = build_occt_bspline_surface(
        np.asarray(patch.poles, dtype=np.float64),
        np.asarray(patch.knots_u, dtype=np.float64),
        np.asarray(patch.knots_v, dtype=np.float64),
        patch.degree,
    )
    points = np.zeros((len(parameters), 3))
    normals = np.zeros((len(parameters), 3))
    for index, value in enumerate(parameters):
        if iso == "u0":
            u, v = 0.0, float(value)
        elif iso == "u1":
            u, v = 1.0, float(value)
        elif iso == "v0":
            u, v = float(value), 0.0
        else:
            u, v = float(value), 1.0
        point = gp_Pnt()
        du = gp_Vec()
        dv = gp_Vec()
        surface.D1(u, v, point, du, dv)
        normal = np.cross(
            [du.X(), du.Y(), du.Z()],
            [dv.X(), dv.Y(), dv.Z()],
        )
        length = float(np.linalg.norm(normal))
        points[index] = (point.X(), point.Y(), point.Z())
        normals[index] = normal / length if length > 0.0 else normal
    return points, normals


def shared_edge_evidence(
    network: SurfaceNetwork, *, sample_count: int = 64
) -> tuple[SharedEdgeEvidence, ...]:
    """G0 gap and G1 normal-angle statistics along every shared curve."""

    parameters = np.linspace(0.0, 1.0, sample_count)
    evidence: list[SharedEdgeEvidence] = []
    for curve in network.curves:
        sides: list[tuple[NetworkPatch, IsoSide]] = []
        for patch in network.patches:
            for iso, curve_id in sorted(patch.shared_boundaries.items()):
                if curve_id == curve.id:
                    sides.append((patch, iso))
        if len(sides) != 2:
            raise SurfaceNetworkError(
                "network_curve_adjacency",
                f"shared curve {curve.id!r} must bound exactly two patches, found {len(sides)}",
            )
        (patch_a, iso_a), (patch_b, iso_b) = sides
        points_a, normals_a = _patch_frame_along_iso(patch_a, iso_a, parameters)
        points_b, normals_b = _patch_frame_along_iso(patch_b, iso_b, parameters)
        gaps = np.linalg.norm(points_a - points_b, axis=1)
        cosine = np.clip(np.einsum("ij,ij->i", normals_a, normals_b), -1.0, 1.0)
        angles = np.degrees(np.arccos(np.abs(cosine)))
        evidence.append(
            SharedEdgeEvidence(
                curve_id=curve.id,
                continuity=curve.continuity,
                maximum_position_gap=float(gaps.max()),
                mean_normal_angle_deg=float(angles.mean()),
                p95_normal_angle_deg=float(np.percentile(angles, 95)),
                maximum_normal_angle_deg=float(angles.max()),
            )
        )
    return tuple(evidence)


__all__ = [
    "ARTIFACT_SCHEMA",
    "NetworkCurve",
    "NetworkPatch",
    "NetworkVertex",
    "SharedEdgeEvidence",
    "SurfaceNetwork",
    "SurfaceNetworkError",
    "build_network_faces",
    "shared_edge_evidence",
]
