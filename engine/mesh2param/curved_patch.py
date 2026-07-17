"""Milestone 1 vertical: one fitted freeform patch inside a closed solid.

Reconstructs a "plate" body -- a single disk-like freeform region whose
straight, creased rectangular boundary meets planar walls over a planar
bottom -- from a triangle mesh. The freeform region is harmonically
parameterized, fitted with a fair sparse B-spline patch whose boundary poles
are pinned to the exact crease rectangle, and assembled with the analytic
faces into one closed, validated solid. This deliberately supports only the
single-patch topology; the general surface network is Milestone 2.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

import cadquery as cq
import numpy as np
import trimesh
from OCP.BRepBuilderAPI import (
    BRepBuilderAPI_MakeFace,
    BRepBuilderAPI_MakePolygon,
    BRepBuilderAPI_Sewing,
)
from OCP.Geom import Geom_BSplineSurface
from OCP.gp import gp_Pnt
from OCP.ShapeFix import ShapeFix_Shell, ShapeFix_Solid
from OCP.TopoDS import TopoDS

from .comparison import ComparisonReport, ComparisonSettings, compare_mesh_to_shape
from .fit_cache import CurvedFitCache, mesh_content_sha256
from .parameterization import (
    ChartParameterization,
    ChartParameterizationError,
    cut_chart_midline,
    harmonic_square_parameterization,
)
from .segmentation import SegmentationSettings, SurfacePatch, segment_mesh
from .surface_fit import (
    FitIteration,
    FittedPatch,
    PatchSystem,
    PoleConstraint,
    SurfaceFitSettings,
    fit_bspline_patch,
    greville_abscissae,
    open_uniform_knots,
    patch_distances,
    rectangle_boundary_poles,
    reproject_patch_uv,
    solve_patch_network,
)
from .surface_network import (
    NetworkCurve,
    NetworkPatch,
    NetworkVertex,
    SharedEdgeEvidence,
    SurfaceNetwork,
    build_network_faces,
    shared_edge_evidence,
)
from .validation import classify_face_surfaces, validate_shape


class CurvedPatchError(ValueError):
    """A fail-closed single-patch reconstruction error with a stable code."""

    def __init__(self, phase: str, code: str, message: str) -> None:
        super().__init__(message)
        self.phase = phase
        self.code = code


ProgressCallback = Callable[[str, float], None]


@dataclass(frozen=True, slots=True)
class ReconstructionBudget:
    """Hard resource ceilings; hitting one fails closed, never degrades output.

    Budgets only decide whether a run completes -- successful runs stay
    byte-deterministic. Direct RSS capping is intentionally absent: the
    services worker already spawn-isolates jobs, and ``maximum_solve_unknowns``
    bounds the dominant sparse-factorization memory in-process.
    """

    wall_clock_seconds: float = 120.0
    maximum_patches: int = 8
    maximum_total_control_points: int = 20_000
    maximum_solve_unknowns: int = 60_000

    def validate(self) -> None:
        if self.wall_clock_seconds <= 0.0:
            raise ValueError("wall clock budget must be positive")
        if self.maximum_patches < 1:
            raise ValueError("patch budget must allow at least one patch")
        if self.maximum_total_control_points < 16 or self.maximum_solve_unknowns < 16:
            raise ValueError("control point and unknown budgets are too small to fit anything")


class _StageGuard:
    """Cooperative cancellation, wall-clock budget, and stage progress."""

    def __init__(
        self,
        budget: ReconstructionBudget,
        progress: ProgressCallback | None,
        should_cancel: Callable[[], bool] | None,
    ) -> None:
        self._budget = budget
        self._progress = progress
        self._should_cancel = should_cancel
        self._started = time.monotonic()
        self._phase = "starting"

    def stage(self, phase: str, fraction: float) -> None:
        self._phase = phase
        self.checkpoint()
        if self._progress is not None:
            self._progress(phase, float(fraction))

    def checkpoint(self) -> None:
        if self._should_cancel is not None and self._should_cancel():
            raise CurvedPatchError(
                self._phase, "curved_patch_cancelled", "reconstruction was cancelled"
            )
        elapsed = time.monotonic() - self._started
        if elapsed > self._budget.wall_clock_seconds:
            raise CurvedPatchError(
                self._phase,
                "curved_patch_time_budget",
                (
                    f"wall clock budget of {self._budget.wall_clock_seconds:g} s exceeded "
                    f"after {elapsed:.1f} s"
                ),
            )


@dataclass(frozen=True, slots=True)
class CurvedPatchSettings:
    """Bounded, explicit budgets; nothing auto-raises a tolerance."""

    fit_tolerance_mm: float = 0.05
    surface_deviation_tolerance_mm: float = 0.25
    boundary_line_tolerance_mm: float = 0.05
    plane_parallel_tolerance_deg: float = 1.0
    sewing_tolerance_mm: float = 1e-3
    corner_turn_threshold_deg: float = 45.0
    segmentation: SegmentationSettings = field(default_factory=SegmentationSettings)
    fit: SurfaceFitSettings = field(default_factory=SurfaceFitSettings)
    comparison_sample_count: int = 1000
    # cadquery meshing treats deflection as relative to edge size, so a large
    # curved face needs a much smaller value than the faceted default to keep
    # the comparison mesh's own chordal error out of the measured deviation.
    comparison_tessellation: float = 0.002
    budget: ReconstructionBudget = field(default_factory=ReconstructionBudget)

    def validate(self) -> None:
        if self.fit_tolerance_mm <= 0.0 or self.surface_deviation_tolerance_mm <= 0.0:
            raise ValueError("tolerances must be positive")
        if self.boundary_line_tolerance_mm <= 0.0 or self.sewing_tolerance_mm <= 0.0:
            raise ValueError("boundary and sewing tolerances must be positive")
        if not 0.0 < self.plane_parallel_tolerance_deg < 90.0:
            raise ValueError("plane parallel tolerance must be in (0, 90) degrees")
        self.segmentation.validate()
        self.fit.validate()
        self.budget.validate()


@dataclass(frozen=True, slots=True)
class CurvedPatchResult:
    solid: cq.Shape
    chart: ChartParameterization
    fitted: FittedPatch
    corners: np.ndarray = field(repr=False)
    prism_vector: tuple[float, float, float]
    face_surfaces: dict[str, int]
    comparison: ComparisonReport
    segmentation_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": "approximate curved B-Rep, single freeform patch",
            "chart": self.chart.to_dict(),
            "fit": self.fitted.to_dict(),
            "corners": [list(map(float, corner)) for corner in self.corners],
            "prismVector": list(self.prism_vector),
            "faceSurfaces": dict(self.face_surfaces),
            "comparison": self.comparison.to_dict(),
            "segmentationCounts": dict(self.segmentation_counts),
            "limitations": [
                "The fitted surface is a tolerance-controlled approximation of the "
                "mesh, not the recovered original CAD surface.",
                "Only single-patch plate topology is supported at this milestone.",
            ],
        }


def _polygon_face(points: np.ndarray) -> cq.Shape:
    polygon = BRepBuilderAPI_MakePolygon()
    for point in points:
        polygon.Add(gp_Pnt(float(point[0]), float(point[1]), float(point[2])))
    polygon.Close()
    return cq.Shape.cast(BRepBuilderAPI_MakeFace(polygon.Wire(), True).Face())


def assemble_single_patch_plate(
    surface: Geom_BSplineSurface,
    corners: np.ndarray,
    prism_vector: np.ndarray,
    *,
    sewing_tolerance: float = 1e-3,
) -> cq.Shape:
    """Sew the freeform top, four planar walls, and planar bottom into a solid.

    The surface's natural boundary must geometrically equal the four
    corner-to-corner segments (guaranteed by collinear boundary poles), so
    sewing within the linear resolution joins shared edges without healing.
    """

    corners = np.asarray(corners, dtype=np.float64)
    vector = np.asarray(prism_vector, dtype=np.float64)
    if corners.shape != (4, 3):
        raise CurvedPatchError(
            "assembling solid", "curved_patch_invalid_corners", "expected four 3-D corners"
        )
    if not np.all(np.isfinite(vector)) or float(np.linalg.norm(vector)) <= 0.0:
        raise CurvedPatchError(
            "assembling solid",
            "curved_patch_invalid_prism",
            "prism vector must be finite and non-zero",
        )

    top = cq.Shape.cast(BRepBuilderAPI_MakeFace(surface, 1e-6).Face())
    faces = [top]
    lower = corners + vector
    for index in range(4):
        following = (index + 1) % 4
        faces.append(
            _polygon_face(
                np.asarray([corners[index], corners[following], lower[following], lower[index]])
            )
        )
    faces.append(_polygon_face(lower[::-1]))

    sewing = BRepBuilderAPI_Sewing(float(sewing_tolerance), True, True, True, False)
    for face in faces:
        sewing.Add(face.wrapped)
    sewing.Perform()
    if sewing.NbFreeEdges() != 0 or sewing.NbMultipleEdges() != 0:
        raise CurvedPatchError(
            "assembling solid",
            "curved_patch_sewing_incomplete",
            (
                f"sewing left {sewing.NbFreeEdges()} free edges and "
                f"{sewing.NbMultipleEdges()} multiply-connected edges"
            ),
        )
    shell_fix = ShapeFix_Shell()
    shell_fix.Init(TopoDS.Shell_s(sewing.SewedShape()))
    shell_fix.Perform()
    solid = cq.Shape.cast(ShapeFix_Solid().SolidFromShell(shell_fix.Shell()))
    if len(solid.Solids()) != 1 or not all(shell.Closed() for shell in solid.Shells()):
        raise CurvedPatchError(
            "assembling solid",
            "curved_patch_not_closed",
            "sewn faces did not produce one closed solid",
        )
    return solid


def _fit_line(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Least-squares 3-D line: centroid, unit direction, maximum deviation."""

    centroid = points.mean(axis=0)
    centered = points - centroid
    _, _, rotation = np.linalg.svd(centered, full_matrices=False)
    direction = rotation[0]
    deviation = np.linalg.norm(centered - np.outer(centered @ direction, direction), axis=1)
    return centroid, direction, float(deviation.max())


def _line_intersection(
    origin_a: np.ndarray,
    direction_a: np.ndarray,
    origin_b: np.ndarray,
    direction_b: np.ndarray,
) -> np.ndarray:
    """Midpoint of the common perpendicular of two nearly intersecting lines."""

    dot = float(direction_a @ direction_b)
    denominator = 1.0 - dot * dot
    if abs(denominator) < 1e-12:
        raise CurvedPatchError(
            "fitting boundary",
            "curved_patch_parallel_boundary",
            "adjacent boundary chains are parallel; no corner exists",
        )
    offset = origin_b - origin_a
    t = float((offset @ direction_a - dot * (offset @ direction_b)) / denominator)
    s = float((dot * (offset @ direction_a) - (offset @ direction_b)) / denominator)
    return np.asarray((origin_a + t * direction_a + origin_b + s * direction_b) / 2.0)


def _chain_positions(loop_length: int, start: int, end: int) -> np.ndarray:
    if end <= start:
        end += loop_length
    return np.arange(start, end + 1) % loop_length


def _freeform_patch(patches: tuple[SurfacePatch, ...]) -> SurfacePatch:
    freeform = [patch for patch in patches if patch.kind in ("freeform", "unknown")]
    if len(freeform) != 1:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_unsupported_topology",
            (
                f"single-patch reconstruction needs exactly one freeform region, "
                f"found {len(freeform)}"
            ),
        )
    patch = freeform[0]
    closed = [loop for loop in patch.boundary_loops if loop.closed]
    if len(closed) != len(patch.boundary_loops) or not closed:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_not_disk",
            "every freeform boundary loop must be closed (one outer, optional holes)",
        )
    return patch


def _plate_holes(
    patches: tuple[SurfacePatch, ...],
    freeform: SurfacePatch,
    hole_loops: list[np.ndarray],
) -> tuple[PlateHole, ...]:
    """Match each interior boundary loop to one recognized cylinder patch."""

    holes: list[PlateHole] = []
    for index, loop in enumerate(hole_loops):
        loop_vertices = set(int(vertex) for vertex in loop)
        matches = [
            patch
            for patch in patches
            if patch.kind == "cylinder" and loop_vertices & set(patch.vertex_ids)
        ]
        cylinder = matches[0] if len(matches) == 1 else None
        if cylinder is None or cylinder.cylinder_radius_mm is None:
            raise CurvedPatchError(
                "segmenting mesh",
                "curved_patch_hole_unrecognized",
                (
                    f"hole loop {index} does not border exactly one recognized "
                    f"cylinder (found {len(matches)})"
                ),
            )
        holes.append(
            PlateHole(
                radius=float(cylinder.cylinder_radius_mm),
                axis_point=np.asarray(cylinder.cylinder_axis_point, dtype=np.float64),
                axis=np.asarray(cylinder.cylinder_axis, dtype=np.float64),
                residual_p95=cylinder.residuals_mm.p95,
                patch_id=cylinder.id,
            )
        )
    return tuple(holes)


def _bottom_plane(
    patches: tuple[SurfacePatch, ...], freeform: SurfacePatch
) -> tuple[np.ndarray, np.ndarray]:
    planes = [patch for patch in patches if patch.kind == "plane"]
    detached = [patch for patch in planes if freeform.id not in patch.neighbor_ids]
    if len(detached) != 1:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_no_bottom_plane",
            (
                "expected exactly one planar region not adjacent to the freeform "
                f"patch (the bottom), found {len(detached)}"
            ),
        )
    bottom = detached[0]
    if bottom.plane_origin is None or bottom.plane_normal is None:
        raise CurvedPatchError(
            "segmenting mesh", "curved_patch_no_bottom_plane", "bottom plane fit is missing"
        )
    return (
        np.asarray(bottom.plane_origin, dtype=np.float64),
        np.asarray(bottom.plane_normal, dtype=np.float64),
    )


def chart_lattice_samples(
    vertices: np.ndarray, faces: np.ndarray, uv: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vertices plus an area-scaled barycentric lattice of interior samples.

    Large boundary fan triangles (straight crease edges never subdivide)
    would otherwise leave whole knot spans without data.
    """

    chart_mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False, validate=False)
    face_areas = np.asarray(chart_mesh.area_faces, dtype=np.float64)
    vertex_weights = np.zeros(len(vertices))
    for column in range(3):
        np.add.at(vertex_weights, faces[:, column], face_areas / 3.0)

    median_area = float(np.median(face_areas[face_areas > 0.0]))
    lattice_uv: list[np.ndarray] = [uv]
    lattice_points: list[np.ndarray] = [vertices]
    lattice_weights: list[np.ndarray] = [vertex_weights]
    levels = np.clip(np.ceil(np.sqrt(face_areas / max(median_area, 1e-300))).astype(np.int64), 1, 8)
    for level in np.unique(levels):
        selected = np.flatnonzero(levels == level)
        interior = [
            (i / (level + 2), j / (level + 2), (level + 2 - i - j) / (level + 2))
            for i in range(1, level + 2)
            for j in range(1, level + 2 - i)
        ]
        if not interior:
            continue
        barycentric = np.asarray(interior, dtype=np.float64)
        triangle_uv = uv[faces[selected]]
        triangle_points = vertices[faces[selected]]
        lattice_uv.append(np.einsum("kb,tbc->tkc", barycentric, triangle_uv).reshape(-1, 2))
        lattice_points.append(np.einsum("kb,tbc->tkc", barycentric, triangle_points).reshape(-1, 3))
        lattice_weights.append(np.repeat(face_areas[selected] / len(barycentric), len(barycentric)))
    sample_uv = np.concatenate(lattice_uv)
    sample_points = np.concatenate(lattice_points)
    sample_weights = np.concatenate(lattice_weights)
    return sample_uv, sample_points, sample_weights


def reconstruct_single_patch_plate(
    mesh: trimesh.Trimesh,
    *,
    settings: CurvedPatchSettings | None = None,
) -> CurvedPatchResult:
    """Reconstruct one freeform-topped plate as an approximate curved B-Rep."""

    settings = settings or CurvedPatchSettings()
    settings.validate()

    context = _plate_context(mesh, settings)
    if context.holes:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_holes_unsupported",
            "single-patch reconstruction does not support holes; use reconstruct_plate_network",
        )
    chart = context.chart
    corners = context.corners
    prism_vector = context.prism_vector

    sample_uv, sample_points, sample_weights = chart_lattice_samples(
        context.chart_vertices, context.chart_faces, chart.uv
    )
    valid = sample_weights > 0.0
    fitted = fit_bspline_patch(
        sample_uv[valid],
        sample_points[valid],
        sample_weights[valid],
        settings.fit_tolerance_mm,
        settings=settings.fit,
        rectangle_corners=corners,
    )
    if not fitted.converged:
        raise CurvedPatchError(
            "fitting surface",
            "curved_patch_tolerance_not_met",
            (
                f"maximum fit residual {fitted.maximum_distance:g} mm exceeds "
                f"{settings.fit_tolerance_mm:g} mm within the span budget"
            ),
        )

    solid = assemble_single_patch_plate(
        fitted.to_occt_surface(),
        corners,
        prism_vector,
        sewing_tolerance=settings.sewing_tolerance_mm,
    )
    shape_validation = validate_shape(solid)
    if not shape_validation.valid:
        raise CurvedPatchError(
            "validating solid",
            "curved_patch_invalid_brep",
            "; ".join(shape_validation.errors),
        )
    face_surfaces = classify_face_surfaces(solid)
    if face_surfaces["bspline"] < 1:
        raise CurvedPatchError(
            "validating solid",
            "curved_patch_no_bspline_face",
            "the reconstructed solid lost its B-spline face",
        )

    comparison = compare_mesh_to_shape(
        mesh,
        solid,
        settings=ComparisonSettings(
            sample_count_each_direction=settings.comparison_sample_count,
            linear_tessellation_mm=settings.comparison_tessellation,
        ),
    )
    if comparison.maximum_distance_mm > settings.surface_deviation_tolerance_mm:
        raise CurvedPatchError(
            "validating solid",
            "curved_patch_deviation_exceeded",
            (
                f"maximum source deviation {comparison.maximum_distance_mm:g} mm "
                f"exceeds {settings.surface_deviation_tolerance_mm:g} mm"
            ),
        )

    return CurvedPatchResult(
        solid=solid,
        chart=chart,
        fitted=fitted,
        corners=corners,
        prism_vector=(
            float(prism_vector[0]),
            float(prism_vector[1]),
            float(prism_vector[2]),
        ),
        face_surfaces=face_surfaces,
        comparison=comparison,
        segmentation_counts=context.segmentation_counts,
    )


@dataclass(frozen=True, slots=True)
class CurvedNetworkSettings:
    """Milestone 2 additions: split control and continuity gates."""

    force_split: bool = False
    g1_maximum_angle_deg: float = 1.0
    coupling_weight: float = 10.0
    curve_fairness: float = 1e-3
    evidence_sample_count: int = 64
    solve_rounds: int = 2

    def validate(self) -> None:
        if not 0.0 < self.g1_maximum_angle_deg < 90.0:
            raise ValueError("G1 gate must be in (0, 90) degrees")
        if self.coupling_weight < 0.0 or self.curve_fairness < 0.0:
            raise ValueError("coupling weight and curve fairness must be non-negative")
        if self.evidence_sample_count < 2 or self.solve_rounds < 1:
            raise ValueError("evidence samples and solve rounds must be positive")


@dataclass(frozen=True, slots=True)
class CurvedNetworkResult:
    solid: cq.Shape
    network: SurfaceNetwork
    artifact_sha256: str
    charts: tuple[ChartParameterization, ...]
    iterations: tuple[FitIteration, ...]
    residual_maximum: float
    residual_rms: float
    shared_evidence: tuple[SharedEdgeEvidence, ...]
    face_surfaces: dict[str, int]
    comparison: ComparisonReport
    corners: np.ndarray = field(repr=False)
    prism_vector: tuple[float, float, float]
    holes: tuple[PlateHole, ...] = ()
    hole_cutters: tuple[HoleCutter, ...] = ()
    candidates: tuple[dict[str, Any], ...] = ()
    cache_status: str = "uncached"
    sewing_tolerance_mm: float = 1e-3

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": "approximate curved B-Rep, shared-topology patch network",
            "artifactSha256": self.artifact_sha256,
            "network": self.network.to_artifact(),
            "charts": [chart.to_dict() for chart in self.charts],
            "iterations": [iteration.to_dict() for iteration in self.iterations],
            "residualMaximum": self.residual_maximum,
            "residualRms": self.residual_rms,
            "sharedEdges": [evidence.to_dict() for evidence in self.shared_evidence],
            "faceSurfaces": dict(self.face_surfaces),
            "comparison": self.comparison.to_dict(),
            "corners": [list(map(float, corner)) for corner in self.corners],
            "prismVector": list(self.prism_vector),
            "holes": [hole.to_dict() for hole in self.holes],
            "candidates": [dict(candidate) for candidate in self.candidates],
            "cacheStatus": self.cache_status,
            "limitations": [
                "The fitted network is a tolerance-controlled approximation of the "
                "mesh, not the recovered original CAD surfaces.",
                "Plate topology only: straight outer creases over a planar bottom.",
            ],
        }


@dataclass(frozen=True, slots=True)
class PlateHole:
    """A recognized analytic through-hole cylinder piercing the plate."""

    radius: float
    axis_point: np.ndarray = field(repr=False)
    axis: np.ndarray = field(repr=False)
    residual_p95: float
    patch_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "cylinder",
            "radiusMm": self.radius,
            "axisPoint": [float(value) for value in self.axis_point],
            "axis": [float(value) for value in self.axis],
            "residualP95Mm": self.residual_p95,
            "patchId": self.patch_id,
        }


@dataclass(frozen=True, slots=True)
class _PlateContext:
    chart_vertices: np.ndarray
    chart_faces: np.ndarray
    chart_loop: np.ndarray
    chart: ChartParameterization
    lines: tuple[tuple[np.ndarray, np.ndarray], ...]
    corners: np.ndarray
    rectangle_normal: np.ndarray
    prism_vector: np.ndarray
    segmentation_counts: dict[str, int]
    holes: tuple[PlateHole, ...] = ()
    hole_loops: tuple[np.ndarray, ...] = ()


def _plate_context(mesh: trimesh.Trimesh, settings: CurvedPatchSettings) -> _PlateContext:
    """Segment, extract, parameterize, and bound the plate's freeform chart."""

    segmentation = segment_mesh(mesh, settings.segmentation)
    freeform = _freeform_patch(segmentation.patches)
    bottom_origin, bottom_normal = _bottom_plane(segmentation.patches, freeform)

    triangle_ids = np.asarray(freeform.triangle_ids, dtype=np.int64)
    chart_faces_global = np.asarray(mesh.faces, dtype=np.int64)[triangle_ids]
    used_vertices = np.unique(chart_faces_global)
    local_index = np.full(len(mesh.vertices), -1, dtype=np.int64)
    local_index[used_vertices] = np.arange(len(used_vertices))
    chart_vertices = np.asarray(mesh.vertices, dtype=np.float64)[used_vertices]
    chart_faces = local_index[chart_faces_global]

    # The outer boundary is the loop with the largest 3-D perimeter; every
    # other closed loop is an interior hole matched to an analytic patch.
    mesh_vertices = np.asarray(mesh.vertices, dtype=np.float64)

    def perimeter(loop: np.ndarray) -> float:
        points = mesh_vertices[loop]
        return float(np.linalg.norm(np.diff(np.vstack([points, points[:1]]), axis=0), axis=1).sum())

    loops_global = [np.asarray(loop.vertex_ids, dtype=np.int64) for loop in freeform.boundary_loops]
    outer_index = int(np.argmax([perimeter(loop) for loop in loops_global]))
    loop_global = loops_global[outer_index]
    hole_loops = [loop for index, loop in enumerate(loops_global) if index != outer_index]
    holes = _plate_holes(segmentation.patches, freeform, hole_loops)

    chart_loop = local_index[loop_global]
    hole_loops_local = tuple(local_index[loop] for loop in hole_loops)
    if np.any(chart_loop < 0) or any(np.any(loop < 0) for loop in hole_loops_local):
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_boundary_mismatch",
            "a freeform boundary loop references vertices outside the region",
        )

    try:
        chart = harmonic_square_parameterization(
            chart_vertices,
            chart_faces,
            chart_loop,
            minimum_turn_deg=settings.corner_turn_threshold_deg,
        )
    except ChartParameterizationError as exc:
        raise CurvedPatchError("parameterizing chart", exc.code, str(exc)) from exc

    corner_positions = np.asarray(chart.corner_loop_positions, dtype=np.int64)
    lines: list[tuple[np.ndarray, np.ndarray]] = []
    for chain in range(4):
        positions = _chain_positions(
            len(chart_loop),
            int(corner_positions[chain]),
            int(corner_positions[(chain + 1) % 4]),
        )
        centroid, direction, deviation = _fit_line(chart_vertices[chart_loop[positions]])
        if deviation > settings.boundary_line_tolerance_mm:
            raise CurvedPatchError(
                "fitting boundary",
                "curved_patch_boundary_not_straight",
                (
                    f"boundary chain {chain} deviates {deviation:g} mm from a line "
                    f"(limit {settings.boundary_line_tolerance_mm:g} mm)"
                ),
            )
        lines.append((centroid, direction))
    corners = np.asarray(
        [_line_intersection(*lines[(chain - 1) % 4], *lines[chain]) for chain in range(4)]
    )

    rectangle_normal = np.cross(corners[1] - corners[0], corners[3] - corners[0])
    normal_length = float(np.linalg.norm(rectangle_normal))
    if normal_length <= 0.0:
        raise CurvedPatchError(
            "fitting boundary",
            "curved_patch_degenerate_rectangle",
            "corner rectangle is degenerate",
        )
    rectangle_normal = rectangle_normal / normal_length
    coplanarity = abs(float((corners[2] - corners[0]) @ rectangle_normal))
    if coplanarity > settings.boundary_line_tolerance_mm:
        raise CurvedPatchError(
            "fitting boundary",
            "curved_patch_boundary_not_planar",
            f"boundary corners deviate {coplanarity:g} mm from a common plane",
        )

    alignment = abs(float(rectangle_normal @ bottom_normal))
    if alignment < np.cos(np.radians(settings.plane_parallel_tolerance_deg)):
        raise CurvedPatchError(
            "assembling solid",
            "curved_patch_bottom_not_parallel",
            "the bottom plane is not parallel to the boundary rectangle",
        )
    height = float((bottom_origin - corners[0]) @ rectangle_normal)
    if abs(height) <= settings.sewing_tolerance_mm:
        raise CurvedPatchError(
            "assembling solid",
            "curved_patch_zero_height",
            "the bottom plane coincides with the boundary rectangle",
        )

    for index, hole in enumerate(holes):
        if abs(float(hole.axis @ rectangle_normal)) < np.cos(
            np.radians(settings.plane_parallel_tolerance_deg)
        ):
            raise CurvedPatchError(
                "segmenting mesh",
                "curved_patch_hole_not_normal",
                f"hole {index} axis is not perpendicular to the plate",
            )

    counts = dict(segmentation.counts_by_type)
    return _PlateContext(
        chart_vertices=chart_vertices,
        chart_faces=chart_faces,
        chart_loop=chart_loop,
        chart=chart,
        lines=tuple(lines),
        corners=corners,
        rectangle_normal=rectangle_normal,
        prism_vector=rectangle_normal * height,
        segmentation_counts=counts,
        holes=holes,
        hole_loops=hole_loops_local,
    )


def _hole_fill_samples(
    chart: ChartParameterization,
    vertices: np.ndarray,
    hole_loops: tuple[np.ndarray, ...],
    base_weight: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Weak synthetic samples across hole interiors.

    Holes carry no mesh data, and fairness alone lets the free poles inside
    them run away (the surface balloons and the trimming boolean then severs
    it into a second solid). A concentric blend of each rim toward its
    centroid pins the extrapolation without competing with real samples: the
    fill weight is a small fraction of the real sample weight and the region
    is trimmed away by the recognized hole anyway.
    """

    fill_uv: list[np.ndarray] = []
    fill_points: list[np.ndarray] = []
    for loop in hole_loops:
        rim_uv = chart.uv[loop]
        rim_points = vertices[loop]
        centroid_uv = rim_uv.mean(axis=0)
        centroid_point = rim_points.mean(axis=0)
        fill_uv.append(centroid_uv[None, :])
        fill_points.append(centroid_point[None, :])
        step = max(1, len(loop) // 12)
        selected = np.arange(0, len(loop), step)
        for fraction in (0.35, 0.7):
            fill_uv.append(centroid_uv + fraction * (rim_uv[selected] - centroid_uv))
            fill_points.append(centroid_point + fraction * (rim_points[selected] - centroid_point))
    if not fill_uv:
        empty = np.zeros((0, 3))
        return np.zeros((0, 2)), empty, np.zeros(0)
    uv = np.concatenate(fill_uv)
    points = np.concatenate(fill_points)
    weights = np.full(len(uv), base_weight)
    return uv, points, weights


@dataclass(frozen=True, slots=True)
class HoleCutter:
    """Exact boolean cutter for a recognized hole, recorded for replay.

    The cutter's base point and height enter the resulting cylinder face's
    underlying surface placement, so replays (fit cache, compiler rebuild)
    must reuse the recorded cutter verbatim to stay byte-deterministic.
    """

    radius: float
    base_point: tuple[float, float, float]
    direction: tuple[float, float, float]
    height: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "radiusMm": self.radius,
            "basePoint": list(self.base_point),
            "direction": list(self.direction),
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> HoleCutter:
        return cls(
            radius=float(payload["radiusMm"]),
            base_point=(
                float(payload["basePoint"][0]),
                float(payload["basePoint"][1]),
                float(payload["basePoint"][2]),
            ),
            direction=(
                float(payload["direction"][0]),
                float(payload["direction"][1]),
                float(payload["direction"][2]),
            ),
            height=float(payload["height"]),
        )


def _hole_cutters(holes: tuple[PlateHole, ...], mesh: trimesh.Trimesh) -> tuple[HoleCutter, ...]:
    """Derive each hole's boolean cutter from the source-mesh extent once."""

    cutters: list[HoleCutter] = []
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    for hole in holes:
        axis = hole.axis / float(np.linalg.norm(hole.axis))
        projections = vertices @ axis
        extent = float(projections.max() - projections.min())
        pad = max(1.0, 0.1 * extent)
        base = (
            hole.axis_point
            + (float(projections.min()) - float(hole.axis_point @ axis) - pad) * axis
        )
        cutters.append(
            HoleCutter(
                radius=float(hole.radius),
                base_point=(float(base[0]), float(base[1]), float(base[2])),
                direction=(float(axis[0]), float(axis[1]), float(axis[2])),
                height=extent + 2.0 * pad,
            )
        )
    return tuple(cutters)


def _subtract_holes(solid: cq.Shape, cutters: tuple[HoleCutter, ...]) -> cq.Shape:
    """Boolean-subtract each recorded hole cutter from the plate solid.

    The kernel computes the exact intersection curves and pcurves, so the
    trimmed B-spline top, the analytic cylinder, and the planes share one
    valid shell without approximation on our side.
    """

    result = solid
    for index, cutter_spec in enumerate(cutters):
        cutter = cq.Solid.makeCylinder(
            cutter_spec.radius,
            cutter_spec.height,
            cq.Vector(*cutter_spec.base_point),
            cq.Vector(*cutter_spec.direction),
        )
        try:
            result = result.cut(cutter)
        except Exception as exc:
            raise CurvedPatchError(
                "assembling solid",
                "curved_patch_hole_boolean_failed",
                f"subtracting hole {index} failed: {exc}",
            ) from exc
        if len(result.Solids()) != 1:
            raise CurvedPatchError(
                "assembling solid",
                "curved_patch_hole_boolean_failed",
                f"subtracting hole {index} split the plate into multiple solids",
            )
    return result


def _plate_solid_from_network(
    network: SurfaceNetwork,
    corners: np.ndarray,
    prism_vector: np.ndarray,
    cutters: tuple[HoleCutter, ...],
    sewing_tolerance: float,
) -> cq.Shape:
    """The single assembly path shared by the driver, cache, and compiler.

    Wall chains derive from the network itself: a split network carries its
    cut endpoints as the ``cut-0-start``/``cut-0-end`` vertices.
    """

    if network.curves:
        mid_start = np.asarray(network.vertex("cut-0-start").point, dtype=np.float64)
        mid_end = np.asarray(network.vertex("cut-0-end").point, dtype=np.float64)
        wall_chains = [
            [corners[0], mid_start, corners[1]],
            [corners[1], corners[2]],
            [corners[2], mid_end, corners[3]],
            [corners[3], corners[0]],
        ]
    else:
        wall_chains = [[corners[k], corners[(k + 1) % 4]] for k in range(4)]
    solid = _network_plate_solid(network, wall_chains, corners, prism_vector, sewing_tolerance)
    return _subtract_holes(solid, cutters)


def _project_to_line(point: np.ndarray, line: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    centroid, direction = line
    return np.asarray(centroid + float((point - centroid) @ direction) * direction)


def _network_distances(
    uv_state: list[np.ndarray],
    samples: list[tuple[np.ndarray, np.ndarray, np.ndarray]],
    poles: list[np.ndarray],
    knots: np.ndarray,
    degree: int,
    steps: int,
) -> np.ndarray:
    """Distance of every sample to the closest patch of the network.

    The discrete cut path zig-zags around the smooth emergent boundary curve,
    so samples adjacent to the cut can land on the neighbor patch's side of
    the shared curve; measuring against one patch alone would misreport a
    perfectly covered point as an error.
    """

    per_patch: list[np.ndarray] = []
    boundary_u = (1.0, 0.0)
    for side in range(2):
        own = patch_distances(uv_state[side], samples[side][1], poles[side], knots, knots, degree)
        other = 1 - side
        seed = np.column_stack([np.full(len(own), boundary_u[other]), uv_state[side][:, 1]])
        seed = reproject_patch_uv(
            seed, samples[side][1], poles[other], knots, knots, degree, steps=steps + 2
        )
        across = patch_distances(seed, samples[side][1], poles[other], knots, knots, degree)
        per_patch.append(np.minimum(own, across))
    return np.concatenate(per_patch)


def _solidify_faces(faces: list[Any], sewing_tolerance: float) -> cq.Shape:
    """Sew prepared faces and demand exactly one closed solid."""

    sewing = BRepBuilderAPI_Sewing(float(sewing_tolerance), True, True, True, False)
    for face in faces:
        sewing.Add(face)
    sewing.Perform()
    if sewing.NbFreeEdges() != 0 or sewing.NbMultipleEdges() != 0:
        raise CurvedPatchError(
            "assembling solid",
            "curved_patch_sewing_incomplete",
            (
                f"sewing left {sewing.NbFreeEdges()} free edges and "
                f"{sewing.NbMultipleEdges()} multiply-connected edges"
            ),
        )
    shell_fix = ShapeFix_Shell()
    shell_fix.Init(TopoDS.Shell_s(sewing.SewedShape()))
    shell_fix.Perform()
    solid = cq.Shape.cast(ShapeFix_Solid().SolidFromShell(shell_fix.Shell()))
    if len(solid.Solids()) != 1 or not all(shell.Closed() for shell in solid.Shells()):
        raise CurvedPatchError(
            "assembling solid",
            "curved_patch_not_closed",
            "sewn faces did not produce one closed solid",
        )
    return solid


def _network_plate_solid(
    network: SurfaceNetwork,
    wall_chains: list[list[np.ndarray]],
    corners: np.ndarray,
    prism_vector: np.ndarray,
    sewing_tolerance: float,
) -> cq.Shape:
    faces, _ = build_network_faces(network)
    all_faces: list[Any] = list(faces)
    for chain_points in wall_chains:
        polygon = [
            *chain_points,
            chain_points[-1] + prism_vector,
            chain_points[0] + prism_vector,
        ]
        all_faces.append(_polygon_face(np.asarray(polygon)).wrapped)
    all_faces.append(_polygon_face((corners + prism_vector)[::-1]).wrapped)
    return _solidify_faces(all_faces, sewing_tolerance)


def _network_gates(
    mesh: trimesh.Trimesh,
    solid: cq.Shape,
    network: SurfaceNetwork,
    settings: CurvedPatchSettings,
    network_settings: CurvedNetworkSettings,
    *,
    expected_cylinders: int = 0,
) -> tuple[dict[str, int], ComparisonReport, tuple[SharedEdgeEvidence, ...]]:
    shape_validation = validate_shape(solid)
    if not shape_validation.valid:
        raise CurvedPatchError(
            "validating solid",
            "curved_patch_invalid_brep",
            "; ".join(shape_validation.errors),
        )
    face_surfaces = classify_face_surfaces(solid)
    if face_surfaces["bspline"] < len(network.patches):
        raise CurvedPatchError(
            "validating solid",
            "curved_patch_no_bspline_face",
            (f"expected {len(network.patches)} B-spline faces, found {face_surfaces['bspline']}"),
        )
    if face_surfaces["cylinder"] != expected_cylinders:
        raise CurvedPatchError(
            "validating solid",
            "curved_patch_hole_faces_mismatch",
            (
                f"expected {expected_cylinders} cylinder faces from recognized holes, "
                f"found {face_surfaces['cylinder']}"
            ),
        )
    evidence = shared_edge_evidence(network, sample_count=network_settings.evidence_sample_count)
    for entry in evidence:
        if entry.maximum_position_gap > settings.sewing_tolerance_mm:
            raise CurvedPatchError(
                "validating solid",
                "curved_patch_g0_gap",
                (
                    f"shared curve {entry.curve_id!r} G0 gap {entry.maximum_position_gap:g} "
                    f"exceeds the sewing tolerance"
                ),
            )
        if (
            entry.continuity == "smooth"
            and entry.maximum_normal_angle_deg > network_settings.g1_maximum_angle_deg
        ):
            raise CurvedPatchError(
                "validating solid",
                "curved_patch_g1_angle",
                (
                    f"shared curve {entry.curve_id!r} tangent mismatch "
                    f"{entry.maximum_normal_angle_deg:g} deg exceeds "
                    f"{network_settings.g1_maximum_angle_deg:g} deg"
                ),
            )
    comparison = compare_mesh_to_shape(
        mesh,
        solid,
        settings=ComparisonSettings(
            sample_count_each_direction=settings.comparison_sample_count,
            linear_tessellation_mm=settings.comparison_tessellation,
        ),
    )
    if comparison.maximum_distance_mm > settings.surface_deviation_tolerance_mm:
        raise CurvedPatchError(
            "validating solid",
            "curved_patch_deviation_exceeded",
            (
                f"maximum source deviation {comparison.maximum_distance_mm:g} mm "
                f"exceeds {settings.surface_deviation_tolerance_mm:g} mm"
            ),
        )
    return face_surfaces, comparison, evidence


def reconstruct_plate_network(
    mesh: trimesh.Trimesh,
    *,
    settings: CurvedPatchSettings | None = None,
    network_settings: CurvedNetworkSettings | None = None,
    progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
    fit_cache: CurvedFitCache | None = None,
    source_sha256: str | None = None,
) -> CurvedNetworkResult:
    """Reconstruct a plate as a shared-topology patch network.

    Fits one patch when the budget allows it; otherwise (or when forced) cuts
    the chart along a deterministic interior path, fits the shared boundary
    curve once, fits both patches jointly with a C1 coupling across the
    artificial smooth boundary, and assembles everything on a common OCCT
    edge with exact iso pcurves.
    """

    settings = settings or CurvedPatchSettings()
    settings.validate()
    network_settings = network_settings or CurvedNetworkSettings()
    network_settings.validate()
    guard = _StageGuard(settings.budget, progress, should_cancel)

    guard.stage("segmenting mesh", 5.0)
    context = _plate_context(mesh, settings)
    guard.stage("parameterizing chart", 20.0)
    corners = context.corners
    degree = settings.fit.degree
    corner_vertices = tuple(NetworkVertex(f"corner-{index}", corners[index]) for index in range(4))

    # Budgets translate into a hard span clamp: total control points and solve
    # unknowns both scale with (spans + degree)^2 per patch.
    pole_cap = min(
        settings.budget.maximum_total_control_points,
        settings.budget.maximum_solve_unknowns,
    )
    budget_fit = replace(
        settings.fit,
        maximum_spans=max(
            settings.fit.initial_spans,
            min(settings.fit.maximum_spans, math.isqrt(pole_cap) - degree),
        ),
    )

    cache_key: str | None = None
    if fit_cache is not None:
        cache_key = fit_cache.key(
            source_sha256 or mesh_content_sha256(mesh),
            settings,
            network_settings,
            (context.chart_vertices, context.chart_faces),
        )
        cached = fit_cache.load(cache_key)
        if cached is not None:
            guard.stage("assembling solid", 70.0)
            return _assemble_cached_network(
                mesh, context, cached, settings, network_settings, guard, cache_key
            )

    # Always evaluate the single-patch layout so the choice between layouts is
    # an explicit, retained score rather than an implicit code path.
    guard.stage("fitting surface", 35.0)
    candidates: list[dict[str, Any]] = []
    sample_uv, sample_points, sample_weights = chart_lattice_samples(
        context.chart_vertices, context.chart_faces, context.chart.uv
    )
    valid = sample_weights > 0.0
    sample_uv = sample_uv[valid]
    sample_points = sample_points[valid]
    sample_weights = sample_weights[valid]
    real_sample_count = len(sample_uv)
    if context.hole_loops:
        fill_weight = 0.05 * float(np.median(sample_weights))
        fill_uv, fill_points, fill_weights = _hole_fill_samples(
            context.chart, context.chart_vertices, context.hole_loops, fill_weight
        )
        sample_uv = np.concatenate([sample_uv, fill_uv])
        sample_points = np.concatenate([sample_points, fill_points])
        sample_weights = np.concatenate([sample_weights, fill_weights])
    fitted = fit_bspline_patch(
        sample_uv,
        sample_points,
        sample_weights,
        settings.fit_tolerance_mm,
        settings=budget_fit,
        rectangle_corners=corners,
        gate_count=real_sample_count,
        checkpoint=guard.checkpoint,
    )
    candidates.append(
        {
            "layout": "single-patch",
            "converged": fitted.converged,
            "residualMaximum": fitted.maximum_distance,
            "residualRms": fitted.rms_distance,
            "controlPoints": fitted.control_u * fitted.control_v,
            "chosen": False,
        }
    )

    if fitted.converged and not network_settings.force_split:
        candidates[0]["chosen"] = True
        patch = NetworkPatch(
            id="patch-0",
            degree=degree,
            knots_u=fitted.knots_u,
            knots_v=fitted.knots_v,
            poles=fitted.poles,
            corner_vertex_ids=("corner-0", "corner-1", "corner-2", "corner-3"),
        )
        network = SurfaceNetwork(units="mm", vertices=corner_vertices, curves=(), patches=(patch,))
        guard.stage("assembling solid", 70.0)
        cutters = _hole_cutters(context.holes, mesh)
        solid = _plate_solid_from_network(
            network, corners, context.prism_vector, cutters, settings.sewing_tolerance_mm
        )
        guard.stage("validating solid", 90.0)
        face_surfaces, comparison, evidence = _network_gates(
            mesh,
            solid,
            network,
            settings,
            network_settings,
            expected_cylinders=len(context.holes),
        )
        if fit_cache is not None and cache_key is not None:
            fit_cache.store(
                cache_key,
                _fit_cache_payload(
                    "single-patch",
                    network,
                    fitted.iterations,
                    candidates,
                    fitted.maximum_distance,
                    fitted.rms_distance,
                ),
            )
        guard.stage("finished", 100.0)
        return CurvedNetworkResult(
            solid=solid,
            network=network,
            artifact_sha256=network.artifact_sha256(),
            charts=(context.chart,),
            iterations=fitted.iterations,
            residual_maximum=fitted.maximum_distance,
            residual_rms=fitted.rms_distance,
            shared_evidence=evidence,
            face_surfaces=face_surfaces,
            comparison=comparison,
            corners=corners,
            prism_vector=(
                float(context.prism_vector[0]),
                float(context.prism_vector[1]),
                float(context.prism_vector[2]),
            ),
            holes=context.holes,
            hole_cutters=cutters,
            candidates=tuple(candidates),
            cache_status="stored" if fit_cache is not None else "uncached",
            sewing_tolerance_mm=settings.sewing_tolerance_mm,
        )

    if context.holes:
        raise CurvedPatchError(
            "cutting chart",
            "curved_patch_holes_unsupported_split",
            "chart cutting across regions with holes is not supported yet; the "
            "single-patch layout did not meet tolerance",
        )

    if settings.budget.maximum_patches < 2:
        raise CurvedPatchError(
            "cutting chart",
            "curved_patch_patch_budget",
            "the patch budget does not allow splitting into a two-patch network",
        )

    # Split path: cut the chart, fit the shared curve once, fit both patches
    # jointly with C1 coupling across the artificial smooth boundary.
    guard.stage("cutting chart", 45.0)
    try:
        cut = cut_chart_midline(context.chart_vertices, context.chart_faces, context.chart)
        halves = (cut.half_a, cut.half_b)
        charts = tuple(
            harmonic_square_parameterization(
                half.vertices,
                half.faces,
                half.boundary_loop,
                corner_loop_positions=np.asarray(half.corner_positions, dtype=np.int64),
            )
            for half in halves
        )
    except ChartParameterizationError as exc:
        raise CurvedPatchError("cutting chart", exc.code, str(exc)) from exc

    path_points = cut.path_points.copy()
    path_points[0] = _project_to_line(path_points[0], context.lines[0])
    path_points[-1] = _project_to_line(path_points[-1], context.lines[2])
    mid_start, mid_end = path_points[0], path_points[-1]
    chord = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(path_points, axis=0), axis=1))])
    if chord[-1] <= 0.0:
        raise CurvedPatchError(
            "cutting chart", "curved_patch_degenerate_cut", "the cut path has zero length"
        )
    half_corners = (
        np.asarray([corners[0], mid_start, mid_end, corners[3]]),
        np.asarray([mid_start, corners[1], corners[2], mid_end]),
    )
    samples = []
    for half, chart in zip(halves, charts, strict=True):
        sample_uv, sample_points, sample_weights = chart_lattice_samples(
            half.vertices, half.faces, chart.uv
        )
        keep = sample_weights > 0.0
        samples.append((sample_uv[keep], sample_points[keep], sample_weights[keep]))

    smallest = min(len(points) for _, points, _ in samples)
    sample_span_cap = max(1, int(np.sqrt(smallest / 2.0)) - degree)
    budget_span_cap = max(1, math.isqrt(pole_cap // 2) - degree)
    maximum_spans = max(
        settings.fit.initial_spans,
        min(settings.fit.maximum_spans, sample_span_cap, budget_span_cap),
    )
    spans = settings.fit.initial_spans
    iterations: list[FitIteration] = []
    best: tuple[list[np.ndarray], np.ndarray, np.ndarray] | None = None
    for _ in range(settings.fit.maximum_refinements + 1):
        guard.checkpoint()
        control = spans + degree
        knots = open_uniform_knots(control, degree)
        greville = greville_abscissae(knots, degree)
        # Pin the three straight outer edges of each half; the shared cut
        # boundary stays a FREE pole row aliased across both patches, so the
        # shared curve emerges from the joint fit lying on the surface instead
        # of chasing the zig-zag of the discrete cut path.
        fixed_sets: list[dict[tuple[int, int], np.ndarray]] = []
        for side, side_corners in enumerate(half_corners):
            fixed = rectangle_boundary_poles(side_corners, greville, greville)
            for j in range(1, control - 1):
                del fixed[(control - 1, j) if side == 0 else (0, j)]
            fixed_sets.append(fixed)
        shared_poles = [((0, (control - 1, j)), (1, (0, j))) for j in range(control)]
        constraints = [
            PoleConstraint(
                entries=(
                    (0, (control - 2, j), 1.0),
                    (1, (1, j), 1.0),
                    (0, (control - 1, j), -2.0),
                ),
                target=np.zeros(3),
            )
            for j in range(control)
        ]

        uv_state = [sample[0].copy() for sample in samples]
        poles: list[np.ndarray] = []
        for _ in range(network_settings.solve_rounds):
            systems = [
                PatchSystem(
                    uv=uv_state[side],
                    points=samples[side][1],
                    weights=samples[side][2],
                    fixed_poles=fixed_sets[side],
                )
                for side in range(2)
            ]
            poles = solve_patch_network(
                systems,
                knots,
                knots,
                degree,
                fairness=settings.fit.fairness,
                shared_poles=shared_poles,
                constraints=constraints,
                constraint_weight=network_settings.coupling_weight,
            )
            uv_state = [
                reproject_patch_uv(
                    uv_state[side],
                    samples[side][1],
                    poles[side],
                    knots,
                    knots,
                    degree,
                    steps=settings.fit.reprojection_steps,
                )
                for side in range(2)
            ]
        residuals = _network_distances(
            uv_state, samples, poles, knots, degree, settings.fit.reprojection_steps
        )
        iterations.append(
            FitIteration(
                spans_u=spans,
                spans_v=spans,
                rms_distance=float(np.sqrt(np.mean(residuals**2))),
                p95_distance=float(np.percentile(residuals, 95)),
                maximum_distance=float(residuals.max()),
            )
        )
        best = (poles, knots, residuals)
        if residuals.max() <= settings.fit_tolerance_mm:
            break
        if spans >= maximum_spans:
            break
        spans = min(spans * 2, maximum_spans)

    assert best is not None
    poles, knots, residuals = best
    # Both patches carry identical shared-boundary poles by aliasing; that
    # pole row IS the shared curve.
    curve_poles = np.asarray(poles[0][-1], dtype=np.float64)
    control = len(knots) - degree - 1
    candidates.append(
        {
            "layout": "split-network",
            "converged": bool(residuals.max() <= settings.fit_tolerance_mm),
            "residualMaximum": float(residuals.max()),
            "residualRms": float(np.sqrt(np.mean(residuals**2))),
            "controlPoints": 2 * control * control - control,
            "chosen": False,
        }
    )
    if residuals.max() > settings.fit_tolerance_mm:
        raise CurvedPatchError(
            "fitting surface",
            "curved_patch_tolerance_not_met",
            (
                f"maximum network fit residual {residuals.max():g} mm exceeds "
                f"{settings.fit_tolerance_mm:g} mm within the span budget"
            ),
        )
    candidates[-1]["chosen"] = True

    vertices = (
        *corner_vertices,
        NetworkVertex("cut-0-start", mid_start),
        NetworkVertex("cut-0-end", mid_end),
    )
    curve = NetworkCurve(
        id="cut-0",
        degree=degree,
        knots=knots,
        poles=curve_poles,
        start_vertex_id="cut-0-start",
        end_vertex_id="cut-0-end",
        continuity="smooth",
    )
    patch_a = NetworkPatch(
        id="patch-0",
        degree=degree,
        knots_u=knots,
        knots_v=knots,
        poles=poles[0],
        corner_vertex_ids=("corner-0", "cut-0-start", "cut-0-end", "corner-3"),
        shared_boundaries={"u1": "cut-0"},
    )
    patch_b = NetworkPatch(
        id="patch-1",
        degree=degree,
        knots_u=knots,
        knots_v=knots,
        poles=poles[1],
        corner_vertex_ids=("cut-0-start", "corner-1", "corner-2", "cut-0-end"),
        shared_boundaries={"u0": "cut-0"},
    )
    network = SurfaceNetwork(
        units="mm", vertices=vertices, curves=(curve,), patches=(patch_a, patch_b)
    )

    guard.stage("assembling solid", 70.0)
    solid = _plate_solid_from_network(
        network, corners, context.prism_vector, (), settings.sewing_tolerance_mm
    )
    guard.stage("validating solid", 90.0)
    face_surfaces, comparison, evidence = _network_gates(
        mesh, solid, network, settings, network_settings
    )
    if fit_cache is not None and cache_key is not None:
        fit_cache.store(
            cache_key,
            _fit_cache_payload(
                "split-network",
                network,
                tuple(iterations),
                candidates,
                float(residuals.max()),
                float(np.sqrt(np.mean(residuals**2))),
            ),
        )
    guard.stage("finished", 100.0)
    return CurvedNetworkResult(
        solid=solid,
        network=network,
        artifact_sha256=network.artifact_sha256(),
        charts=charts,
        iterations=tuple(iterations),
        residual_maximum=float(residuals.max()),
        residual_rms=float(np.sqrt(np.mean(residuals**2))),
        shared_evidence=evidence,
        face_surfaces=face_surfaces,
        comparison=comparison,
        corners=corners,
        prism_vector=(
            float(context.prism_vector[0]),
            float(context.prism_vector[1]),
            float(context.prism_vector[2]),
        ),
        holes=(),
        candidates=tuple(candidates),
        cache_status="stored" if fit_cache is not None else "uncached",
        sewing_tolerance_mm=settings.sewing_tolerance_mm,
    )


PLATE_ARTIFACT_SCHEMA = "mesh2param/curved-plate/1"


def plate_artifact_payload(result: CurvedNetworkResult, *, units: str = "mm") -> dict[str, Any]:
    """The self-sufficient content-addressed artifact behind the CADGraph
    ``reconstructedSurfaceNetwork`` base feature.

    Everything the compiler needs to rebuild the identical solid is inside:
    the surface network, the plate closure (corners, prism vector, sewing
    tolerance), and the exact recorded hole cutters.
    """

    return {
        "schema": PLATE_ARTIFACT_SCHEMA,
        "units": units,
        "network": result.network.to_artifact(),
        "assembly": {
            "corners": [[float(value) for value in corner] for corner in result.corners],
            "prismVector": [float(value) for value in result.prism_vector],
            "sewingToleranceMm": float(result.sewing_tolerance_mm),
            "holes": [cutter.to_dict() for cutter in result.hole_cutters],
        },
    }


def plate_artifact_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def plate_artifact_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(plate_artifact_bytes(payload)).hexdigest()


def rebuild_plate_solid(payload: dict[str, Any]) -> cq.Shape:
    """Deterministically rebuild the plate solid from its artifact payload."""

    if payload.get("schema") != PLATE_ARTIFACT_SCHEMA:
        raise CurvedPatchError(
            "resolving artifact",
            "curved_patch_unsupported_artifact",
            f"unsupported curved-plate artifact schema {payload.get('schema')!r}",
        )
    assembly = payload["assembly"]
    network = SurfaceNetwork.from_artifact(payload["network"])
    corners = np.asarray(assembly["corners"], dtype=np.float64)
    if corners.shape != (4, 3):
        raise CurvedPatchError(
            "resolving artifact",
            "curved_patch_unsupported_artifact",
            "curved-plate artifact must carry exactly four 3-D corners",
        )
    prism_vector = np.asarray(assembly["prismVector"], dtype=np.float64)
    cutters = tuple(HoleCutter.from_dict(entry) for entry in assembly["holes"])
    return _plate_solid_from_network(
        network,
        corners,
        prism_vector,
        cutters,
        float(assembly["sewingToleranceMm"]),
    )


def _fit_cache_payload(
    layout: str,
    network: SurfaceNetwork,
    iterations: tuple[FitIteration, ...],
    candidates: list[dict[str, Any]],
    residual_maximum: float,
    residual_rms: float,
) -> dict[str, Any]:
    return {
        "layout": layout,
        "network": network.to_artifact(),
        "iterations": [iteration.to_dict() for iteration in iterations],
        "candidates": [dict(candidate) for candidate in candidates],
        "residualMaximum": residual_maximum,
        "residualRms": residual_rms,
    }


def _assemble_cached_network(
    mesh: trimesh.Trimesh,
    context: _PlateContext,
    payload: dict[str, Any],
    settings: CurvedPatchSettings,
    network_settings: CurvedNetworkSettings,
    guard: _StageGuard,
    cache_key: str,
) -> CurvedNetworkResult:
    """Rebuild a cached fit and re-run every downstream gate.

    Only the fitting stage is skipped; assembly, kernel validation, G0/G1
    evidence, and the source-deviation comparison all run fresh on the
    rebuilt network, so a hit can never bypass a gate.
    """

    network = SurfaceNetwork.from_artifact(payload["network"])
    corners = context.corners
    cutters = _hole_cutters(context.holes, mesh)
    solid = _plate_solid_from_network(
        network, corners, context.prism_vector, cutters, settings.sewing_tolerance_mm
    )
    guard.stage("validating solid", 90.0)
    face_surfaces, comparison, evidence = _network_gates(
        mesh,
        solid,
        network,
        settings,
        network_settings,
        expected_cylinders=len(context.holes),
    )
    iterations = tuple(
        FitIteration(
            spans_u=int(entry["spansU"]),
            spans_v=int(entry["spansV"]),
            rms_distance=float(entry["rmsDistance"]),
            p95_distance=float(entry["p95Distance"]),
            maximum_distance=float(entry["maximumDistance"]),
        )
        for entry in payload["iterations"]
    )
    guard.stage("finished", 100.0)
    return CurvedNetworkResult(
        solid=solid,
        network=network,
        artifact_sha256=network.artifact_sha256(),
        charts=(context.chart,),
        iterations=iterations,
        residual_maximum=float(payload["residualMaximum"]),
        residual_rms=float(payload["residualRms"]),
        shared_evidence=evidence,
        face_surfaces=face_surfaces,
        comparison=comparison,
        corners=corners,
        prism_vector=(
            float(context.prism_vector[0]),
            float(context.prism_vector[1]),
            float(context.prism_vector[2]),
        ),
        holes=context.holes,
        hole_cutters=cutters,
        candidates=tuple(dict(candidate) for candidate in payload["candidates"]),
        cache_status="hit",
        sewing_tolerance_mm=settings.sewing_tolerance_mm,
    )


__all__ = [
    "PLATE_ARTIFACT_SCHEMA",
    "CurvedNetworkResult",
    "CurvedNetworkSettings",
    "CurvedPatchError",
    "CurvedPatchResult",
    "CurvedPatchSettings",
    "HoleCutter",
    "PlateHole",
    "ProgressCallback",
    "ReconstructionBudget",
    "assemble_single_patch_plate",
    "chart_lattice_samples",
    "plate_artifact_bytes",
    "plate_artifact_payload",
    "plate_artifact_sha256",
    "rebuild_plate_solid",
    "reconstruct_plate_network",
    "reconstruct_single_patch_plate",
]
