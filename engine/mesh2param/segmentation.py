"""Deterministic plane/cylinder segmentation and reversible patch editing.

The supported automatic scope is intentionally narrow: connected, sharp-edged,
plane- and full-cylinder-dominant mechanical meshes.  Poor fits remain freeform;
the engine does not relabel them optimistically.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from itertools import combinations
from typing import Any, Literal, get_args

import numpy as np
import trimesh
from scipy.optimize import least_squares

PatchKind = Literal["plane", "cylinder", "sphere", "cone", "torus", "freeform", "unknown"]
CurvatureClass = Literal["planar", "cylindrical", "fillet-band", "freeform"]
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
class PrincipalCurvatureEstimate:
    """Robust local principal-curvature evidence for one region vertex."""

    vertex_id: int
    minimum_mm_inv: float
    maximum_mm_inv: float
    minimum_direction: tuple[float, float, float] | None
    maximum_direction: tuple[float, float, float] | None
    neighborhood_vertex_count: int
    fit_rms_mm: float
    valid: bool


@dataclass(frozen=True, slots=True)
class CurvatureFragmentMerge:
    """Evidence for one sub-floor curvature fragment absorbed by a neighbor."""

    source_class: CurvatureClass
    target_class: CurvatureClass
    triangle_count: int
    area_mm2: float
    shared_boundary_length_mm: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourceClass": self.source_class,
            "targetClass": self.target_class,
            "triangleCount": self.triangle_count,
            "areaMm2": self.area_mm2,
            "sharedBoundaryLengthMm": self.shared_boundary_length_mm,
        }


@dataclass(frozen=True, slots=True)
class CurvaturePatchEvidence:
    """Curvature class and deterministic statistics attached to one patch."""

    curvature_class: CurvatureClass
    median_minimum_mm_inv: float
    median_maximum_mm_inv: float
    estimated_minimum_radius_mm: float | None
    valid_vertex_fraction: float
    fit_rms_p95_mm: float | None
    absorbed_fragments: tuple[CurvatureFragmentMerge, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": self.curvature_class,
            "medianMinimumMmInv": self.median_minimum_mm_inv,
            "medianMaximumMmInv": self.median_maximum_mm_inv,
            "estimatedMinimumRadiusMm": self.estimated_minimum_radius_mm,
            "validVertexFraction": self.valid_vertex_fraction,
            "fitRmsP95Mm": self.fit_rms_p95_mm,
            "absorbedFragments": [item.to_dict() for item in self.absorbed_fragments],
        }


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
    curvature_evidence: CurvaturePatchEvidence | None = None

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
        if self.curvature_evidence is not None:
            result["curvatureEvidence"] = self.curvature_evidence.to_dict()
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
    enable_curvature_subsegmentation: bool = False
    curvature_k_ring: int = 2
    curvature_minimum_neighbors: int = 6
    curvature_zero_tolerance_mm_inv: float = 0.03
    curvature_constant_relative_tolerance: float = 0.2
    curvature_hysteresis_ratio: float = 1.75
    curvature_axis_tolerance_deg: float = 20.0
    curvature_fillet_maximum_radius_fraction: float = 0.05
    curvature_fragment_minimum_area_mm2: float = 0.5
    curvature_fragment_minimum_area_fraction: float = 0.02
    curvature_fragment_minimum_triangles: int = 6

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
        if self.enable_curvature_subsegmentation:
            if self.curvature_k_ring < 1:
                raise ValueError("curvature k-ring must be at least one")
            if self.curvature_minimum_neighbors < 6:
                raise ValueError("curvature quadric fit requires at least six neighbors")
            if self.curvature_zero_tolerance_mm_inv <= 0:
                raise ValueError("curvature zero tolerance must be positive")
            if not 0 < self.curvature_constant_relative_tolerance < 1:
                raise ValueError("curvature constant tolerance must be in (0, 1)")
            if self.curvature_hysteresis_ratio < 1:
                raise ValueError("curvature hysteresis ratio must be at least one")
            if not 0 < self.curvature_axis_tolerance_deg < 90:
                raise ValueError("curvature axis tolerance must be in (0, 90) degrees")
            if not 0 < self.curvature_fillet_maximum_radius_fraction < 1:
                raise ValueError("fillet maximum-radius fraction must be in (0, 1)")
            if self.curvature_fragment_minimum_area_mm2 < 0:
                raise ValueError("curvature fragment minimum area cannot be negative")
            if not 0 <= self.curvature_fragment_minimum_area_fraction < 1:
                raise ValueError("curvature fragment area fraction must be in [0, 1)")
            if self.curvature_fragment_minimum_triangles < 1:
                raise ValueError("curvature fragment triangle floor must be at least one")


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

    @property
    def counts_by_curvature_class(self) -> dict[str, int]:
        return {
            curvature_class: sum(
                patch.curvature_evidence is not None
                and patch.curvature_evidence.curvature_class == curvature_class
                for patch in self.patches
            )
            for curvature_class in get_args(CurvatureClass)
        }

    def to_dict(self) -> dict[str, Any]:
        serialized_settings: dict[str, Any] = {
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
            "minimumFacetedCylinderSideCount": self.settings.minimum_faceted_cylinder_side_count,
            "maximumFacetedCylinderSagittaMm": (self.settings.maximum_faceted_cylinder_sagitta_mm),
            "minimumPatchAreaMm2": self.settings.minimum_patch_area_mm2,
            "stableIdResolutionMm": self.settings.stable_id_resolution_mm,
        }
        if self.settings.enable_curvature_subsegmentation:
            serialized_settings["curvatureSubsegmentation"] = {
                "enabled": True,
                "kRing": self.settings.curvature_k_ring,
                "minimumNeighbors": self.settings.curvature_minimum_neighbors,
                "zeroToleranceMmInv": self.settings.curvature_zero_tolerance_mm_inv,
                "constantRelativeTolerance": (self.settings.curvature_constant_relative_tolerance),
                "hysteresisRatio": self.settings.curvature_hysteresis_ratio,
                "axisToleranceDeg": self.settings.curvature_axis_tolerance_deg,
                "filletMaximumRadiusFraction": (
                    self.settings.curvature_fillet_maximum_radius_fraction
                ),
                "fragmentMinimumAreaMm2": (self.settings.curvature_fragment_minimum_area_mm2),
                "fragmentMinimumAreaFraction": (
                    self.settings.curvature_fragment_minimum_area_fraction
                ),
                "fragmentMinimumTriangles": (self.settings.curvature_fragment_minimum_triangles),
            }
        result: dict[str, Any] = {
            "settings": serialized_settings,
            "countsByType": self.counts_by_type,
            "warnings": list(self.warnings),
            "patches": [patch.to_dict() for patch in self.patches],
        }
        if self.settings.enable_curvature_subsegmentation:
            result["countsByCurvatureClass"] = self.counts_by_curvature_class
        return result


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
) -> tuple[np.ndarray, np.ndarray, float, float, ResidualStats, float, float]:
    """Axis-symmetric torus fit: center, axis, major/minor radii, residuals, coverage.

    In cylindrical coordinates around the symmetry axis the torus is the
    circle ``(rho - R)^2 + h^2 = r^2``, so the tube reduces to the existing
    deterministic 2-D circle fit.  The algebraic reduction is only an
    initializer: an exposed bead is a partial tube whose non-uniform trim
    biases PCA's axis, so center, axis, and both radii are polished together
    against the Euclidean torus residual.
    """

    offsets = points - centroid
    heights = offsets @ axis
    radial = np.linalg.norm(offsets - heights[:, None] * axis, axis=1)
    (rho_center, height_center), minor_radius, _, _ = _fit_circle_2d(
        np.column_stack((radial, heights))
    )
    center = centroid + height_center * axis
    axis = axis / max(float(np.linalg.norm(axis)), 1e-300)
    theta = math.acos(float(np.clip(axis[2], -1.0, 1.0)))
    phi = math.atan2(float(axis[1]), float(axis[0]))
    point_scale = max(float(np.linalg.norm(np.ptp(points, axis=0))), 1e-12)
    minimum_radius = max(point_scale * 1e-9, 1e-12)
    maximum_radius = max(point_scale * 1e6, minimum_radius * 10.0)
    initial_major = float(np.clip(rho_center, minimum_radius, maximum_radius))
    initial_minor = float(np.clip(minor_radius, minimum_radius, maximum_radius))

    def torus_residual(parameters: np.ndarray) -> np.ndarray:
        candidate_center = parameters[:3]
        candidate_theta, candidate_phi, log_major, log_minor = parameters[3:]
        candidate_axis = np.asarray(
            (
                math.sin(candidate_theta) * math.cos(candidate_phi),
                math.sin(candidate_theta) * math.sin(candidate_phi),
                math.cos(candidate_theta),
            )
        )
        candidate_offsets = points - candidate_center
        candidate_heights = candidate_offsets @ candidate_axis
        candidate_radial = np.linalg.norm(
            candidate_offsets - candidate_heights[:, None] * candidate_axis,
            axis=1,
        )
        return np.asarray(
            np.hypot(candidate_radial - math.exp(log_major), candidate_heights)
            - math.exp(log_minor)
        )

    optimized = least_squares(
        torus_residual,
        np.asarray(
            (
                *center,
                theta,
                phi,
                math.log(initial_major),
                math.log(initial_minor),
            )
        ),
        method="trf",
        bounds=(
            np.asarray(
                (
                    -np.inf,
                    -np.inf,
                    -np.inf,
                    -2.0 * np.pi,
                    -4.0 * np.pi,
                    math.log(minimum_radius),
                    math.log(minimum_radius),
                )
            ),
            np.asarray(
                (
                    np.inf,
                    np.inf,
                    np.inf,
                    2.0 * np.pi,
                    4.0 * np.pi,
                    math.log(maximum_radius),
                    math.log(maximum_radius),
                )
            ),
        ),
        ftol=1e-13,
        xtol=1e-13,
        gtol=1e-13,
        max_nfev=200,
    )
    center = np.asarray(optimized.x[:3])
    theta, phi = (float(value) for value in optimized.x[3:5])
    axis = np.asarray(
        (
            math.sin(theta) * math.cos(phi),
            math.sin(theta) * math.sin(phi),
            math.cos(theta),
        )
    )
    major_radius = math.exp(float(optimized.x[5]))
    minor_radius = math.exp(float(optimized.x[6]))
    stats = _residual_stats(torus_residual(optimized.x))

    offsets = points - center
    heights = offsets @ axis
    radial = np.linalg.norm(offsets - heights[:, None] * axis, axis=1)
    _, _, _, profile_coverage = _fit_circle_2d(np.column_stack((radial, heights)))
    basis_u, basis_v = _orthogonal_basis(axis)
    angles = np.mod(np.arctan2(offsets @ basis_v, offsets @ basis_u), 2 * np.pi)
    sorted_angles = np.sort(angles)
    gaps = np.diff(np.concatenate((sorted_angles, sorted_angles[:1] + 2 * np.pi)))
    revolution_coverage = math.degrees(2 * np.pi - float(np.max(gaps))) if len(angles) >= 2 else 0.0
    return (
        center,
        axis,
        major_radius,
        minor_radius,
        stats,
        revolution_coverage,
        profile_coverage,
    )


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
        torus_profile_coverage,
    ) = _fit_torus(points, plane_normal, centroid)
    if (
        not below_minimum_area
        and torus_stats.p95 <= settings.torus_fit_tolerance_mm
        and torus_coverage >= settings.minimum_revolution_coverage_deg
        # A proud bead exposes only part of the tube profile.  Ninety degrees
        # is still a strongly conditioned circle arc; the independent full
        # revolution and Euclidean residual gates remain unchanged.
        and torus_profile_coverage >= 90.0
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


@dataclass(frozen=True, slots=True)
class _FaceCurvatureMetric:
    face_id: int
    valid_fraction: float
    minimum_mm_inv: float
    maximum_mm_inv: float
    minimum_direction: tuple[float, float, float] | None
    minimum_radius_mm: float | None
    radius_relative_mad: float


@dataclass(frozen=True, slots=True)
class _CurvatureRegion:
    face_ids: tuple[int, ...]
    evidence: CurvaturePatchEvidence


@dataclass(frozen=True, slots=True)
class _FaceComponent:
    curvature_class: CurvatureClass
    face_ids: tuple[int, ...]
    area_mm2: float

    @property
    def minimum_face_id(self) -> int:
        return min(self.face_ids)


@dataclass(frozen=True, slots=True)
class _GrowthSeed:
    curvature_class: Literal["planar", "cylindrical", "fillet-band"]
    face_ids: tuple[int, ...]
    reference_radius_mm: float | None
    reference_axis: tuple[float, float, float] | None

    @property
    def minimum_face_id(self) -> int:
        return min(self.face_ids)


def _region_face_adjacency(mesh: trimesh.Trimesh, face_ids: tuple[int, ...]) -> dict[int, set[int]]:
    selected = set(face_ids)
    adjacency: dict[int, set[int]] = {face_id: set() for face_id in face_ids}
    for left_value, right_value in np.asarray(mesh.face_adjacency, dtype=np.int64):
        left, right = int(left_value), int(right_value)
        if left in selected and right in selected:
            adjacency[left].add(right)
            adjacency[right].add(left)
    return adjacency


def _region_vertex_topology(
    mesh: trimesh.Trimesh, face_ids: tuple[int, ...]
) -> tuple[dict[int, set[int]], dict[int, list[int]]]:
    faces = np.asarray(mesh.faces, dtype=np.int64)
    adjacency: dict[int, set[int]] = {}
    incident_faces: dict[int, list[int]] = {}
    for face_id in face_ids:
        first, second, third = (int(value) for value in faces[face_id])
        for vertex_id in (first, second, third):
            adjacency.setdefault(vertex_id, set())
            incident_faces.setdefault(vertex_id, []).append(face_id)
        for left, right in ((first, second), (second, third), (third, first)):
            adjacency[left].add(right)
            adjacency[right].add(left)
    return adjacency, incident_faces


def _k_ring_vertices(adjacency: dict[int, set[int]], vertex_id: int, rings: int) -> tuple[int, ...]:
    visited = {vertex_id}
    frontier = {vertex_id}
    for _ in range(rings):
        following: set[int] = set()
        for current in sorted(frontier):
            following.update(adjacency.get(current, ()))
        following -= visited
        if not following:
            break
        visited.update(following)
        frontier = following
    return tuple(sorted(visited))


def _invalid_curvature_estimate(
    vertex_id: int, neighborhood_vertex_count: int
) -> PrincipalCurvatureEstimate:
    return PrincipalCurvatureEstimate(
        vertex_id=vertex_id,
        minimum_mm_inv=0.0,
        maximum_mm_inv=0.0,
        minimum_direction=None,
        maximum_direction=None,
        neighborhood_vertex_count=neighborhood_vertex_count,
        fit_rms_mm=math.inf,
        valid=False,
    )


def _fit_vertex_quadric(
    vertices: np.ndarray,
    vertex_id: int,
    neighborhood: tuple[int, ...],
    incident_face_ids: list[int],
    face_normals: np.ndarray,
    face_areas: np.ndarray,
) -> PrincipalCurvatureEstimate:
    center = vertices[vertex_id]
    normal = np.sum(
        face_normals[incident_face_ids] * face_areas[incident_face_ids, None],
        axis=0,
    )
    normal_magnitude = float(np.linalg.norm(normal))
    if normal_magnitude <= 1e-15:
        return _invalid_curvature_estimate(vertex_id, len(neighborhood))
    normal /= normal_magnitude
    basis_u, basis_v = _orthogonal_basis(normal)
    offsets = vertices[list(neighborhood)] - center
    local_x = offsets @ basis_u
    local_y = offsets @ basis_v
    local_z = offsets @ normal
    radial = np.hypot(local_x, local_y)
    scale = float(np.sqrt(np.mean(radial * radial)))
    if not math.isfinite(scale) or scale <= 1e-12:
        return _invalid_curvature_estimate(vertex_id, len(neighborhood))
    x_values = local_x / scale
    y_values = local_y / scale
    z_values = local_z / scale
    design = np.column_stack(
        (
            0.5 * x_values * x_values,
            x_values * y_values,
            0.5 * y_values * y_values,
            x_values,
            y_values,
            np.ones(len(neighborhood)),
        )
    )
    base_weights = 1.0 / (1.0 + (radial / max(scale, 1e-300)) ** 2)
    weights = np.asarray(base_weights, dtype=np.float64)
    coefficients = np.zeros(6, dtype=np.float64)
    residuals = np.zeros(len(neighborhood), dtype=np.float64)
    try:
        for _ in range(5):
            square_root_weights = np.sqrt(np.maximum(weights, 1e-12))
            weighted_design = design * square_root_weights[:, None]
            if int(np.linalg.matrix_rank(weighted_design)) < 6:
                return _invalid_curvature_estimate(vertex_id, len(neighborhood))
            if float(np.linalg.cond(weighted_design)) > 1e12:
                return _invalid_curvature_estimate(vertex_id, len(neighborhood))
            coefficients = np.linalg.lstsq(
                weighted_design,
                z_values * square_root_weights,
                rcond=None,
            )[0]
            residuals = z_values - design @ coefficients
            residual_center = float(np.median(residuals))
            absolute_deviation = np.abs(residuals - residual_center)
            robust_scale = 1.4826 * float(np.median(absolute_deviation))
            if robust_scale <= 1e-12:
                break
            cutoff = 1.345 * robust_scale
            robust_weights = np.minimum(
                1.0,
                cutoff / np.maximum(absolute_deviation, 1e-300),
            )
            weights = base_weights * robust_weights
    except np.linalg.LinAlgError:
        return _invalid_curvature_estimate(vertex_id, len(neighborhood))

    curvature_xx, curvature_xy, curvature_yy, slope_x, slope_y, _ = coefficients
    gradient_norm = 1.0 + slope_x * slope_x + slope_y * slope_y
    first_form = np.asarray(
        (
            (1.0 + slope_x * slope_x, slope_x * slope_y),
            (slope_x * slope_y, 1.0 + slope_y * slope_y),
        )
    )
    second_form = np.asarray(
        (
            (curvature_xx, curvature_xy),
            (curvature_xy, curvature_yy),
        )
    ) / (scale * math.sqrt(gradient_norm))
    try:
        values, directions = np.linalg.eig(np.linalg.solve(first_form, second_form))
    except np.linalg.LinAlgError:
        return _invalid_curvature_estimate(vertex_id, len(neighborhood))
    if np.max(np.abs(np.imag(values))) > 1e-10 or np.max(np.abs(np.imag(directions))) > 1e-10:
        return _invalid_curvature_estimate(vertex_id, len(neighborhood))
    real_values = np.real(values)
    real_directions = np.real(directions)
    order = sorted(range(2), key=lambda index: (abs(float(real_values[index])), index))
    global_directions: list[tuple[float, float, float]] = []
    for index in order:
        local_direction = real_directions[:, index]
        direction = (
            local_direction[0] * basis_u
            + local_direction[1] * basis_v
            + (slope_x * local_direction[0] + slope_y * local_direction[1]) * normal
        )
        try:
            global_directions.append(_tuple3(_canonical_direction(direction)))
        except ValueError:
            return _invalid_curvature_estimate(vertex_id, len(neighborhood))
    minimum_value = float(real_values[order[0]])
    maximum_value = float(real_values[order[1]])
    fit_rms = scale * float(np.sqrt(np.mean(residuals * residuals)))
    if not all(math.isfinite(value) for value in (minimum_value, maximum_value, fit_rms)):
        return _invalid_curvature_estimate(vertex_id, len(neighborhood))
    return PrincipalCurvatureEstimate(
        vertex_id=vertex_id,
        minimum_mm_inv=minimum_value,
        maximum_mm_inv=maximum_value,
        minimum_direction=global_directions[0],
        maximum_direction=global_directions[1],
        neighborhood_vertex_count=len(neighborhood),
        fit_rms_mm=fit_rms,
        valid=True,
    )


def estimate_principal_curvatures(
    mesh: trimesh.Trimesh,
    face_ids: np.ndarray | tuple[int, ...] | list[int],
    settings: SegmentationSettings | None = None,
) -> tuple[PrincipalCurvatureEstimate, ...]:
    """Estimate principal curvatures by deterministic robust k-ring quadrics."""

    active_settings = settings or SegmentationSettings(enable_curvature_subsegmentation=True)
    if active_settings.curvature_k_ring < 1 or active_settings.curvature_minimum_neighbors < 6:
        raise ValueError("curvature estimation requires a positive k-ring and six neighbors")
    selected = tuple(sorted(set(int(value) for value in face_ids)))
    if not selected or selected[0] < 0 or selected[-1] >= len(mesh.faces):
        raise ValueError("curvature face IDs are empty or out of range")
    adjacency, incident_faces = _region_vertex_topology(mesh, selected)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    face_normals = np.asarray(mesh.face_normals, dtype=np.float64)
    face_areas = np.asarray(mesh.area_faces, dtype=np.float64)
    estimates: list[PrincipalCurvatureEstimate] = []
    for vertex_id in sorted(adjacency):
        neighborhood = _k_ring_vertices(adjacency, vertex_id, active_settings.curvature_k_ring)
        if len(neighborhood) < active_settings.curvature_minimum_neighbors:
            estimates.append(_invalid_curvature_estimate(vertex_id, len(neighborhood)))
            continue
        estimates.append(
            _fit_vertex_quadric(
                vertices,
                vertex_id,
                neighborhood,
                incident_faces[vertex_id],
                face_normals,
                face_areas,
            )
        )
    return tuple(estimates)


def _average_directions(
    directions: list[tuple[float, float, float]],
) -> tuple[float, float, float] | None:
    if not directions:
        return None
    reference = np.asarray(directions[0], dtype=np.float64)
    aligned = []
    for direction_value in directions:
        direction = np.asarray(direction_value, dtype=np.float64)
        aligned.append(-direction if float(np.dot(direction, reference)) < 0.0 else direction)
    average = np.sum(np.asarray(aligned), axis=0)
    if float(np.linalg.norm(average)) <= 1e-15:
        return None
    return _tuple3(_canonical_direction(average))


def _face_curvature_metrics(
    mesh: trimesh.Trimesh,
    face_ids: tuple[int, ...],
    estimates: tuple[PrincipalCurvatureEstimate, ...],
) -> dict[int, _FaceCurvatureMetric]:
    by_vertex = {estimate.vertex_id: estimate for estimate in estimates}
    faces = np.asarray(mesh.faces, dtype=np.int64)
    metrics: dict[int, _FaceCurvatureMetric] = {}
    for face_id in face_ids:
        candidates = [by_vertex[int(vertex_id)] for vertex_id in faces[face_id]]
        valid = [estimate for estimate in candidates if estimate.valid]
        valid_fraction = len(valid) / 3.0
        if not valid:
            metrics[face_id] = _FaceCurvatureMetric(
                face_id,
                valid_fraction,
                math.inf,
                math.inf,
                None,
                None,
                math.inf,
            )
            continue
        minimum_values = np.asarray(
            [abs(estimate.minimum_mm_inv) for estimate in valid], dtype=np.float64
        )
        maximum_values = np.asarray(
            [abs(estimate.maximum_mm_inv) for estimate in valid], dtype=np.float64
        )
        minimum_value = float(np.median(minimum_values))
        maximum_value = float(np.median(maximum_values))
        directions = [
            estimate.minimum_direction
            for estimate in valid
            if estimate.minimum_direction is not None
        ]
        positive = maximum_values[maximum_values > 1e-12]
        if len(positive):
            radii = 1.0 / positive
            radius = float(np.median(radii))
            radius_relative_mad = float(np.median(np.abs(radii - radius)) / max(radius, 1e-300))
        else:
            radius = None
            radius_relative_mad = 0.0
        metrics[face_id] = _FaceCurvatureMetric(
            face_id=face_id,
            valid_fraction=valid_fraction,
            minimum_mm_inv=minimum_value,
            maximum_mm_inv=maximum_value,
            minimum_direction=_average_directions(directions),
            minimum_radius_mm=radius,
            radius_relative_mad=radius_relative_mad,
        )
    return metrics


def _strict_curvature_class(
    metric: _FaceCurvatureMetric,
    fillet_maximum_radius_mm: float,
    settings: SegmentationSettings,
) -> Literal["planar", "cylindrical", "fillet-band"] | None:
    if metric.valid_fraction < 2.0 / 3.0:
        return None
    zero = settings.curvature_zero_tolerance_mm_inv
    if metric.maximum_mm_inv <= zero:
        return "planar"
    if (
        metric.minimum_radius_mm is not None
        and metric.minimum_radius_mm <= fillet_maximum_radius_mm
        and metric.radius_relative_mad <= settings.curvature_constant_relative_tolerance
    ):
        return "fillet-band"
    if (
        metric.minimum_mm_inv <= zero
        and metric.maximum_mm_inv >= 2.0 * zero
        and metric.minimum_direction is not None
        and metric.radius_relative_mad <= settings.curvature_constant_relative_tolerance
    ):
        return "cylindrical"
    return None


def _labeled_components(
    face_ids: tuple[int, ...],
    adjacency: dict[int, set[int]],
    labels: Mapping[int, CurvatureClass | None],
    *,
    include_freeform: bool,
) -> list[_FaceComponent]:
    unvisited = set(face_ids)
    components: list[_FaceComponent] = []
    while unvisited:
        start = min(unvisited)
        curvature_class = labels[start]
        if curvature_class is None or (curvature_class == "freeform" and not include_freeform):
            unvisited.remove(start)
            continue
        pending = [start]
        members: list[int] = []
        while pending:
            current = pending.pop()
            if current not in unvisited or labels[current] != curvature_class:
                continue
            unvisited.remove(current)
            members.append(current)
            pending.extend(sorted(adjacency[current] & unvisited, reverse=True))
        components.append(
            _FaceComponent(
                curvature_class=curvature_class,
                face_ids=tuple(sorted(members)),
                area_mm2=0.0,
            )
        )
    components.sort(key=lambda component: component.minimum_face_id)
    return components


def _seed_axis(
    face_ids: tuple[int, ...], metrics: dict[int, _FaceCurvatureMetric]
) -> tuple[float, float, float] | None:
    directions: list[tuple[float, float, float]] = []
    for face_id in face_ids:
        direction = metrics[face_id].minimum_direction
        if direction is not None:
            directions.append(direction)
    return _average_directions(directions)


def _plane_fit_p95_mm(mesh: trimesh.Trimesh, face_ids: tuple[int, ...]) -> float:
    faces = np.asarray(mesh.faces, dtype=np.int64)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    face_areas = np.asarray(mesh.area_faces, dtype=np.float64)[list(face_ids)]
    face_centers = np.asarray(mesh.triangles_center, dtype=np.float64)[list(face_ids)]
    vertex_ids = np.unique(faces[list(face_ids)].reshape(-1))
    points = vertices[vertex_ids]
    centroid = np.average(face_centers, axis=0, weights=face_areas)
    try:
        _, _, vectors = np.linalg.svd(points - np.mean(points, axis=0), full_matrices=False)
    except np.linalg.LinAlgError:
        return math.inf
    distances = np.abs((points - centroid) @ vectors[-1])
    return float(np.quantile(distances, 0.95))


def _coplanar_seed_faces(
    mesh: trimesh.Trimesh,
    face_ids: tuple[int, ...],
    adjacency: dict[int, set[int]],
    settings: SegmentationSettings,
) -> set[int]:
    """Find deterministic, materially sized coplanar seed components.

    A quadric centered on a plane boundary necessarily sees the adjoining fillet and can
    report non-zero curvature.  This geometric seed preserves exact planar interiors while
    still requiring a connected, multi-face component large enough not to relabel individual
    tessellation facets as planes.
    """

    face_normals = np.asarray(mesh.face_normals, dtype=np.float64)
    face_areas = np.asarray(mesh.area_faces, dtype=np.float64)
    region_area = float(np.sum(face_areas[list(face_ids)]))
    area_floor = max(
        settings.curvature_fragment_minimum_area_mm2,
        region_area * 0.01,
    )
    minimum_alignment = math.cos(math.radians(0.1))
    unvisited = set(face_ids)
    planar: set[int] = set()
    while unvisited:
        start = min(unvisited)
        unvisited.remove(start)
        pending = [start]
        members: list[int] = []
        reference_normal = face_normals[start]
        while pending:
            current = pending.pop()
            members.append(current)
            for neighbor in sorted(adjacency[current], reverse=True):
                if neighbor not in unvisited:
                    continue
                if float(np.dot(reference_normal, face_normals[neighbor])) < minimum_alignment:
                    continue
                unvisited.remove(neighbor)
                pending.append(neighbor)
        component_area = float(np.sum(face_areas[members]))
        if len(members) < 2 or (
            len(members) < settings.curvature_fragment_minimum_triangles
            and component_area < area_floor
        ):
            continue
        if _plane_fit_p95_mm(mesh, tuple(members)) <= settings.planar_fit_tolerance_mm:
            planar.update(members)
    return planar


def _growth_score(
    seed: _GrowthSeed,
    metric: _FaceCurvatureMetric,
    fillet_maximum_radius_mm: float,
    settings: SegmentationSettings,
) -> float | None:
    if metric.valid_fraction < 1.0 / 3.0:
        return None
    zero = settings.curvature_zero_tolerance_mm_inv
    hysteresis = settings.curvature_hysteresis_ratio
    if seed.curvature_class == "planar":
        return None
    if seed.curvature_class == "fillet-band":
        if metric.minimum_radius_mm is None or seed.reference_radius_mm is None:
            return None
        if metric.minimum_radius_mm > fillet_maximum_radius_mm * hysteresis:
            return None
        radius_delta = abs(metric.minimum_radius_mm - seed.reference_radius_mm) / max(
            seed.reference_radius_mm, 1e-300
        )
        if radius_delta > settings.curvature_constant_relative_tolerance * hysteresis:
            return None
        if metric.radius_relative_mad > settings.curvature_constant_relative_tolerance * hysteresis:
            return None
        return radius_delta
    cylindrical_minimum_limit = max(
        zero * hysteresis,
        metric.maximum_mm_inv * 0.55,
    )
    if (
        metric.minimum_mm_inv > cylindrical_minimum_limit
        or metric.maximum_mm_inv <= zero / hysteresis
    ):
        return None
    if metric.minimum_direction is None or seed.reference_axis is None:
        return None
    alignment = abs(
        float(
            np.dot(
                np.asarray(metric.minimum_direction),
                np.asarray(seed.reference_axis),
            )
        )
    )
    minimum_alignment = math.cos(math.radians(settings.curvature_axis_tolerance_deg))
    if alignment < minimum_alignment:
        return None
    return metric.minimum_mm_inv / max(cylindrical_minimum_limit, 1e-300) + (1.0 - alignment)


def _grow_curvature_classes(
    mesh: trimesh.Trimesh,
    face_ids: tuple[int, ...],
    adjacency: dict[int, set[int]],
    metrics: dict[int, _FaceCurvatureMetric],
    fillet_maximum_radius_mm: float,
    settings: SegmentationSettings,
) -> dict[int, CurvatureClass]:
    coplanar_faces = _coplanar_seed_faces(mesh, face_ids, adjacency, settings)
    strict_labels: dict[int, CurvatureClass | None] = {
        face_id: _strict_curvature_class(metrics[face_id], fillet_maximum_radius_mm, settings)
        for face_id in face_ids
    }
    for face_id, curvature_class in strict_labels.items():
        if curvature_class == "planar" and face_id not in coplanar_faces:
            strict_labels[face_id] = None
    for face_id in coplanar_faces:
        strict_labels[face_id] = "planar"
    seed_components = _labeled_components(
        face_ids,
        adjacency,
        strict_labels,
        include_freeform=False,
    )
    seeds: list[_GrowthSeed] = []
    for component in seed_components:
        curvature_class = component.curvature_class
        if curvature_class == "freeform":
            continue
        radii: list[float] = []
        for face_id in component.face_ids:
            radius = metrics[face_id].minimum_radius_mm
            if radius is not None:
                radii.append(radius)
        seeds.append(
            _GrowthSeed(
                curvature_class=curvature_class,
                face_ids=component.face_ids,
                reference_radius_mm=float(np.median(radii)) if radii else None,
                reference_axis=(
                    _seed_axis(component.face_ids, metrics)
                    if curvature_class == "cylindrical"
                    else None
                ),
            )
        )
    class_priority = {"fillet-band": 0, "planar": 1, "cylindrical": 2}
    seeds.sort(key=lambda seed: (class_priority[seed.curvature_class], seed.minimum_face_id))
    owner: dict[int, int] = {}
    for seed_index, seed in enumerate(seeds):
        for face_id in seed.face_ids:
            owner[face_id] = seed_index
    pending: list[tuple[float, int, int, int, int]] = []

    def enqueue(seed_index: int, face_id: int) -> None:
        if face_id in owner:
            return
        seed = seeds[seed_index]
        score = _growth_score(
            seed,
            metrics[face_id],
            fillet_maximum_radius_mm,
            settings,
        )
        if score is None:
            return
        heapq.heappush(
            pending,
            (
                score,
                class_priority[seed.curvature_class],
                seed.minimum_face_id,
                face_id,
                seed_index,
            ),
        )

    for face_id, seed_index in sorted(owner.items()):
        for neighbor in sorted(adjacency[face_id]):
            enqueue(seed_index, neighbor)
    while pending:
        _, _, _, face_id, seed_index = heapq.heappop(pending)
        if face_id in owner:
            continue
        owner[face_id] = seed_index
        for neighbor in sorted(adjacency[face_id]):
            enqueue(seed_index, neighbor)
    return {
        face_id: seeds[owner[face_id]].curvature_class if face_id in owner else "freeform"
        for face_id in face_ids
    }


def _adjacency_edge_lengths(mesh: trimesh.Trimesh) -> dict[tuple[int, int], float]:
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    result: dict[tuple[int, int], float] = {}
    adjacency = np.asarray(mesh.face_adjacency, dtype=np.int64)
    edges = np.asarray(mesh.face_adjacency_edges, dtype=np.int64)
    for (left_value, right_value), (start, end) in zip(adjacency, edges, strict=True):
        left, right = int(left_value), int(right_value)
        key = min(left, right), max(left, right)
        result[key] = float(np.linalg.norm(vertices[int(end)] - vertices[int(start)]))
    return result


def _components_with_area(
    mesh: trimesh.Trimesh,
    face_ids: tuple[int, ...],
    adjacency: dict[int, set[int]],
    labels: dict[int, CurvatureClass],
) -> list[_FaceComponent]:
    components = _labeled_components(
        face_ids,
        adjacency,
        labels,
        include_freeform=True,
    )
    areas = np.asarray(mesh.area_faces, dtype=np.float64)
    return [
        replace(
            component,
            area_mm2=float(np.sum(areas[list(component.face_ids)])),
        )
        for component in components
    ]


def _promote_cylindrical_wall_planes(
    mesh: trimesh.Trimesh,
    face_ids: tuple[int, ...],
    adjacency: dict[int, set[int]],
    labels: dict[int, CurvatureClass],
    metrics: dict[int, _FaceCurvatureMetric],
    edge_lengths: dict[tuple[int, int], float],
    settings: SegmentationSettings,
) -> None:
    components = _components_with_area(mesh, face_ids, adjacency, labels)
    face_to_component = {
        face_id: index
        for index, component in enumerate(components)
        for face_id in component.face_ids
    }
    cylinder_axes = {
        index: _seed_axis(component.face_ids, metrics)
        for index, component in enumerate(components)
        if component.curvature_class == "cylindrical"
    }
    face_normals = np.asarray(mesh.face_normals, dtype=np.float64)
    face_areas = np.asarray(mesh.area_faces, dtype=np.float64)
    region_area = float(np.sum(face_areas[list(face_ids)]))
    maximum_normal_component = math.sin(math.radians(settings.curvature_axis_tolerance_deg))

    def component_normal(component: _FaceComponent) -> np.ndarray | None:
        normal = np.sum(
            face_normals[list(component.face_ids)] * face_areas[list(component.face_ids), None],
            axis=0,
        )
        magnitude = float(np.linalg.norm(normal))
        return normal / magnitude if magnitude > 1e-15 else None

    dominant_plane_normals = [
        normal
        for component in components
        if component.curvature_class == "planar" and component.area_mm2 >= region_area * 0.1
        if (normal := component_normal(component)) is not None
    ]
    extrusion_axis: np.ndarray | None = None
    if len(dominant_plane_normals) >= 2:
        reference = dominant_plane_normals[0]
        aligned = [
            -normal if float(np.dot(normal, reference)) < 0.0 else normal
            for normal in dominant_plane_normals
        ]
        if all(
            abs(float(np.dot(reference, normal)))
            >= math.cos(math.radians(settings.curvature_axis_tolerance_deg))
            for normal in dominant_plane_normals[1:]
        ):
            extrusion_axis = np.asarray(_canonical_direction(np.sum(aligned, axis=0)))
    for index, component in enumerate(components):
        if component.curvature_class != "planar" or component.area_mm2 >= region_area * 0.1:
            continue
        normal = component_normal(component)
        if normal is None:
            continue
        if (
            extrusion_axis is not None
            and abs(float(np.dot(normal, extrusion_axis))) <= maximum_normal_component
        ):
            for face_id in component.face_ids:
                labels[face_id] = "cylindrical"
            continue
        shared_by_neighbor: dict[int, float] = {}
        for face_id in component.face_ids:
            for neighbor in adjacency[face_id]:
                neighbor_index = face_to_component[neighbor]
                if neighbor_index == index or neighbor_index not in cylinder_axes:
                    continue
                key = min(face_id, neighbor), max(face_id, neighbor)
                shared_by_neighbor[neighbor_index] = (
                    shared_by_neighbor.get(neighbor_index, 0.0) + (edge_lengths[key])
                )
        candidates = [
            neighbor_index
            for neighbor_index in shared_by_neighbor
            if cylinder_axes[neighbor_index] is not None
        ]
        if not candidates:
            continue
        candidates.sort(
            key=lambda neighbor_index: (
                -shared_by_neighbor[neighbor_index],
                -components[neighbor_index].area_mm2,
                components[neighbor_index].minimum_face_id,
            )
        )
        target = candidates[0]
        axis = cylinder_axes[target]
        if axis is None or abs(float(np.dot(normal, np.asarray(axis)))) > maximum_normal_component:
            continue
        for face_id in component.face_ids:
            labels[face_id] = "cylindrical"


def _merge_subfloor_fragments(
    mesh: trimesh.Trimesh,
    face_ids: tuple[int, ...],
    adjacency: dict[int, set[int]],
    labels: dict[int, CurvatureClass],
    edge_lengths: dict[tuple[int, int], float],
    settings: SegmentationSettings,
) -> list[tuple[int, CurvatureFragmentMerge]]:
    face_areas = np.asarray(mesh.area_faces, dtype=np.float64)
    region_area = float(np.sum(face_areas[list(face_ids)]))
    area_floor = max(
        settings.curvature_fragment_minimum_area_mm2,
        region_area * settings.curvature_fragment_minimum_area_fraction,
    )
    records: list[tuple[int, CurvatureFragmentMerge]] = []
    for _ in range(len(face_ids)):
        components = _components_with_area(mesh, face_ids, adjacency, labels)
        if len(components) <= 1:
            break
        face_to_component = {
            face_id: index
            for index, component in enumerate(components)
            for face_id in component.face_ids
        }
        small = [
            (index, component)
            for index, component in enumerate(components)
            if component.area_mm2 < area_floor
            or (
                len(component.face_ids) < settings.curvature_fragment_minimum_triangles
                and component.area_mm2 < 2.0 * area_floor
            )
        ]
        small.sort(key=lambda item: (item[1].area_mm2, item[1].minimum_face_id))
        merged = False
        for source_index, source in small:
            shared_by_neighbor: dict[int, float] = {}
            for face_id in source.face_ids:
                for neighbor in adjacency[face_id]:
                    neighbor_index = face_to_component[neighbor]
                    if neighbor_index == source_index:
                        continue
                    key = min(face_id, neighbor), max(face_id, neighbor)
                    shared_by_neighbor[neighbor_index] = (
                        shared_by_neighbor.get(neighbor_index, 0.0) + edge_lengths[key]
                    )
            if not shared_by_neighbor:
                continue
            candidates = sorted(
                shared_by_neighbor,
                key=lambda index: (
                    -shared_by_neighbor[index],
                    -components[index].area_mm2,
                    components[index].minimum_face_id,
                ),
            )
            compatible = [
                index
                for index in candidates
                if components[index].curvature_class != "planar"
                or _plane_fit_p95_mm(
                    mesh,
                    tuple(
                        sorted(
                            (*source.face_ids, *components[index].face_ids),
                        )
                    ),
                )
                <= settings.planar_fit_tolerance_mm
            ]
            target_index = compatible[0] if compatible else candidates[0]
            target = components[target_index]
            records.append(
                (
                    target.minimum_face_id,
                    CurvatureFragmentMerge(
                        source_class=source.curvature_class,
                        target_class=target.curvature_class,
                        triangle_count=len(source.face_ids),
                        area_mm2=source.area_mm2,
                        shared_boundary_length_mm=shared_by_neighbor[target_index],
                    ),
                )
            )
            for face_id in source.face_ids:
                labels[face_id] = target.curvature_class
            merged = True
            break
        if not merged:
            break
    return records


def _curvature_evidence(
    mesh: trimesh.Trimesh,
    component: _FaceComponent,
    estimates_by_vertex: dict[int, PrincipalCurvatureEstimate],
    absorbed_fragments: tuple[CurvatureFragmentMerge, ...],
    settings: SegmentationSettings,
) -> CurvaturePatchEvidence:
    faces = np.asarray(mesh.faces, dtype=np.int64)
    vertex_ids = tuple(
        sorted(set(int(value) for value in faces[list(component.face_ids)].reshape(-1)))
    )
    valid = [
        estimates_by_vertex[vertex_id]
        for vertex_id in vertex_ids
        if vertex_id in estimates_by_vertex and estimates_by_vertex[vertex_id].valid
    ]
    valid_fraction = len(valid) / max(len(vertex_ids), 1)
    minimum_values = [abs(estimate.minimum_mm_inv) for estimate in valid]
    maximum_values = [abs(estimate.maximum_mm_inv) for estimate in valid]
    fit_rms_values = [estimate.fit_rms_mm for estimate in valid]
    median_minimum = float(np.median(minimum_values)) if minimum_values else 0.0
    median_maximum = float(np.median(maximum_values)) if maximum_values else 0.0
    if component.curvature_class == "fillet-band":
        radii = [
            1.0 / value
            for value in maximum_values
            if value > settings.curvature_zero_tolerance_mm_inv
        ]
        estimated_radius = float(np.median(radii)) if radii else None
    else:
        estimated_radius = None
    aggregated_fragments: dict[tuple[CurvatureClass, CurvatureClass], CurvatureFragmentMerge] = {}
    for fragment in absorbed_fragments:
        key = fragment.source_class, fragment.target_class
        previous = aggregated_fragments.get(key)
        aggregated_fragments[key] = CurvatureFragmentMerge(
            source_class=fragment.source_class,
            target_class=fragment.target_class,
            triangle_count=fragment.triangle_count + (previous.triangle_count if previous else 0),
            area_mm2=fragment.area_mm2 + (previous.area_mm2 if previous else 0.0),
            shared_boundary_length_mm=fragment.shared_boundary_length_mm
            + (previous.shared_boundary_length_mm if previous else 0.0),
        )
    return CurvaturePatchEvidence(
        curvature_class=component.curvature_class,
        median_minimum_mm_inv=median_minimum,
        median_maximum_mm_inv=median_maximum,
        estimated_minimum_radius_mm=estimated_radius,
        valid_vertex_fraction=valid_fraction,
        fit_rms_p95_mm=(float(np.quantile(fit_rms_values, 0.95)) if fit_rms_values else None),
        absorbed_fragments=tuple(aggregated_fragments[key] for key in sorted(aggregated_fragments)),
    )


def _analytic_curvature_evidence(patch: SurfacePatch) -> CurvaturePatchEvidence:
    if patch.kind == "plane":
        curvature_class: CurvatureClass = "planar"
        maximum = 0.0
    elif patch.kind == "cylinder":
        curvature_class = "cylindrical"
        maximum = (
            1.0 / patch.cylinder_radius_mm
            if patch.cylinder_radius_mm is not None and patch.cylinder_radius_mm > 0.0
            else 0.0
        )
    else:
        curvature_class = "freeform"
        maximum = 0.0
    return CurvaturePatchEvidence(
        curvature_class=curvature_class,
        median_minimum_mm_inv=0.0,
        median_maximum_mm_inv=maximum,
        estimated_minimum_radius_mm=None,
        valid_vertex_fraction=0.0,
        fit_rms_p95_mm=patch.residuals_mm.p95,
    )


def _subdivide_patch_by_curvature(
    mesh: trimesh.Trimesh,
    patch: SurfacePatch,
    settings: SegmentationSettings,
) -> tuple[list[_CurvatureRegion], int]:
    if patch.kind != "freeform":
        return [
            _CurvatureRegion(
                face_ids=patch.triangle_ids,
                evidence=_analytic_curvature_evidence(patch),
            )
        ], 0
    face_ids = tuple(sorted(patch.triangle_ids))
    estimates = estimate_principal_curvatures(mesh, face_ids, settings)
    estimates_by_vertex = {estimate.vertex_id: estimate for estimate in estimates}
    if not any(estimate.valid for estimate in estimates):
        component = _FaceComponent("freeform", face_ids, patch.area_mm2)
        return [
            _CurvatureRegion(
                face_ids=face_ids,
                evidence=_curvature_evidence(mesh, component, estimates_by_vertex, (), settings),
            )
        ], 0
    metrics = _face_curvature_metrics(mesh, face_ids, estimates)
    adjacency = _region_face_adjacency(mesh, face_ids)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    selected_vertex_ids = np.unique(
        np.asarray(mesh.faces, dtype=np.int64)[list(face_ids)].reshape(-1)
    )
    diagonal = float(np.linalg.norm(np.ptp(vertices[selected_vertex_ids], axis=0)))
    fillet_maximum_radius = max(
        diagonal * settings.curvature_fillet_maximum_radius_fraction,
        settings.stable_id_resolution_mm * 10.0,
    )
    labels = _grow_curvature_classes(
        mesh,
        face_ids,
        adjacency,
        metrics,
        fillet_maximum_radius,
        settings,
    )
    edge_lengths = _adjacency_edge_lengths(mesh)
    _promote_cylindrical_wall_planes(
        mesh,
        face_ids,
        adjacency,
        labels,
        metrics,
        edge_lengths,
        settings,
    )
    merge_records = _merge_subfloor_fragments(
        mesh,
        face_ids,
        adjacency,
        labels,
        edge_lengths,
        settings,
    )
    components = _components_with_area(mesh, face_ids, adjacency, labels)
    face_to_component = {
        face_id: index
        for index, component in enumerate(components)
        for face_id in component.face_ids
    }
    records_by_component: dict[int, list[CurvatureFragmentMerge]] = {
        index: [] for index in range(len(components))
    }
    for target_face_id, record in merge_records:
        records_by_component[face_to_component[target_face_id]].append(record)
    regions = [
        _CurvatureRegion(
            face_ids=component.face_ids,
            evidence=_curvature_evidence(
                mesh,
                component,
                estimates_by_vertex,
                tuple(records_by_component[index]),
                settings,
            ),
        )
        for index, component in enumerate(components)
    ]
    regions.sort(key=lambda region: min(region.face_ids))
    return regions, len(merge_records)


def _subdivide_patches_by_curvature(
    mesh: trimesh.Trimesh,
    patches: list[SurfacePatch],
    settings: SegmentationSettings,
) -> tuple[list[SurfacePatch], int, int]:
    regions: list[_CurvatureRegion] = []
    merged_fragment_count = 0
    for patch in sorted(patches, key=lambda item: min(item.triangle_ids)):
        patch_regions, patch_merge_count = _subdivide_patch_by_curvature(mesh, patch, settings)
        regions.extend(patch_regions)
        merged_fragment_count += patch_merge_count
    fitted = [
        replace(
            fit_surface_patch(mesh, np.asarray(region.face_ids, dtype=np.int64), settings),
            curvature_evidence=region.evidence,
        )
        for region in regions
    ]
    fitted.sort(key=lambda patch: patch.id)
    return fitted, len(fitted) - len(patches), merged_fragment_count


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
    curvature_patch_delta = 0
    merged_curvature_fragment_count = 0
    if settings.enable_curvature_subsegmentation:
        patches, curvature_patch_delta, merged_curvature_fragment_count = (
            _subdivide_patches_by_curvature(mesh, patches, settings)
        )
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
    if settings.enable_curvature_subsegmentation:
        warnings.append(
            "curvature sub-segmentation enabled; patch classes carry robust quadric evidence"
        )
        if curvature_patch_delta:
            warnings.append(f"curvature sub-segmentation added {curvature_patch_delta} patch(es)")
        if merged_curvature_fragment_count:
            warnings.append(
                f"merged {merged_curvature_fragment_count} sub-floor curvature fragment(s) "
                "into dominant neighbors with recorded evidence"
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
    "CurvatureClass",
    "CurvatureFragmentMerge",
    "CurvaturePatchEvidence",
    "PatchEditRecord",
    "PatchEditSession",
    "PatchKind",
    "PrincipalCurvatureEstimate",
    "ResidualStats",
    "SegmentationResult",
    "SegmentationSettings",
    "SurfacePatch",
    "estimate_principal_curvatures",
    "fit_surface_patch",
    "segment_mesh",
]
