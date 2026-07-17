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
from itertools import combinations
from typing import Any, Literal, get_args

import numpy as np
import trimesh
from scipy.optimize import least_squares

PatchKind = Literal["plane", "cylinder", "sphere", "cone", "torus", "freeform", "unknown"]
ANALYTIC_PATCH_KINDS: tuple[str, ...] = ("plane", "cylinder", "sphere", "cone", "torus")


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
    sphere_center: tuple[float, float, float] | None = None
    sphere_radius_mm: float | None = None
    cone_apex: tuple[float, float, float] | None = None
    cone_axis: tuple[float, float, float] | None = None
    cone_half_angle_deg: float | None = None
    torus_center: tuple[float, float, float] | None = None
    torus_axis: tuple[float, float, float] | None = None
    torus_major_radius_mm: float | None = None
    torus_minor_radius_mm: float | None = None
    recovered_from_facets: bool = False
    facet_sagitta_mm: float | None = None
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
                "recoveredFromFacets": self.recovered_from_facets,
                "facetSagittaMm": self.facet_sagitta_mm,
            }
        elif self.kind == "sphere":
            result["fit"] = {
                "center": list(self.sphere_center or ()),
                "radiusMm": self.sphere_radius_mm,
            }
        elif self.kind == "cone":
            result["fit"] = {
                "apex": list(self.cone_apex or ()),
                "axis": list(self.cone_axis or ()),
                "halfAngleDeg": self.cone_half_angle_deg,
                "angularCoverageDeg": self.angular_coverage_deg,
            }
        elif self.kind == "torus":
            result["fit"] = {
                "center": list(self.torus_center or ()),
                "axis": list(self.torus_axis or ()),
                "majorRadiusMm": self.torus_major_radius_mm,
                "minorRadiusMm": self.torus_minor_radius_mm,
                "angularCoverageDeg": self.angular_coverage_deg,
            }
        return result


@dataclass(frozen=True, slots=True)
class SegmentationSettings:
    smooth_angle_deg: float = 12.0
    planar_fit_tolerance_mm: float = 0.005
    cylinder_fit_tolerance_mm: float = 0.01
    sphere_fit_tolerance_mm: float = 0.01
    cone_fit_tolerance_mm: float = 0.01
    torus_fit_tolerance_mm: float = 0.01
    minimum_cylinder_coverage_deg: float = 300.0
    minimum_revolution_coverage_deg: float = 300.0
    minimum_cone_half_angle_deg: float = 5.0
    maximum_cone_half_angle_deg: float = 85.0
    maximum_cylinder_axis_normal_component: float = 0.05
    minimum_faceted_cylinder_side_count: int = 8
    maximum_faceted_cylinder_sagitta_mm: float = 0.1
    minimum_patch_area_mm2: float = 1e-8
    stable_id_resolution_mm: float = 1e-5

    def validate(self) -> None:
        if not 0 < self.smooth_angle_deg < 90:
            raise ValueError("smooth angle must be between 0 and 90 degrees")
        if (
            self.planar_fit_tolerance_mm <= 0
            or self.cylinder_fit_tolerance_mm <= 0
            or self.sphere_fit_tolerance_mm <= 0
            or self.cone_fit_tolerance_mm <= 0
            or self.torus_fit_tolerance_mm <= 0
        ):
            raise ValueError("fit tolerances must be positive")
        if not 0 < self.minimum_cylinder_coverage_deg <= 360:
            raise ValueError("minimum cylinder coverage must be in (0, 360]")
        if not 0 < self.minimum_revolution_coverage_deg <= 360:
            raise ValueError("minimum revolution coverage must be in (0, 360]")
        if not 0 < self.minimum_cone_half_angle_deg < self.maximum_cone_half_angle_deg < 90:
            raise ValueError("cone half-angle bounds must satisfy 0 < min < max < 90")
        if self.minimum_faceted_cylinder_side_count < 6:
            raise ValueError("minimum faceted-cylinder side count must be at least 6")
        if self.maximum_faceted_cylinder_sagitta_mm <= 0:
            raise ValueError("maximum faceted-cylinder sagitta must be positive")


@dataclass(frozen=True, slots=True)
class SegmentationResult:
    patches: tuple[SurfacePatch, ...]
    settings: SegmentationSettings
    warnings: tuple[str, ...]

    @property
    def counts_by_type(self) -> dict[str, int]:
        return {
            kind: sum(patch.kind == kind for patch in self.patches) for kind in get_args(PatchKind)
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "settings": {
                "smoothAngleDeg": self.settings.smooth_angle_deg,
                "planarFitToleranceMm": self.settings.planar_fit_tolerance_mm,
                "cylinderFitToleranceMm": self.settings.cylinder_fit_tolerance_mm,
                "sphereFitToleranceMm": self.settings.sphere_fit_tolerance_mm,
                "coneFitToleranceMm": self.settings.cone_fit_tolerance_mm,
                "torusFitToleranceMm": self.settings.torus_fit_tolerance_mm,
                "minimumRevolutionCoverageDeg": self.settings.minimum_revolution_coverage_deg,
                "minimumConeHalfAngleDeg": self.settings.minimum_cone_half_angle_deg,
                "maximumConeHalfAngleDeg": self.settings.maximum_cone_half_angle_deg,
                "minimumCylinderCoverageDeg": self.settings.minimum_cylinder_coverage_deg,
                "maximumCylinderAxisNormalComponent": (
                    self.settings.maximum_cylinder_axis_normal_component
                ),
                "minimumFacetedCylinderSideCount": (
                    self.settings.minimum_faceted_cylinder_side_count
                ),
                "maximumFacetedCylinderSagittaMm": (
                    self.settings.maximum_faceted_cylinder_sagitta_mm
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


def _fit_sphere(points: np.ndarray) -> tuple[np.ndarray, float, ResidualStats]:
    """Algebraic least-squares sphere: center, radius, and radial residuals."""

    design = np.column_stack((2.0 * points, np.ones(len(points))))
    target = np.einsum("ij,ij->i", points, points)
    solution = np.linalg.lstsq(design, target, rcond=None)[0]
    center = solution[:3]
    radius = math.sqrt(max(float(solution[3] + center @ center), 0.0))
    residuals = np.linalg.norm(points - center, axis=1) - radius
    return center, radius, _residual_stats(residuals)


def _fit_cone(
    points: np.ndarray,
    face_normals: np.ndarray,
    face_centers: np.ndarray,
    face_areas: np.ndarray,
    axis: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float, ResidualStats, float]:
    """Apex/axis/half-angle cone fit: apex, axis, angle (deg), residuals, coverage.

    Every tangent plane of a cone contains the apex, so the apex is the least
    squares solution of ``n . q = n . c`` over all sampled tangent planes
    (anchored at face centers); the half angle then comes from the
    radial-versus-axial slope of the points.
    """

    weights = np.sqrt(np.maximum(face_areas, 0.0))
    design = face_normals * weights[:, None]
    target = np.einsum("ij,ij->i", face_normals, face_centers) * weights
    apex = np.linalg.lstsq(design, target, rcond=None)[0]
    offsets = points - apex
    heights = offsets @ axis
    if float(np.mean(heights)) < 0.0:
        axis = -axis
        heights = -heights
    radial = np.linalg.norm(offsets - heights[:, None] * axis, axis=1)
    denominator = float(heights @ heights)
    if denominator <= 0.0:
        return apex, axis, 0.0, ResidualStats(math.inf, math.inf, math.inf, math.inf), 0.0
    slope = float((heights @ radial) / denominator)
    half_angle = math.atan(max(slope, 0.0))

    # Faceted normals are chord normals, which bias the linear apex estimate
    # by tens of microns; polish geometrically like the 2-D circle fit does.
    theta = math.acos(float(np.clip(axis[2], -1.0, 1.0)))
    phi = math.atan2(float(axis[1]), float(axis[0]))

    def cone_residual(parameters: np.ndarray) -> np.ndarray:
        candidate_apex = parameters[:3]
        candidate_theta, candidate_phi, candidate_alpha = parameters[3:]
        candidate_axis = np.asarray(
            (
                math.sin(candidate_theta) * math.cos(candidate_phi),
                math.sin(candidate_theta) * math.sin(candidate_phi),
                math.cos(candidate_theta),
            )
        )
        local = points - candidate_apex
        local_heights = local @ candidate_axis
        local_radial = np.linalg.norm(local - local_heights[:, None] * candidate_axis, axis=1)
        return np.asarray(
            local_radial * math.cos(candidate_alpha) - local_heights * math.sin(candidate_alpha)
        )

    optimized = least_squares(
        cone_residual,
        np.concatenate([apex, (theta, phi, half_angle)]),
        method="trf",
        ftol=1e-13,
        xtol=1e-13,
        gtol=1e-13,
    )
    apex = np.asarray(optimized.x[:3])
    theta, phi, half_angle = (float(value) for value in optimized.x[3:])
    axis = np.asarray(
        (math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), math.cos(theta))
    )
    offsets = points - apex
    heights = offsets @ axis
    if float(np.mean(heights)) < 0.0:
        axis = -axis
        heights = -heights
        half_angle = -half_angle
    half_angle = abs(half_angle)
    radial = np.linalg.norm(offsets - heights[:, None] * axis, axis=1)
    residuals = radial * math.cos(half_angle) - heights * math.sin(half_angle)
    basis_u, basis_v = _orthogonal_basis(axis)
    angles = np.mod(np.arctan2(offsets @ basis_v, offsets @ basis_u), 2 * np.pi)
    sorted_angles = np.sort(angles)
    gaps = np.diff(np.concatenate((sorted_angles, sorted_angles[:1] + 2 * np.pi)))
    coverage = math.degrees(2 * np.pi - float(np.max(gaps))) if len(angles) >= 2 else 0.0
    return apex, axis, math.degrees(half_angle), _residual_stats(residuals), coverage


def _fit_torus(
    points: np.ndarray,
    axis: np.ndarray,
    centroid: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float, float, ResidualStats, float]:
    """Axis-symmetric torus fit: center, axis, major/minor radii, residuals, coverage.

    In cylindrical coordinates around the symmetry axis the torus is the
    circle ``(rho - R)^2 + h^2 = r^2``, so the tube reduces to the existing
    deterministic 2-D circle fit.
    """

    offsets = points - centroid
    heights = offsets @ axis
    radial = np.linalg.norm(offsets - heights[:, None] * axis, axis=1)
    (rho_center, height_center), minor_radius, stats, tube_coverage = _fit_circle_2d(
        np.column_stack((radial, heights))
    )
    center = centroid + height_center * axis
    basis_u, basis_v = _orthogonal_basis(axis)
    angles = np.mod(np.arctan2(offsets @ basis_v, offsets @ basis_u), 2 * np.pi)
    sorted_angles = np.sort(angles)
    gaps = np.diff(np.concatenate((sorted_angles, sorted_angles[:1] + 2 * np.pi)))
    coverage = math.degrees(2 * np.pi - float(np.max(gaps))) if len(angles) >= 2 else 0.0
    coverage = min(coverage, tube_coverage)
    return center, axis, float(rho_center), float(minor_radius), stats, coverage


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

    cone_apex, cone_axis, cone_half_angle, cone_stats, cone_coverage = _fit_cone(
        points, face_normals, face_centers, face_areas, cylinder_axis
    )
    if (
        not below_minimum_area
        and cone_stats.p95 <= settings.cone_fit_tolerance_mm
        and cone_coverage >= settings.minimum_revolution_coverage_deg
        and settings.minimum_cone_half_angle_deg
        <= cone_half_angle
        <= settings.maximum_cone_half_angle_deg
    ):
        confidence = max(0.0, 1.0 - cone_stats.p95 / settings.cone_fit_tolerance_mm)
        patch = SurfacePatch(
            id="",
            kind="cone",
            triangle_ids=triangle_id_tuple,
            vertex_ids=vertex_id_tuple,
            area_mm2=area,
            centroid=centroid_tuple,
            residuals_mm=cone_stats,
            confidence=confidence,
            cone_apex=_tuple3(cone_apex),
            cone_axis=_tuple3(_canonical_direction(cone_axis)),
            cone_half_angle_deg=cone_half_angle,
            angular_coverage_deg=cone_coverage,
        )
        return replace(patch, id=_patch_id(patch, settings.stable_id_resolution_mm))

    sphere_center, sphere_radius, sphere_stats = _fit_sphere(points)
    if (
        not below_minimum_area
        and math.isfinite(sphere_radius)
        and sphere_radius > 0.0
        and sphere_stats.p95 <= settings.sphere_fit_tolerance_mm
    ):
        confidence = max(0.0, 1.0 - sphere_stats.p95 / settings.sphere_fit_tolerance_mm)
        patch = SurfacePatch(
            id="",
            kind="sphere",
            triangle_ids=triangle_id_tuple,
            vertex_ids=vertex_id_tuple,
            area_mm2=area,
            centroid=centroid_tuple,
            residuals_mm=sphere_stats,
            confidence=confidence,
            sphere_center=_tuple3(sphere_center),
            sphere_radius_mm=sphere_radius,
        )
        return replace(patch, id=_patch_id(patch, settings.stable_id_resolution_mm))

    (
        torus_center,
        torus_axis,
        torus_major,
        torus_minor,
        torus_stats,
        torus_coverage,
    ) = _fit_torus(points, plane_normal, centroid)
    if (
        not below_minimum_area
        and torus_stats.p95 <= settings.torus_fit_tolerance_mm
        and torus_coverage >= settings.minimum_revolution_coverage_deg
        and torus_major > torus_minor > 0.0
    ):
        confidence = max(0.0, 1.0 - torus_stats.p95 / settings.torus_fit_tolerance_mm)
        patch = SurfacePatch(
            id="",
            kind="torus",
            triangle_ids=triangle_id_tuple,
            vertex_ids=vertex_id_tuple,
            area_mm2=area,
            centroid=centroid_tuple,
            residuals_mm=torus_stats,
            confidence=confidence,
            torus_center=_tuple3(torus_center),
            torus_axis=_tuple3(_canonical_direction(torus_axis)),
            torus_major_radius_mm=torus_major,
            torus_minor_radius_mm=torus_minor,
            angular_coverage_deg=torus_coverage,
        )
        return replace(patch, id=_patch_id(patch, settings.stable_id_resolution_mm))

    freeform_stats = ResidualStats(
        rms=min(plane_stats.rms, cylinder_stats.rms, sphere_stats.rms, cone_stats.rms),
        median=min(
            plane_stats.median, cylinder_stats.median, sphere_stats.median, cone_stats.median
        ),
        p95=min(plane_stats.p95, cylinder_stats.p95, sphere_stats.p95, cone_stats.p95),
        maximum=min(
            plane_stats.maximum, cylinder_stats.maximum, sphere_stats.maximum, cone_stats.maximum
        ),
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


def _patch_adjacency(mesh: trimesh.Trimesh, patches: list[SurfacePatch]) -> dict[int, set[int]]:
    face_to_patch = {
        face_id: index for index, patch in enumerate(patches) for face_id in patch.triangle_ids
    }
    neighbors: dict[int, set[int]] = {index: set() for index in range(len(patches))}
    for left, right in np.asarray(mesh.face_adjacency, dtype=np.int64):
        left_index = face_to_patch[int(left)]
        right_index = face_to_patch[int(right)]
        if left_index != right_index:
            neighbors[left_index].add(right_index)
            neighbors[right_index].add(left_index)
    return neighbors


def _faceted_cylinder_candidate(
    mesh: trimesh.Trimesh,
    patches: list[SurfacePatch],
    neighbors: dict[int, set[int]],
    left_index: int,
    right_index: int,
    settings: SegmentationSettings,
) -> tuple[frozenset[int], SurfacePatch] | None:
    """Grow one analytic cylinder hypothesis from two adjacent planar strips.

    Polygonal STL cylinders are frequently split before surface fitting because their
    per-facet normal jump exceeds ``smooth_angle_deg``.  Two adjacent strips still expose
    the intended cylinder axis through the cross product of their normals and three or
    more common-radius vertices.  This routine grows only a closed cycle of matching
    strips and applies a chordal-sagitta gate before replacing them with cylinder evidence.
    """

    left, right = patches[left_index], patches[right_index]
    if (
        left.kind != "plane"
        or right.kind != "plane"
        or left.plane_normal is None
        or right.plane_normal is None
    ):
        return None
    left_normal = np.asarray(left.plane_normal, dtype=np.float64)
    right_normal = np.asarray(right.plane_normal, dtype=np.float64)
    normal_dot = float(np.dot(left_normal, right_normal))
    maximum_seed_angle_deg = min(
        75.0,
        360.0 / settings.minimum_faceted_cylinder_side_count * 1.5,
    )
    if normal_dot >= math.cos(math.radians(settings.smooth_angle_deg)) or normal_dot <= math.cos(
        math.radians(maximum_seed_angle_deg)
    ):
        return None
    axis = np.cross(left_normal, right_normal)
    axis_magnitude = float(np.linalg.norm(axis))
    if axis_magnitude <= 1e-12:
        return None
    axis = _canonical_direction(axis / axis_magnitude)
    shared_ids = sorted(set(left.vertex_ids) & set(right.vertex_ids))
    if len(shared_ids) < 2:
        return None
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    shared_points = vertices[shared_ids]
    edge_start, edge_end = max(
        combinations(range(len(shared_points)), 2),
        key=lambda pair: float(np.linalg.norm(shared_points[pair[1]] - shared_points[pair[0]])),
    )
    shared_direction = _canonical_direction(shared_points[edge_end] - shared_points[edge_start])
    if abs(float(np.dot(shared_direction, axis))) < math.cos(math.radians(2.0)):
        return None
    basis_u, basis_v = _orthogonal_basis(axis)
    seed_vertex_ids = sorted(set(left.vertex_ids) | set(right.vertex_ids))
    seed_points = vertices[seed_vertex_ids]
    seed_projected = np.column_stack((seed_points @ basis_u, seed_points @ basis_v))
    try:
        center_2d, radius, seed_stats, _ = _fit_circle_2d(seed_projected)
    except (ValueError, np.linalg.LinAlgError):
        return None
    radial_tolerance = max(
        settings.cylinder_fit_tolerance_mm,
        settings.stable_id_resolution_mm * 10,
    )
    if radius <= radial_tolerance or seed_stats.maximum > radial_tolerance:
        return None
    seed_axial = seed_points @ axis
    axial_min = float(np.min(seed_axial))
    axial_max = float(np.max(seed_axial))
    axial_tolerance = max(radial_tolerance * 2, settings.stable_id_resolution_mm * 20)

    eligibility: dict[int, bool] = {}

    def eligible(index: int) -> bool:
        if index in eligibility:
            return eligibility[index]
        patch = patches[index]
        if patch.kind != "plane" or patch.plane_normal is None:
            eligibility[index] = False
            return False
        normal = np.asarray(patch.plane_normal, dtype=np.float64)
        if abs(float(np.dot(normal, axis))) > settings.maximum_cylinder_axis_normal_component:
            eligibility[index] = False
            return False
        points = vertices[list(patch.vertex_ids)]
        projected = np.column_stack((points @ basis_u, points @ basis_v))
        radial = np.linalg.norm(projected - center_2d, axis=1)
        if float(np.max(np.abs(radial - radius))) > radial_tolerance:
            eligibility[index] = False
            return False
        axial = points @ axis
        if (
            abs(float(np.min(axial)) - axial_min) > axial_tolerance
            or abs(float(np.max(axial)) - axial_max) > axial_tolerance
        ):
            eligibility[index] = False
            return False
        eligibility[index] = True
        return True

    if not eligible(left_index) or not eligible(right_index):
        return None

    component: set[int] = set()
    pending = [left_index]
    while pending:
        index = pending.pop()
        if index in component or not eligible(index):
            continue
        component.add(index)
        pending.extend(sorted(neighbors[index] - component, reverse=True))
    if (
        right_index not in component
        or len(component) < settings.minimum_faceted_cylinder_side_count
        or any(len(neighbors[index] & component) != 2 for index in component)
    ):
        return None
    triangle_ids = np.asarray(
        sorted(face_id for index in component for face_id in patches[index].triangle_ids),
        dtype=np.int64,
    )
    fitted = fit_surface_patch(mesh, triangle_ids, settings)
    if (
        fitted.kind != "cylinder"
        or fitted.cylinder_axis is None
        or fitted.cylinder_radius_mm is None
    ):
        return None
    final_axis = np.asarray(fitted.cylinder_axis, dtype=np.float64)
    final_u, final_v = _orthogonal_basis(final_axis)
    final_points = vertices[list(fitted.vertex_ids)]
    final_projected = np.column_stack((final_points @ final_u, final_points @ final_v))
    final_center, final_radius, _, _ = _fit_circle_2d(final_projected)
    angles = np.mod(
        np.arctan2(
            final_projected[:, 1] - final_center[1],
            final_projected[:, 0] - final_center[0],
        ),
        2 * np.pi,
    )
    unique_angles = np.unique(np.round(angles, 12))
    if len(unique_angles) < settings.minimum_faceted_cylinder_side_count:
        return None
    gaps = np.diff(np.concatenate((unique_angles, unique_angles[:1] + 2 * np.pi)))
    maximum_gap = float(np.max(gaps))
    sagitta = final_radius * (1.0 - math.cos(maximum_gap / 2.0))
    if sagitta > settings.maximum_faceted_cylinder_sagitta_mm:
        return None
    confidence = min(
        fitted.confidence,
        max(0.0, 1.0 - sagitta / settings.maximum_faceted_cylinder_sagitta_mm),
    )
    return (
        frozenset(component),
        replace(
            fitted,
            confidence=confidence,
            recovered_from_facets=True,
            facet_sagitta_mm=sagitta,
        ),
    )


def _coalesce_faceted_cylinders(
    mesh: trimesh.Trimesh,
    patches: list[SurfacePatch],
    settings: SegmentationSettings,
) -> tuple[list[SurfacePatch], int]:
    neighbors = _patch_adjacency(mesh, patches)
    candidates: dict[frozenset[int], SurfacePatch] = {}
    for left_index in range(len(patches)):
        for right_index in sorted(neighbors[left_index]):
            if right_index <= left_index:
                continue
            candidate = _faceted_cylinder_candidate(
                mesh,
                patches,
                neighbors,
                left_index,
                right_index,
                settings,
            )
            if candidate is not None:
                members, cylinder = candidate
                candidates[members] = cylinder
    selected: list[tuple[frozenset[int], SurfacePatch]] = []
    claimed: set[int] = set()
    for members, cylinder in sorted(
        candidates.items(),
        key=lambda item: (-len(item[0]), item[1].id, tuple(sorted(item[0]))),
    ):
        if members & claimed:
            continue
        selected.append((members, cylinder))
        claimed.update(members)
    result = [patch for index, patch in enumerate(patches) if index not in claimed]
    result.extend(cylinder for _, cylinder in selected)
    result.sort(key=lambda patch: patch.id)
    return result, len(selected)


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
    patches, recovered_cylinder_count = _coalesce_faceted_cylinders(mesh, patches, settings)
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
    if recovered_cylinder_count:
        warnings.append(
            f"recovered {recovered_cylinder_count} analytic cylinder patch(es) from "
            "closed rings of planar STL facets"
        )
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
        if kind in set(ANALYTIC_PATCH_KINDS):
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
    "ANALYTIC_PATCH_KINDS",
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
