"""Deterministic plane/cylinder segmentation and reversible patch editing.

The supported automatic scope is intentionally narrow: connected, sharp-edged,
plane- and full-cylinder-dominant mechanical meshes.  Poor fits remain freeform;
the engine does not relabel them optimistically.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np
import trimesh
from scipy.optimize import least_squares

PatchKind = Literal["plane", "cylinder", "freeform", "unknown"]


@dataclass(frozen=True, slots=True)
class ResidualStats:
    rms: float
    median: float
    p95: float
    maximum: float

    def to_dict(self) -> dict[str, float]:
        return {
            "rms": self.rms,
            "median": self.median,
            "p95": self.p95,
            "max": self.maximum,
        }


@dataclass(frozen=True, slots=True)
class BoundaryLoop:
    vertex_ids: tuple[int, ...]
    closed: bool


@dataclass(frozen=True, slots=True)
class SurfacePatch:
    id: str
    kind: PatchKind
    triangle_ids: tuple[int, ...]
    vertex_ids: tuple[int, ...]
    area_mm2: float
    centroid: tuple[float, float, float]
    residuals_mm: ResidualStats
    confidence: float
    neighbor_ids: tuple[str, ...] = ()
    boundary_loops: tuple[BoundaryLoop, ...] = ()
    plane_origin: tuple[float, float, float] | None = None
    plane_normal: tuple[float, float, float] | None = None
    cylinder_axis_point: tuple[float, float, float] | None = None
    cylinder_axis: tuple[float, float, float] | None = None
    cylinder_radius_mm: float | None = None
    angular_coverage_deg: float | None = None
    user_overridden: bool = False
    locked: bool = False
    excluded_triangle_ids: tuple[int, ...] = ()

    def to_dict(self, *, include_triangle_ids: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "type": self.kind,
            "triangleCount": len(self.triangle_ids),
            "vertexCount": len(self.vertex_ids),
            "areaMm2": self.area_mm2,
            "centroid": list(self.centroid),
            "residualsMm": self.residuals_mm.to_dict(),
            "confidence": self.confidence,
            "neighborIds": list(self.neighbor_ids),
            "boundaryLoops": [
                {"vertexIds": list(loop.vertex_ids), "closed": loop.closed}
                for loop in self.boundary_loops
            ],
            "userOverriddenClassification": self.user_overridden,
            "locked": self.locked,
            "excludedTriangleIds": list(self.excluded_triangle_ids),
        }
        if include_triangle_ids:
            result["triangleIds"] = list(self.triangle_ids)
        if self.kind == "plane":
            result["fit"] = {
                "origin": list(self.plane_origin or ()),
                "normal": list(self.plane_normal or ()),
            }
        elif self.kind == "cylinder":
            result["fit"] = {
                "axisPoint": list(self.cylinder_axis_point or ()),
                "axis": list(self.cylinder_axis or ()),
                "radiusMm": self.cylinder_radius_mm,
                "angularCoverageDeg": self.angular_coverage_deg,
            }
        return result


@dataclass(frozen=True, slots=True)
class SegmentationSettings:
    smooth_angle_deg: float = 12.0
    planar_fit_tolerance_mm: float = 0.005
    cylinder_fit_tolerance_mm: float = 0.01
    minimum_cylinder_coverage_deg: float = 300.0
    maximum_cylinder_axis_normal_component: float = 0.05
    minimum_patch_area_mm2: float = 1e-8
    stable_id_resolution_mm: float = 1e-5

    def validate(self) -> None:
        if not 0 < self.smooth_angle_deg < 90:
            raise ValueError("smooth angle must be between 0 and 90 degrees")
        if self.planar_fit_tolerance_mm <= 0 or self.cylinder_fit_tolerance_mm <= 0:
            raise ValueError("fit tolerances must be positive")
        if not 0 < self.minimum_cylinder_coverage_deg <= 360:
            raise ValueError("minimum cylinder coverage must be in (0, 360]")


@dataclass(frozen=True, slots=True)
class SegmentationResult:
    patches: tuple[SurfacePatch, ...]
    settings: SegmentationSettings
    warnings: tuple[str, ...]

    @property
    def counts_by_type(self) -> dict[str, int]:
        return {
            kind: sum(patch.kind == kind for patch in self.patches)
            for kind in ("plane", "cylinder", "freeform", "unknown")
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "settings": {
                "smoothAngleDeg": self.settings.smooth_angle_deg,
                "planarFitToleranceMm": self.settings.planar_fit_tolerance_mm,
                "cylinderFitToleranceMm": self.settings.cylinder_fit_tolerance_mm,
                "minimumCylinderCoverageDeg": self.settings.minimum_cylinder_coverage_deg,
                "maximumCylinderAxisNormalComponent": (
                    self.settings.maximum_cylinder_axis_normal_component
                ),
                "minimumPatchAreaMm2": self.settings.minimum_patch_area_mm2,
                "stableIdResolutionMm": self.settings.stable_id_resolution_mm,
            },
            "countsByType": self.counts_by_type,
            "warnings": list(self.warnings),
            "patches": [patch.to_dict() for patch in self.patches],
        }


class _UnionFind:
    def __init__(self, count: int):
        self.parent = np.arange(count, dtype=np.int64)
        self.rank = np.zeros(count, dtype=np.int8)

    def find(self, item: int) -> int:
        root = item
        while self.parent[root] != root:
            root = int(self.parent[root])
        while self.parent[item] != item:
            following = int(self.parent[item])
            self.parent[item] = root
            item = following
        return root

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1


def _tuple3(value: np.ndarray) -> tuple[float, float, float]:
    return float(value[0]), float(value[1]), float(value[2])


def _canonical_direction(direction: np.ndarray) -> np.ndarray:
    normalized = np.asarray(direction, dtype=np.float64)
    magnitude = float(np.linalg.norm(normalized))
    if magnitude <= 1e-15:
        raise ValueError("cannot normalize a zero direction")
    normalized = normalized / magnitude
    dominant = int(np.argmax(np.abs(normalized)))
    return -normalized if normalized[dominant] < 0 else normalized


def _orthogonal_basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    trial = np.asarray((1.0, 0.0, 0.0)) if abs(axis[0]) < 0.8 else np.asarray((0.0, 1.0, 0.0))
    first = np.cross(axis, trial)
    first /= np.linalg.norm(first)
    return first, np.asarray(np.cross(axis, first))


def _residual_stats(values: np.ndarray) -> ResidualStats:
    absolute = np.abs(np.asarray(values, dtype=np.float64))
    if len(absolute) == 0:
        return ResidualStats(math.inf, math.inf, math.inf, math.inf)
    return ResidualStats(
        rms=float(np.sqrt(np.mean(absolute * absolute))),
        median=float(np.median(absolute)),
        p95=float(np.quantile(absolute, 0.95)),
        maximum=float(np.max(absolute)),
    )


def _fit_circle_2d(points: np.ndarray) -> tuple[np.ndarray, float, ResidualStats, float]:
    x_values, y_values = points[:, 0], points[:, 1]
    design = np.column_stack((2 * x_values, 2 * y_values, np.ones(len(points))))
    target = x_values * x_values + y_values * y_values
    x_center, y_center, constant = np.linalg.lstsq(design, target, rcond=None)[0]
    radius = math.sqrt(max(float(constant + x_center * x_center + y_center * y_center), 0.0))

    def residual(parameters: np.ndarray) -> np.ndarray:
        center_x, center_y, candidate_radius = parameters
        return np.asarray(np.hypot(x_values - center_x, y_values - center_y) - candidate_radius)

    optimized = least_squares(
        residual,
        np.asarray((x_center, y_center, radius)),
        method="trf",
        ftol=1e-13,
        xtol=1e-13,
        gtol=1e-13,
    )
    x_center, y_center, radius = (float(value) for value in optimized.x)
    stats = _residual_stats(residual(optimized.x))
    angles = np.mod(np.arctan2(y_values - y_center, x_values - x_center), 2 * np.pi)
    sorted_angles = np.sort(angles)
    if len(sorted_angles) < 2:
        coverage = 0.0
    else:
        gaps = np.diff(np.concatenate((sorted_angles, sorted_angles[:1] + 2 * np.pi)))
        coverage = math.degrees(2 * np.pi - float(np.max(gaps)))
    return np.asarray((x_center, y_center)), radius, stats, coverage


def _patch_id(patch: SurfacePatch, resolution: float) -> str:
    def quantize(values: tuple[float, ...] | None) -> list[int] | None:
        if values is None:
            return None
        return [round(value / resolution) for value in values]

    identity = {
        "kind": patch.kind,
        "centroid": quantize(patch.centroid),
        "area": round(patch.area_mm2 / max(resolution * resolution, 1e-12)),
        "planeNormal": quantize(patch.plane_normal),
        "axisPoint": quantize(patch.cylinder_axis_point),
        "axis": quantize(patch.cylinder_axis),
        "radius": (
            round(patch.cylinder_radius_mm / resolution)
            if patch.cylinder_radius_mm is not None
            else None
        ),
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:12]
    return f"patch.{patch.kind}.{digest}"


def fit_surface_patch(
    mesh: trimesh.Trimesh,
    face_ids: np.ndarray,
    settings: SegmentationSettings,
) -> SurfacePatch:
    """Fit exactly one supported analytic surface or return a freeform patch."""

    settings.validate()
    face_ids = np.unique(np.asarray(face_ids, dtype=np.int64))
    if len(face_ids) == 0 or np.any(face_ids < 0) or np.any(face_ids >= len(mesh.faces)):
        raise ValueError("patch face IDs are empty or out of range")
    face_areas = np.asarray(mesh.area_faces, dtype=np.float64)[face_ids]
    area = float(np.sum(face_areas))
    if area <= 0:
        raise ValueError("patch area must be positive")
    below_minimum_area = area < settings.minimum_patch_area_mm2
    face_normals = np.asarray(mesh.face_normals, dtype=np.float64)[face_ids]
    face_centers = np.asarray(mesh.triangles_center, dtype=np.float64)[face_ids]
    vertex_ids = np.unique(np.asarray(mesh.faces, dtype=np.int64)[face_ids].reshape(-1))
    points = np.asarray(mesh.vertices, dtype=np.float64)[vertex_ids]
    centroid = np.average(face_centers, axis=0, weights=face_areas)

    centered = points - np.mean(points, axis=0)
    _, _, right_vectors = np.linalg.svd(centered, full_matrices=False)
    plane_normal = right_vectors[-1]
    mean_normal = np.average(face_normals, axis=0, weights=face_areas)
    if float(np.dot(plane_normal, mean_normal)) < 0:
        plane_normal = -plane_normal
    plane_residuals = (points - centroid) @ plane_normal
    plane_stats = _residual_stats(plane_residuals)
    triangle_id_tuple = tuple(int(value) for value in face_ids)
    vertex_id_tuple = tuple(int(value) for value in vertex_ids)
    centroid_tuple = _tuple3(centroid)
    if not below_minimum_area and plane_stats.p95 <= settings.planar_fit_tolerance_mm:
        confidence = max(0.0, 1.0 - plane_stats.p95 / settings.planar_fit_tolerance_mm)
        patch = SurfacePatch(
            id="",
            kind="plane",
            triangle_ids=triangle_id_tuple,
            vertex_ids=vertex_id_tuple,
            area_mm2=area,
            centroid=centroid_tuple,
            residuals_mm=plane_stats,
            confidence=confidence,
            plane_origin=_tuple3(centroid),
            plane_normal=_tuple3(plane_normal / np.linalg.norm(plane_normal)),
        )
        return replace(patch, id=_patch_id(patch, settings.stable_id_resolution_mm))

    normal_matrix = (face_normals * face_areas[:, None]).T @ face_normals
    _, eigenvectors = np.linalg.eigh(normal_matrix)
    cylinder_axis = _canonical_direction(eigenvectors[:, 0])
    basis_u, basis_v = _orthogonal_basis(cylinder_axis)
    projected = np.column_stack((points @ basis_u, points @ basis_v))
    center_2d, radius, cylinder_stats, coverage = _fit_circle_2d(projected)
    axial = points @ cylinder_axis
    axis_point = (
        basis_u * center_2d[0] + basis_v * center_2d[1] + cylinder_axis * float(np.mean(axial))
    )
    axial_normal_p95 = float(np.quantile(np.abs(face_normals @ cylinder_axis), 0.95))
    if (
        not below_minimum_area
        and cylinder_stats.p95 <= settings.cylinder_fit_tolerance_mm
        and coverage >= settings.minimum_cylinder_coverage_deg
        and axial_normal_p95 <= settings.maximum_cylinder_axis_normal_component
    ):
        confidence = max(0.0, 1.0 - cylinder_stats.p95 / settings.cylinder_fit_tolerance_mm)
        patch = SurfacePatch(
            id="",
            kind="cylinder",
            triangle_ids=triangle_id_tuple,
            vertex_ids=vertex_id_tuple,
            area_mm2=area,
            centroid=centroid_tuple,
            residuals_mm=cylinder_stats,
            confidence=confidence,
            cylinder_axis_point=_tuple3(axis_point),
            cylinder_axis=_tuple3(cylinder_axis),
            cylinder_radius_mm=radius,
            angular_coverage_deg=coverage,
        )
        return replace(patch, id=_patch_id(patch, settings.stable_id_resolution_mm))

    freeform_stats = ResidualStats(
        rms=min(plane_stats.rms, cylinder_stats.rms),
        median=min(plane_stats.median, cylinder_stats.median),
        p95=min(plane_stats.p95, cylinder_stats.p95),
        maximum=min(plane_stats.maximum, cylinder_stats.maximum),
    )
    patch = SurfacePatch(
        id="",
        kind="freeform",
        triangle_ids=triangle_id_tuple,
        vertex_ids=vertex_id_tuple,
        area_mm2=area,
        centroid=centroid_tuple,
        residuals_mm=freeform_stats,
        confidence=0.0,
    )
    return replace(patch, id=_patch_id(patch, settings.stable_id_resolution_mm))


def _smooth_regions(mesh: trimesh.Trimesh, threshold_deg: float) -> tuple[np.ndarray, ...]:
    union = _UnionFind(len(mesh.faces))
    cosine = math.cos(math.radians(threshold_deg))
    normals = np.asarray(mesh.face_normals, dtype=np.float64)
    for left, right in np.asarray(mesh.face_adjacency, dtype=np.int64):
        if float(np.dot(normals[left], normals[right])) >= cosine:
            union.union(int(left), int(right))
    groups: dict[int, list[int]] = {}
    for face_id in range(len(mesh.faces)):
        groups.setdefault(union.find(face_id), []).append(face_id)
    return tuple(
        np.asarray(group, dtype=np.int64)
        for _, group in sorted(groups.items(), key=lambda item: min(item[1]))
    )


def _boundary_loops(mesh: trimesh.Trimesh, face_ids: tuple[int, ...]) -> tuple[BoundaryLoop, ...]:
    edge_counts: dict[tuple[int, int], int] = {}
    for face in np.asarray(mesh.faces, dtype=np.int64)[list(face_ids)]:
        for left, right in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = int(min(left, right)), int(max(left, right))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    unused = {edge for edge, count in edge_counts.items() if count == 1}
    adjacency: dict[int, set[int]] = {}
    for left, right in unused:
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    if not unused:
        return ()
    if any(len(neighbors) != 2 for neighbors in adjacency.values()):
        open_vertices = tuple(sorted(adjacency))
        return (BoundaryLoop(open_vertices, False),)
    loops: list[BoundaryLoop] = []
    while unused:
        first_edge = min(unused)
        start = min(first_edge)
        current, previous = start, -1
        loop = [start]
        while True:
            choices = sorted(value for value in adjacency[current] if value != previous)
            if not choices:
                loops.append(BoundaryLoop(tuple(loop), False))
                break
            following = choices[0]
            edge = min(current, following), max(current, following)
            if edge not in unused and following != start:
                loops.append(BoundaryLoop(tuple(loop), False))
                break
            unused.discard(edge)
            if following == start:
                loops.append(BoundaryLoop(tuple(loop), True))
                break
            loop.append(following)
            previous, current = current, following
            if len(loop) > len(adjacency) + 1:
                loops.append(BoundaryLoop(tuple(loop), False))
                break
    mesh_vertices = np.asarray(mesh.vertices, dtype=np.float64)

    def loop_sort_key(loop: BoundaryLoop) -> tuple[bool, tuple[float, float, float], int]:
        center = np.asarray(
            np.round(np.mean(mesh_vertices[list(loop.vertex_ids)], axis=0), 6),
            dtype=np.float64,
        )
        return not loop.closed, _tuple3(center), len(loop.vertex_ids)

    return tuple(
        sorted(
            loops,
            key=loop_sort_key,
        )
    )


def segment_mesh(
    mesh: trimesh.Trimesh,
    settings: SegmentationSettings | None = None,
) -> SegmentationResult:
    settings = settings or SegmentationSettings()
    settings.validate()
    if len(mesh.faces) == 0 or len(mesh.vertices) == 0:
        raise ValueError("cannot segment an empty mesh")
    if not np.all(np.isfinite(mesh.vertices)):
        raise ValueError("cannot segment non-finite vertices")
    patches = [
        fit_surface_patch(mesh, region, settings)
        for region in _smooth_regions(mesh, settings.smooth_angle_deg)
    ]
    patches.sort(key=lambda patch: patch.id)
    face_to_patch: dict[int, str] = {
        face_id: patch.id for patch in patches for face_id in patch.triangle_ids
    }
    neighbors: dict[str, set[str]] = {patch.id: set() for patch in patches}
    for left, right in np.asarray(mesh.face_adjacency, dtype=np.int64):
        left_id, right_id = face_to_patch[int(left)], face_to_patch[int(right)]
        if left_id != right_id:
            neighbors[left_id].add(right_id)
            neighbors[right_id].add(left_id)
    patches = [
        replace(
            patch,
            neighbor_ids=tuple(sorted(neighbors[patch.id])),
            boundary_loops=_boundary_loops(mesh, patch.triangle_ids),
        )
        for patch in patches
    ]
    warnings = []
    if any(not loop.closed for patch in patches for loop in patch.boundary_loops):
        warnings.append(
            "one or more patch boundaries are open; downstream loop inference is partial"
        )
    if any(patch.kind == "freeform" for patch in patches):
        warnings.append("freeform remainder preserved; automatic feature inference is partial")
    return SegmentationResult(tuple(patches), settings, tuple(warnings))


@dataclass(frozen=True, slots=True)
class PatchEditRecord:
    operation: str
    patch_ids: tuple[str, ...]
    before: tuple[SurfacePatch, ...]
    after: tuple[SurfacePatch, ...]
    success: bool
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "patchIds": list(self.patch_ids),
            "before": [patch.to_dict() for patch in self.before],
            "after": [patch.to_dict() for patch in self.after],
            "success": self.success,
            "warning": self.warning,
        }


class PatchEditSession:
    """Small edit contract that preserves the prior patch set on failed edits."""

    def __init__(self, mesh: trimesh.Trimesh, segmentation: SegmentationResult):
        self.mesh = mesh.copy()
        self.settings = segmentation.settings
        self.patches: dict[str, SurfacePatch] = {patch.id: patch for patch in segmentation.patches}
        self.history: list[PatchEditRecord] = []

    def _require(self, patch_id: str) -> SurfacePatch:
        try:
            return self.patches[patch_id]
        except KeyError as exc:
            raise KeyError(f"unknown patch {patch_id!r}") from exc

    def lock(self, patch_id: str, locked: bool = True) -> PatchEditRecord:
        previous = self._require(patch_id)
        updated = replace(previous, locked=locked)
        self.patches.pop(patch_id)
        self.patches[updated.id] = updated
        record = PatchEditRecord("lock", (patch_id,), (previous,), (updated,), True)
        self.history.append(record)
        return record

    def reclassify(self, patch_id: str, kind: PatchKind) -> PatchEditRecord:
        previous = self._require(patch_id)
        if previous.locked:
            record = PatchEditRecord(
                "reclassify", (patch_id,), (previous,), (previous,), False, "patch is locked"
            )
            self.history.append(record)
            return record
        if kind in {"plane", "cylinder"}:
            fitted = fit_surface_patch(self.mesh, np.asarray(previous.triangle_ids), self.settings)
            if fitted.kind != kind:
                record = PatchEditRecord(
                    "reclassify",
                    (patch_id,),
                    (previous,),
                    (previous,),
                    False,
                    f"triangles do not satisfy the {kind} fit tolerance",
                )
                self.history.append(record)
                return record
            updated = replace(
                fitted,
                user_overridden=True,
                neighbor_ids=previous.neighbor_ids,
                boundary_loops=previous.boundary_loops,
            )
        else:
            updated = replace(previous, kind=kind, user_overridden=True)
        self.patches.pop(patch_id)
        self.patches[updated.id] = updated
        record = PatchEditRecord("reclassify", (patch_id,), (previous,), (updated,), True)
        self.history.append(record)
        return record

    def refit(self, patch_id: str) -> PatchEditRecord:
        previous = self._require(patch_id)
        if previous.locked:
            record = PatchEditRecord(
                "refit", (patch_id,), (previous,), (previous,), False, "patch is locked"
            )
            self.history.append(record)
            return record
        fitted = fit_surface_patch(self.mesh, np.asarray(previous.triangle_ids), self.settings)
        updated = replace(
            fitted, neighbor_ids=previous.neighbor_ids, boundary_loops=previous.boundary_loops
        )
        self.patches.pop(patch_id)
        self.patches[updated.id] = updated
        record = PatchEditRecord("refit", (patch_id,), (previous,), (updated,), True)
        self.history.append(record)
        return record

    def exclude_triangles(self, patch_id: str, triangle_ids: set[int]) -> PatchEditRecord:
        previous = self._require(patch_id)
        if previous.locked:
            record = PatchEditRecord(
                "exclude", (patch_id,), (previous,), (previous,), False, "patch is locked"
            )
            self.history.append(record)
            return record
        remaining = tuple(value for value in previous.triangle_ids if value not in triangle_ids)
        if len(remaining) < 2:
            record = PatchEditRecord(
                "exclude", (patch_id,), (previous,), (previous,), False, "too few triangles remain"
            )
            self.history.append(record)
            return record
        fitted = fit_surface_patch(self.mesh, np.asarray(remaining), self.settings)
        updated = replace(
            fitted,
            neighbor_ids=previous.neighbor_ids,
            excluded_triangle_ids=tuple(sorted(set(previous.excluded_triangle_ids) | triangle_ids)),
        )
        self.patches.pop(patch_id)
        self.patches[updated.id] = updated
        record = PatchEditRecord("exclude", (patch_id,), (previous,), (updated,), True)
        self.history.append(record)
        return record

    def merge(self, left_id: str, right_id: str) -> PatchEditRecord:
        left, right = self._require(left_id), self._require(right_id)
        before = (left, right)
        if left.locked or right.locked:
            record = PatchEditRecord(
                "merge",
                (left_id, right_id),
                before,
                before,
                False,
                "one or both patches are locked",
            )
            self.history.append(record)
            return record
        if left.kind != right.kind or left.kind not in {"plane", "cylinder"}:
            record = PatchEditRecord(
                "merge", (left_id, right_id), before, before, False, "patch types are incompatible"
            )
            self.history.append(record)
            return record
        try:
            fitted = fit_surface_patch(
                self.mesh,
                np.asarray(sorted(set(left.triangle_ids) | set(right.triangle_ids))),
                self.settings,
            )
        except ValueError as exc:
            record = PatchEditRecord("merge", (left_id, right_id), before, before, False, str(exc))
            self.history.append(record)
            return record
        if fitted.kind != left.kind:
            record = PatchEditRecord(
                "merge",
                (left_id, right_id),
                before,
                before,
                False,
                "merged fit exceeds compatibility tolerance",
            )
            self.history.append(record)
            return record
        updated = replace(
            fitted,
            neighbor_ids=tuple(
                sorted((set(left.neighbor_ids) | set(right.neighbor_ids)) - {left_id, right_id})
            ),
            user_overridden=True,
        )
        self.patches.pop(left_id)
        self.patches.pop(right_id)
        self.patches[updated.id] = updated
        record = PatchEditRecord("merge", (left_id, right_id), before, (updated,), True)
        self.history.append(record)
        return record


__all__ = [
    "BoundaryLoop",
    "PatchEditRecord",
    "PatchEditSession",
    "PatchKind",
    "ResidualStats",
    "SegmentationResult",
    "SegmentationSettings",
    "SurfacePatch",
    "fit_surface_patch",
    "segment_mesh",
]
