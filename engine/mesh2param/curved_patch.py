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
from typing import Any, get_args

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
    ChartHalf,
    ChartParameterization,
    ChartParameterizationError,
    cut_chart_midline,
    detect_rectangle_corners,
    harmonic_square_parameterization,
    reindexed_chart_region,
)
from .segmentation import (
    PatchEditSession,
    PatchKind,
    SegmentationResult,
    SegmentationSettings,
    SurfacePatch,
    segment_mesh,
)
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


def _plate_openings(
    patches: tuple[SurfacePatch, ...],
    freeform: SurfacePatch,
    hole_loops: list[np.ndarray],
    mesh_vertices: np.ndarray,
) -> tuple[PlateHole | PlateCap | PlateCone | PlateTorus, ...]:
    """Match each interior boundary loop to one recognized analytic patch.

    A loop bordered by a recognized cylinder is a through hole (boolean
    subtraction); a loop bordered by a recognized sphere is a proud analytic
    cap (boolean fusion); a loop bordered by a recognized cone is a proud
    conical boss (boolean fusion), and a loop bordered by a recognized torus
    is a proud analytic bead (boolean fusion). Anything else fails closed. Entries
    come back in loop order so callers can pair them with the loops themselves.
    """

    openings: list[PlateHole | PlateCap | PlateCone | PlateTorus] = []
    for index, loop in enumerate(hole_loops):
        loop_vertices = set(int(vertex) for vertex in loop)
        matches = [
            patch
            for patch in patches
            if patch.kind in ("cylinder", "sphere", "cone", "torus")
            and loop_vertices & set(patch.vertex_ids)
        ]
        analytic = matches[0] if len(matches) == 1 else None
        if analytic is None:
            raise CurvedPatchError(
                "segmenting mesh",
                "curved_patch_hole_unrecognized",
                (
                    f"interior loop {index} does not border exactly one recognized "
                    f"cylinder, sphere, cone, or torus (found {len(matches)})"
                ),
            )
        if analytic.kind == "cylinder" and analytic.cylinder_radius_mm is not None:
            openings.append(
                PlateHole(
                    radius=float(analytic.cylinder_radius_mm),
                    axis_point=np.asarray(analytic.cylinder_axis_point, dtype=np.float64),
                    axis=np.asarray(analytic.cylinder_axis, dtype=np.float64),
                    residual_p95=analytic.residuals_mm.p95,
                    patch_id=analytic.id,
                )
            )
        elif analytic.kind == "sphere" and analytic.sphere_radius_mm is not None:
            openings.append(
                PlateCap(
                    radius=float(analytic.sphere_radius_mm),
                    center=np.asarray(analytic.sphere_center, dtype=np.float64),
                    residual_p95=analytic.residuals_mm.p95,
                    patch_id=analytic.id,
                )
            )
        elif (
            analytic.kind == "cone"
            and analytic.cone_apex is not None
            and analytic.cone_axis is not None
            and analytic.cone_half_angle_deg is not None
        ):
            apex = np.asarray(analytic.cone_apex, dtype=np.float64)
            axis = np.asarray(analytic.cone_axis, dtype=np.float64)
            axis /= float(np.linalg.norm(axis))
            # Segmentation canonicalizes direction for stable patch ids. A
            # cone fuser instead needs the geometric direction from its apex
            # into the recognized side region.
            if float((np.asarray(analytic.centroid) - apex) @ axis) < 0.0:
                axis = -axis
            region_points = mesh_vertices[np.asarray(analytic.vertex_ids, dtype=np.int64)]
            axial = (region_points - apex) @ axis
            visible_height = float(np.max(axial))
            if visible_height <= 0.0:
                raise CurvedPatchError(
                    "segmenting mesh",
                    "curved_patch_hole_unrecognized",
                    f"interior loop {index} borders a cone with no positive axial height",
                )
            openings.append(
                PlateCone(
                    apex=apex,
                    axis=axis,
                    half_angle_deg=float(analytic.cone_half_angle_deg),
                    visible_height=visible_height,
                    residual_p95=analytic.residuals_mm.p95,
                    patch_id=analytic.id,
                )
            )
        elif (
            analytic.kind == "torus"
            and analytic.torus_center is not None
            and analytic.torus_axis is not None
            and analytic.torus_major_radius_mm is not None
            and analytic.torus_minor_radius_mm is not None
        ):
            openings.append(
                PlateTorus(
                    major_radius=float(analytic.torus_major_radius_mm),
                    minor_radius=float(analytic.torus_minor_radius_mm),
                    center=np.asarray(analytic.torus_center, dtype=np.float64),
                    axis=np.asarray(analytic.torus_axis, dtype=np.float64),
                    residual_p95=analytic.residuals_mm.p95,
                    patch_id=analytic.id,
                )
            )
        else:
            raise CurvedPatchError(
                "segmenting mesh",
                "curved_patch_hole_unrecognized",
                f"interior loop {index} borders {analytic.id!r} with an incomplete fit",
            )
    return tuple(openings)


def _bottom_plane(
    patches: tuple[SurfacePatch, ...], *freeforms: SurfacePatch
) -> tuple[np.ndarray, np.ndarray]:
    planes = [patch for patch in patches if patch.kind == "plane"]
    freeform_ids = {freeform.id for freeform in freeforms}
    detached = [patch for patch in planes if not freeform_ids & set(patch.neighbor_ids)]
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
    if context.holes or context.caps or context.cones or context.tori:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_holes_unsupported",
            "single-patch reconstruction does not support holes or analytic bosses; "
            "use reconstruct_plate_network",
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
    # A fitted crease must stay sharp along its whole length; losing the
    # dihedral means the join degenerated into a smooth blend.
    crease_minimum_angle_deg: float = 5.0
    coupling_weight: float = 10.0
    # A user-declared smooth join fights data that genuinely wants a crease,
    # so its C1 penalty must dominate the local sample influence; the default
    # cut coupling only has to agree with already-smooth data.
    smooth_override_coupling_weight: float = 1000.0
    curve_fairness: float = 1e-3
    evidence_sample_count: int = 64
    solve_rounds: int = 2

    def validate(self) -> None:
        if not 0.0 < self.g1_maximum_angle_deg < 90.0:
            raise ValueError("G1 gate must be in (0, 90) degrees")
        if not 0.0 < self.crease_minimum_angle_deg < 90.0:
            raise ValueError("crease sharpness gate must be in (0, 90) degrees")
        if self.coupling_weight < 0.0 or self.curve_fairness < 0.0:
            raise ValueError("coupling weight and curve fairness must be non-negative")
        if self.smooth_override_coupling_weight <= 0.0:
            raise ValueError("smooth override coupling weight must be positive")
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
    caps: tuple[PlateCap, ...] = ()
    cap_fusers: tuple[CapFuser, ...] = ()
    cones: tuple[PlateCone, ...] = ()
    cone_fusers: tuple[ConeFuser, ...] = ()
    tori: tuple[PlateTorus, ...] = ()
    torus_fusers: tuple[TorusFuser, ...] = ()
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
            "caps": [cap.to_dict() for cap in self.caps],
            "cones": [cone.to_dict() for cone in self.cones],
            "tori": [torus.to_dict() for torus in self.tori],
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
class PlateCap:
    """A recognized analytic spherical cap standing proud of the plate top."""

    radius: float
    center: np.ndarray = field(repr=False)
    residual_p95: float
    patch_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "sphere",
            "radiusMm": self.radius,
            "center": [float(value) for value in self.center],
            "residualP95Mm": self.residual_p95,
            "patchId": self.patch_id,
        }


@dataclass(frozen=True, slots=True)
class PlateTorus:
    """A recognized analytic torus bead standing proud of the plate top."""

    major_radius: float
    minor_radius: float
    center: np.ndarray = field(repr=False)
    axis: np.ndarray = field(repr=False)
    residual_p95: float
    patch_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "torus",
            "majorRadiusMm": self.major_radius,
            "minorRadiusMm": self.minor_radius,
            "center": [float(value) for value in self.center],
            "axis": [float(value) for value in self.axis],
            "residualP95Mm": self.residual_p95,
            "patchId": self.patch_id,
        }


@dataclass(frozen=True, slots=True)
class CapFuser:
    """Exact boolean fuser for a recognized cap, recorded for replay.

    The recorded ball enters the resulting sphere face's surface placement,
    so replays (fit cache, compiler rebuild) must reuse it verbatim to stay
    byte-deterministic. The parametric axis stays vertical: a horizontal seam
    meridian across the trim curve breaks OCCT's fuse against fitted
    splines, and the pole's zero-area triangles are dropped by the canonical
    tessellation instead.
    """

    radius: float
    center: tuple[float, float, float]
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "radiusMm": self.radius,
            "center": list(self.center),
            "axis": list(self.axis),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CapFuser:
        return cls(
            radius=float(payload["radiusMm"]),
            center=(
                float(payload["center"][0]),
                float(payload["center"][1]),
                float(payload["center"][2]),
            ),
            axis=(
                float(payload["axis"][0]),
                float(payload["axis"][1]),
                float(payload["axis"][2]),
            ),
        )


@dataclass(frozen=True, slots=True)
class PlateCone:
    """A recognized analytic conical boss standing proud of the plate top."""

    apex: np.ndarray = field(repr=False)
    axis: np.ndarray = field(repr=False)
    half_angle_deg: float
    visible_height: float
    residual_p95: float
    patch_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "cone",
            "apex": [float(value) for value in self.apex],
            "axis": [float(value) for value in self.axis],
            "halfAngleDeg": self.half_angle_deg,
            "visibleHeightMm": self.visible_height,
            "residualP95Mm": self.residual_p95,
            "patchId": self.patch_id,
        }


@dataclass(frozen=True, slots=True)
class ConeFuser:
    """Exact apex-ended cone fuser recorded verbatim for deterministic replay."""

    apex: tuple[float, float, float]
    axis: tuple[float, float, float]
    half_angle_deg: float
    height: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "apex": list(self.apex),
            "axis": list(self.axis),
            "halfAngleDeg": self.half_angle_deg,
            "heightMm": self.height,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ConeFuser:
        return cls(
            apex=(
                float(payload["apex"][0]),
                float(payload["apex"][1]),
                float(payload["apex"][2]),
            ),
            axis=(
                float(payload["axis"][0]),
                float(payload["axis"][1]),
                float(payload["axis"][2]),
            ),
            half_angle_deg=float(payload["halfAngleDeg"]),
            height=float(payload["heightMm"]),
        )


@dataclass(frozen=True, slots=True)
class TorusFuser:
    """Exact vertical torus fuser recorded verbatim for deterministic replay."""

    major_radius: float
    minor_radius: float
    center: tuple[float, float, float]
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "majorRadiusMm": self.major_radius,
            "minorRadiusMm": self.minor_radius,
            "center": list(self.center),
            "axis": list(self.axis),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TorusFuser:
        return cls(
            major_radius=float(payload["majorRadiusMm"]),
            minor_radius=float(payload["minorRadiusMm"]),
            center=(
                float(payload["center"][0]),
                float(payload["center"][1]),
                float(payload["center"][2]),
            ),
            axis=(
                float(payload["axis"][0]),
                float(payload["axis"][1]),
                float(payload["axis"][2]),
            ),
        )


@dataclass(frozen=True, slots=True)
class _SupplementalRegion:
    """Observed plate island fitted into the primary rectangular chart."""

    vertices: np.ndarray = field(repr=False)
    faces: np.ndarray = field(repr=False)
    uv: np.ndarray = field(repr=False)


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
    caps: tuple[PlateCap, ...] = ()
    cones: tuple[PlateCone, ...] = ()
    tori: tuple[PlateTorus, ...] = ()
    hole_loops: tuple[np.ndarray, ...] = ()
    # Per interior loop: the recognized cap standing over it, or None for a
    # through hole. Cap loops get dense synthetic fill on the ball surface
    # lowered by a clearance, so the fitted patch tracks a smooth dome
    # strictly inside the ball and the fuse intersects cleanly at the rim.
    fill_analytics: tuple[PlateCap | PlateCone | None, ...] = ()
    supplemental_regions: tuple[_SupplementalRegion, ...] = ()
    freeform_locked: bool = False


def _smooth_boundary_pairs(
    segmentation: SegmentationResult,
    patch_overrides: dict[str, dict[str, Any]],
) -> set[frozenset[str]]:
    """Validate user smooth-boundary declarations against the segmentation.

    A smooth override names the neighbor whose shared boundary should join
    with tangent continuity instead of the detected sharp crease. It is only
    meaningful between two adjacent freeform regions; anything else fails
    closed rather than silently reinterpreting the user's intent.
    """

    by_id = {patch.id: patch for patch in segmentation.patches}
    pairs: set[frozenset[str]] = set()
    for patch_id in sorted(patch_overrides):
        neighbors = patch_overrides[patch_id].get("smooth_boundaries")
        if not neighbors:
            continue
        patch = by_id[patch_id]
        for neighbor_id in sorted(set(neighbors)):
            neighbor = by_id.get(neighbor_id)
            if neighbor is None:
                raise CurvedPatchError(
                    "segmenting mesh",
                    "curved_patch_override_unknown",
                    (
                        f"smooth boundary override on {patch_id!r} references "
                        f"unknown patch {neighbor_id!r}; re-run analysis before converting"
                    ),
                )
            if neighbor_id not in patch.neighbor_ids:
                raise CurvedPatchError(
                    "segmenting mesh",
                    "curved_patch_override_rejected",
                    f"patches {patch_id!r} and {neighbor_id!r} do not share a boundary",
                )
            if patch.kind not in ("freeform", "unknown") or neighbor.kind not in (
                "freeform",
                "unknown",
            ):
                raise CurvedPatchError(
                    "segmenting mesh",
                    "curved_patch_override_rejected",
                    (
                        "smooth boundary overrides apply only between two "
                        f"freeform regions; {patch_id!r} and {neighbor_id!r} are "
                        f"{patch.kind} and {neighbor.kind}"
                    ),
                )
            pairs.add(frozenset((patch_id, neighbor_id)))
    return pairs


def _apply_patch_overrides(
    mesh: trimesh.Trimesh,
    segmentation: SegmentationResult,
    patch_overrides: dict[str, dict[str, Any]],
) -> tuple[SegmentationResult, set[frozenset[str]]]:
    """Apply persisted user reclassifications and locks, failing closed.

    Reclassification reuses the segmentation edit session, so an analytic
    override is refitted and rejected when the triangles do not satisfy the
    requested kind's tolerance -- user intent never fabricates geometry.
    Smooth boundary declarations are validated against the pre-edit adjacency
    (the ids the client knows) and remapped through any reclassifications.
    """

    session = PatchEditSession(mesh, segmentation)
    for patch_id in sorted(patch_overrides):
        if patch_id not in session.patches:
            raise CurvedPatchError(
                "segmenting mesh",
                "curved_patch_override_unknown",
                (
                    f"patch override {patch_id!r} does not match the current "
                    "segmentation; re-run analysis before converting"
                ),
            )
    smooth_pairs = _smooth_boundary_pairs(segmentation, patch_overrides)

    id_map: dict[str, str] = {}
    for patch_id in sorted(patch_overrides):
        override = patch_overrides[patch_id]
        kind = override.get("kind")
        if kind is not None:
            if kind not in get_args(PatchKind):
                raise CurvedPatchError(
                    "segmenting mesh",
                    "curved_patch_override_rejected",
                    f"unsupported patch kind {kind!r} for {patch_id!r}",
                )
            record = session.reclassify(patch_id, kind)
            if not record.success:
                raise CurvedPatchError(
                    "segmenting mesh",
                    "curved_patch_override_rejected",
                    f"reclassifying {patch_id!r} to {kind!r} failed: {record.warning}",
                )
            id_map[patch_id] = record.after[0].id
            patch_id = record.after[0].id
        if override.get("locked"):
            session.lock(patch_id, True)
    patches = tuple(sorted(session.patches.values(), key=lambda patch: patch.id))
    remapped = {
        frozenset(id_map.get(patch_id, patch_id) for patch_id in pair) for pair in smooth_pairs
    }
    return SegmentationResult(patches, segmentation.settings, segmentation.warnings), remapped


def _segment_with_overrides(
    mesh: trimesh.Trimesh,
    settings: CurvedPatchSettings,
    patch_overrides: dict[str, dict[str, Any]] | None,
) -> tuple[SegmentationResult, set[frozenset[str]]]:
    segmentation = segment_mesh(mesh, settings.segmentation)
    if patch_overrides:
        return _apply_patch_overrides(mesh, segmentation, patch_overrides)
    return segmentation, set()


def _closed_loop_perimeter(vertices: np.ndarray, loop: np.ndarray) -> float:
    """Return the 3-D perimeter of a closed indexed loop."""

    points = vertices[loop]
    closed = np.vstack([points, points[:1]])
    return float(np.linalg.norm(np.diff(closed, axis=0), axis=1).sum())


def _plate_context(
    mesh: trimesh.Trimesh,
    settings: CurvedPatchSettings,
    patch_overrides: dict[str, dict[str, Any]] | None = None,
    segmentation: SegmentationResult | None = None,
    primary_freeform: SurfacePatch | None = None,
    additional_freeforms: tuple[SurfacePatch, ...] = (),
    fill_holes_for_parameterization: bool = False,
) -> _PlateContext:
    """Segment, extract, parameterize, and bound the plate's freeform chart."""

    if segmentation is None:
        segmentation, _ = _segment_with_overrides(mesh, settings, patch_overrides)
    freeform = primary_freeform or _freeform_patch(segmentation.patches)
    bottom_origin, bottom_normal = _bottom_plane(
        segmentation.patches, freeform, *additional_freeforms
    )

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

    loops_global = [np.asarray(loop.vertex_ids, dtype=np.int64) for loop in freeform.boundary_loops]
    outer_index = int(
        np.argmax([_closed_loop_perimeter(mesh_vertices, loop) for loop in loops_global])
    )
    loop_global = loops_global[outer_index]
    hole_loops = [loop for index, loop in enumerate(loops_global) if index != outer_index]
    openings = _plate_openings(segmentation.patches, freeform, hole_loops, mesh_vertices)

    chart_loop = local_index[loop_global]
    hole_loops_local = tuple(local_index[loop] for loop in hole_loops)
    if np.any(chart_loop < 0) or any(np.any(loop < 0) for loop in hole_loops_local):
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_boundary_mismatch",
            "a freeform boundary loop references vertices outside the region",
        )

    try:
        if fill_holes_for_parameterization and hole_loops_local:
            detected = detect_rectangle_corners(
                chart_vertices,
                chart_loop,
                minimum_turn_deg=settings.corner_turn_threshold_deg,
            )
            corner_ids = (
                int(chart_loop[detected[0]]),
                int(chart_loop[detected[1]]),
                int(chart_loop[detected[2]]),
                int(chart_loop[detected[3]]),
            )
            filled_half = reindexed_chart_region(chart_vertices, chart_faces, corner_ids)
            chart = _parameterize_half(filled_half)
            chart_vertices = filled_half.vertices
            chart_faces = filled_half.faces
            chart_loop = filled_half.boundary_loop
            hole_loops_local = filled_half.hole_loops
        else:
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

    for index, hole in enumerate(o for o in openings if isinstance(o, PlateHole)):
        if abs(float(hole.axis @ rectangle_normal)) < np.cos(
            np.radians(settings.plane_parallel_tolerance_deg)
        ):
            raise CurvedPatchError(
                "segmenting mesh",
                "curved_patch_hole_not_normal",
                f"hole {index} axis is not perpendicular to the plate",
            )

    for index, torus in enumerate(o for o in openings if isinstance(o, PlateTorus)):
        axis = torus.axis / max(float(np.linalg.norm(torus.axis)), 1e-300)
        if abs(float(axis @ rectangle_normal)) < np.cos(
            np.radians(settings.plane_parallel_tolerance_deg)
        ):
            raise CurvedPatchError(
                "segmenting mesh",
                "curved_patch_torus_not_normal",
                f"torus {index} axis is not perpendicular to the plate",
            )
        if float(axis @ np.asarray((0.0, 0.0, 1.0))) < np.cos(
            np.radians(settings.plane_parallel_tolerance_deg)
        ):
            raise CurvedPatchError(
                "segmenting mesh",
                "curved_patch_torus_not_vertical",
                f"torus {index} axis is not the supported positive vertical axis",
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
        holes=tuple(o for o in openings if isinstance(o, PlateHole)),
        caps=tuple(o for o in openings if isinstance(o, PlateCap)),
        cones=tuple(o for o in openings if isinstance(o, PlateCone)),
        tori=tuple(o for o in openings if isinstance(o, PlateTorus)),
        hole_loops=hole_loops_local,
        fill_analytics=tuple(
            opening if isinstance(opening, (PlateCap, PlateCone)) else None for opening in openings
        ),
        freeform_locked=freeform.locked,
    )


def _hole_fill_samples(
    chart: ChartParameterization,
    vertices: np.ndarray,
    hole_loops: tuple[np.ndarray, ...],
    base_weight: float,
    fill_analytics: tuple[PlateCap | PlateCone | None, ...] = (),
    normal: np.ndarray | None = None,
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
    fill_weight_blocks: list[np.ndarray] = []

    def push(uv_block: np.ndarray, point_block: np.ndarray, weight: float) -> None:
        fill_uv.append(uv_block)
        fill_points.append(point_block)
        fill_weight_blocks.append(np.full(len(uv_block), weight))

    for index, loop in enumerate(hole_loops):
        rim_uv = chart.uv[loop]
        rim_points = vertices[loop]
        centroid_uv = rim_uv.mean(axis=0)
        centroid_point = rim_points.mean(axis=0)
        analytic = fill_analytics[index] if index < len(fill_analytics) else None
        if analytic is None or normal is None:
            push(centroid_uv[None, :], centroid_point[None, :], base_weight)
            step = max(1, len(loop) // 12)
            selected = np.arange(0, len(loop), step)
            for fraction in (0.35, 0.7):
                push(
                    centroid_uv + fraction * (rim_uv[selected] - centroid_uv),
                    centroid_point + fraction * (rim_points[selected] - centroid_point),
                    base_weight,
                )
            continue
        lowered_analytic: Callable[[np.ndarray], np.ndarray]
        if isinstance(analytic, PlateCap):
            # Sphere loop: dense fill ON the recognized ball lowered by a
            # clearance so the fitted patch stays strictly inside the ball.
            cap_center = np.asarray(analytic.center, dtype=np.float64)
            cap_radius = float(analytic.radius)
            clearance = max(1.5, 0.15 * cap_radius)
            # The chart normal may point either way; orient it toward the
            # proud side of the cap (the rim sits above the ball center).
            up = -normal if float((centroid_point - cap_center) @ normal) < 0.0 else normal

            def on_lowered_ball(
                points: np.ndarray,
                center: np.ndarray = cap_center,
                radius: float = cap_radius,
                clearance: float = clearance,
                up: np.ndarray = up,
            ) -> np.ndarray:
                radial = points - center
                radial = radial - np.outer(radial @ up, up)
                rho_sq = np.einsum("ij,ij->i", radial, radial)
                lift = np.sqrt(np.maximum(radius**2 - rho_sq, (0.2 * radius) ** 2))
                result: np.ndarray = center + radial + np.outer(lift - clearance, up)
                return result

            lowered_analytic = on_lowered_ball

        else:
            # Cone loop: preserve each sample's radial direction and place it
            # on the recognized cone, shifted farther from the apex along the
            # cone axis. This is the cone analogue of on_lowered_ball: the
            # fitted patch stays strictly inside the fuser and cannot poke up
            # through it as disconnected B-spline islands.
            cone_apex = np.asarray(analytic.apex, dtype=np.float64)
            cone_axis = np.asarray(analytic.axis, dtype=np.float64)
            cone_slope = math.tan(math.radians(analytic.half_angle_deg))
            clearance = max(2.0, 0.35 * analytic.visible_height)

            def on_lowered_cone(
                points: np.ndarray,
                apex: np.ndarray = cone_apex,
                axis: np.ndarray = cone_axis,
                slope: float = cone_slope,
                clearance: float = clearance,
            ) -> np.ndarray:
                offsets = points - apex
                radial = offsets - np.outer(offsets @ axis, axis)
                rho = np.linalg.norm(radial, axis=1)
                axial = rho / slope + clearance
                result = apex + radial + np.outer(axial, axis)
                return np.asarray(result)

            lowered_analytic = on_lowered_cone

        # Strong, dense fill: a weak fill lets the patch overshoot above the
        # ball between rings, and every such island becomes a spurious trim
        # in the cap join. These samples are trimmed away by the ball anyway.
        analytic_weight = 50.0 * base_weight
        push(
            centroid_uv[None, :],
            lowered_analytic(centroid_point[None, :]),
            analytic_weight,
        )
        step = max(1, len(loop) // 24)
        selected = np.arange(0, len(loop), step)
        for fraction in np.linspace(0.1, 0.95, 10):
            blend_uv = centroid_uv + fraction * (rim_uv[selected] - centroid_uv)
            blend_points = centroid_point + fraction * (rim_points[selected] - centroid_point)
            push(blend_uv, lowered_analytic(blend_points), analytic_weight)
    if not fill_uv:
        empty = np.zeros((0, 3))
        return np.zeros((0, 2)), empty, np.zeros(0)
    uv = np.concatenate(fill_uv)
    points = np.concatenate(fill_points)
    weights = np.concatenate(fill_weight_blocks)
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


def _cap_fusers(caps: tuple[PlateCap, ...]) -> tuple[CapFuser, ...]:
    """Derive each cap's recorded boolean fuser from its recognized fit."""

    return tuple(
        CapFuser(
            radius=float(cap.radius),
            center=(float(cap.center[0]), float(cap.center[1]), float(cap.center[2])),
        )
        for cap in caps
    )


def _cone_fusers(cones: tuple[PlateCone, ...]) -> tuple[ConeFuser, ...]:
    """Extend each recognized visible cone just inside the fitted plate."""

    return tuple(
        ConeFuser(
            apex=(float(cone.apex[0]), float(cone.apex[1]), float(cone.apex[2])),
            axis=(float(cone.axis[0]), float(cone.axis[1]), float(cone.axis[2])),
            half_angle_deg=float(cone.half_angle_deg),
            height=float(cone.visible_height + max(1.5, 0.15 * cone.visible_height)),
        )
        for cone in cones
    )


def _torus_fusers(tori: tuple[PlateTorus, ...]) -> tuple[TorusFuser, ...]:
    """Record the canonical seam orientation for each recognized torus."""

    return tuple(
        TorusFuser(
            major_radius=float(torus.major_radius),
            minor_radius=float(torus.minor_radius),
            center=(
                float(torus.center[0]),
                float(torus.center[1]),
                float(torus.center[2]),
            ),
        )
        for torus in tori
    )


def _is_removed_core(fragment: cq.Shape, cutter: HoleCutter) -> bool:
    """Whether a boolean fragment is material the cutter was meant to remove.

    Open CASCADE does not always discard the core it cuts out: on some builds
    the subtraction returns it alongside the remainder rather than deleting it.
    A fragment whose centroid lies inside the cutter cylinder is by definition
    that core, and keeping it would fill the hole back in. A fragment outside
    the cutter is a piece the hole genuinely severed from the plate, which is a
    real modelling failure and must still be reported.
    """

    axis = np.asarray(cutter.direction, dtype=np.float64)
    base = np.asarray(cutter.base_point, dtype=np.float64)
    centre = fragment.Center()
    offset = np.array([centre.x, centre.y, centre.z], dtype=np.float64) - base
    along = float(offset @ axis)
    radial = float(np.linalg.norm(offset - along * axis))
    return radial <= cutter.radius and 0.0 <= along <= cutter.height


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
        solids = result.Solids()
        if len(solids) > 1:
            remainder = [piece for piece in solids if not _is_removed_core(piece, cutter_spec)]
            # Only rebuild the shape when the kernel actually handed back extra
            # pieces; leaving the single-solid path untouched keeps the exported
            # bytes identical on builds that discard the core themselves.
            if len(remainder) == 1:
                result = remainder[0]
                solids = remainder
        if len(solids) != 1:
            raise CurvedPatchError(
                "assembling solid",
                "curved_patch_hole_boolean_failed",
                f"subtracting hole {index} split the plate into multiple solids",
            )
    return result


def _fuse_caps(solid: cq.Shape, fusers: tuple[CapFuser, ...], sewing_tolerance: float) -> cq.Shape:
    """Boolean-fuse each recorded cap ball into the plate solid.

    The kernel computes the exact intersection curve where the ball pokes
    through the fitted top, so the trimmed B-spline and the true sphere face
    share one valid shell without approximation on our side. The result is
    used raw: ``clean()`` demonstrably corrupts fused sphere/spline shells.
    Where the fitted patch locally overshoots above the ball, small trimmed
    B-spline islands remain on the cap -- honest fitted geometry that the
    deviation gates referee. Caps fuse before holes subtract, so a future
    hole may pierce a cap.
    """

    del sewing_tolerance
    result = solid
    for index, fuser in enumerate(fusers):
        ball = cq.Solid.makeSphere(
            fuser.radius,
            cq.Vector(*fuser.center),
            cq.Vector(*fuser.axis),
            angleDegrees1=-90,
        )
        try:
            result = result.fuse(ball)
        except Exception as exc:
            raise CurvedPatchError(
                "assembling solid",
                "curved_patch_cap_boolean_failed",
                f"fusing cap {index} failed: {exc}",
            ) from exc
        if len(result.Solids()) != 1:
            raise CurvedPatchError(
                "assembling solid",
                "curved_patch_cap_boolean_failed",
                f"fusing cap {index} split the plate into multiple solids",
            )
    return result


def _fuse_cones(
    solid: cq.Shape, fusers: tuple[ConeFuser, ...], sewing_tolerance: float
) -> cq.Shape:
    """Boolean-fuse recorded apex-ended cones into the plate solid.

    The cone extends beyond the recognized rim and terminates inside the
    plate. OCCT therefore computes the exact cone/B-spline trim curve while
    the base face remains internal to the union. As with spherical caps, the
    raw fuse result is mandatory: post-fuse ``clean()`` can corrupt a hybrid
    analytic/B-spline shell. Cone fusion precedes every hole subtraction.
    """

    del sewing_tolerance
    result = solid
    for index, fuser in enumerate(fusers):
        radius = fuser.height * math.tan(math.radians(fuser.half_angle_deg))
        cone = cq.Solid.makeCone(
            0.0,
            radius,
            fuser.height,
            cq.Vector(*fuser.apex),
            cq.Vector(*fuser.axis),
        )
        try:
            result = result.fuse(cone)
        except Exception as exc:
            raise CurvedPatchError(
                "assembling solid",
                "curved_patch_cone_boolean_failed",
                f"fusing cone {index} failed: {exc}",
            ) from exc
        if len(result.Solids()) != 1:
            raise CurvedPatchError(
                "assembling solid",
                "curved_patch_cone_boolean_failed",
                f"fusing cone {index} split the plate into multiple solids",
            )
    return result


def _fuse_tori(solid: cq.Shape, fusers: tuple[TorusFuser, ...]) -> cq.Shape:
    """Fuse recorded torus beads without cleaning or seam reorientation."""

    result = solid
    for index, fuser in enumerate(fusers):
        torus = cq.Solid.makeTorus(
            fuser.major_radius,
            fuser.minor_radius,
            cq.Vector(*fuser.center),
            cq.Vector(*fuser.axis),
        )
        try:
            result = result.fuse(torus)
        except Exception as exc:
            raise CurvedPatchError(
                "assembling solid",
                "curved_patch_torus_boolean_failed",
                f"fusing torus {index} failed: {exc}",
            ) from exc
        if len(result.Solids()) != 1:
            raise CurvedPatchError(
                "assembling solid",
                "curved_patch_torus_boolean_failed",
                f"fusing torus {index} did not produce exactly one solid",
            )
    return result


def _plate_solid_from_network(
    network: SurfaceNetwork,
    corners: np.ndarray,
    prism_vector: np.ndarray,
    cutters: tuple[HoleCutter, ...],
    sewing_tolerance: float,
    cap_fusers: tuple[CapFuser, ...] = (),
    cone_fusers: tuple[ConeFuser, ...] = (),
    torus_fusers: tuple[TorusFuser, ...] = (),
) -> cq.Shape:
    """The single assembly path shared by the driver, cache, and compiler.

    Wall chains derive from the network itself: a two-patch network's shared
    curve (an artificial cut or a real crease) contributes its endpoints to
    the two walls it terminates on, chosen by proximity so replays stay
    byte-identical regardless of vertex naming.
    """

    if len(network.curves) > 1:
        raise CurvedPatchError(
            "assembling solid",
            "curved_patch_unsupported_network",
            "plate assembly supports at most one shared boundary curve",
        )
    if network.curves:
        curve = network.curves[0]
        endpoints = [
            np.asarray(network.vertex(curve.start_vertex_id).point, dtype=np.float64),
            np.asarray(network.vertex(curve.end_vertex_id).point, dtype=np.float64),
        ]

        def _distance_to_segment(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> float:
            direction = end - start
            length_sq = float(direction @ direction)
            fraction = (point - start) @ direction / max(length_sq, 1e-300)
            fraction = float(np.clip(fraction, 0.0, 1.0))
            return float(np.linalg.norm(point - (start + fraction * direction)))

        if _distance_to_segment(endpoints[0], corners[0], corners[1]) > _distance_to_segment(
            endpoints[1], corners[0], corners[1]
        ):
            endpoints.reverse()
        wall_chains = [
            [corners[0], endpoints[0], corners[1]],
            [corners[1], corners[2]],
            [corners[2], endpoints[1], corners[3]],
            [corners[3], corners[0]],
        ]
    else:
        wall_chains = [[corners[k], corners[(k + 1) % 4]] for k in range(4)]
    solid = _network_plate_solid(network, wall_chains, corners, prism_vector, sewing_tolerance)
    fused = _fuse_caps(solid, cap_fusers, sewing_tolerance)
    fused = _fuse_cones(fused, cone_fusers, sewing_tolerance)
    fused = _fuse_tori(fused, torus_fusers)
    return _subtract_holes(fused, cutters)


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
    expected_spheres: int = 0,
    expected_cones: int = 0,
    expected_face_count: int | None = None,
    expected_tori: int = 0,
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
    if face_surfaces["sphere"] != expected_spheres:
        raise CurvedPatchError(
            "validating solid",
            "curved_patch_cap_faces_mismatch",
            (
                f"expected {expected_spheres} sphere faces from recognized caps, "
                f"found {face_surfaces['sphere']}"
            ),
        )
    if face_surfaces["cone"] != expected_cones:
        raise CurvedPatchError(
            "validating solid",
            "curved_patch_cone_faces_mismatch",
            (
                f"expected {expected_cones} cone faces from recognized bosses, "
                f"found {face_surfaces['cone']}"
            ),
        )
    if expected_face_count is not None and len(solid.Faces()) != expected_face_count:
        raise CurvedPatchError(
            "validating solid",
            "curved_patch_cone_face_count_mismatch",
            (
                f"expected {expected_face_count} total faces after cone fusion, "
                f"found {len(solid.Faces())}"
            ),
        )
    if face_surfaces["torus"] != expected_tori:
        raise CurvedPatchError(
            "validating solid",
            "curved_patch_torus_faces_mismatch",
            (
                f"expected {expected_tori} torus faces from recognized beads, "
                f"found {face_surfaces['torus']}"
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
        # Gate smooth joins on the interior: the plate's straight boundary
        # chains meet at an angle at the shared curve's endpoints, so the
        # walls force C0 corners there even when the join itself is smooth.
        if (
            entry.continuity == "smooth"
            and entry.interior_maximum_normal_angle_deg > network_settings.g1_maximum_angle_deg
        ):
            raise CurvedPatchError(
                "validating solid",
                "curved_patch_g1_angle",
                (
                    f"shared curve {entry.curve_id!r} interior tangent mismatch "
                    f"{entry.interior_maximum_normal_angle_deg:g} deg exceeds "
                    f"{network_settings.g1_maximum_angle_deg:g} deg"
                ),
            )
        if (
            entry.continuity == "crease"
            and entry.minimum_normal_angle_deg < network_settings.crease_minimum_angle_deg
        ):
            raise CurvedPatchError(
                "validating solid",
                "curved_patch_crease_lost",
                (
                    f"crease curve {entry.curve_id!r} dihedral drops to "
                    f"{entry.minimum_normal_angle_deg:g} deg, below the "
                    f"{network_settings.crease_minimum_angle_deg:g} deg sharpness gate"
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


@dataclass(frozen=True, slots=True)
class _CreaseContext:
    """Two adjacent freeform regions sharing one real crease boundary."""

    region_ids: tuple[str, str]
    holes: tuple[PlateHole, ...]
    halves: tuple[ChartHalf, ChartHalf]
    charts: tuple[ChartParameterization, ChartParameterization]
    corners: np.ndarray
    crease_start: np.ndarray
    crease_end: np.ndarray
    rectangle_normal: np.ndarray
    prism_vector: np.ndarray
    segmentation_counts: dict[str, int]
    cache_faces: np.ndarray


def _region_corner_cycle(
    mesh_vertices: np.ndarray,
    loop: np.ndarray,
    settings: CurvedPatchSettings,
) -> tuple[np.ndarray, list[int]]:
    """A region's boundary corner positions (loop order) and vertex ids."""

    try:
        positions = detect_rectangle_corners(
            mesh_vertices, loop, minimum_turn_deg=settings.corner_turn_threshold_deg
        )
    except ChartParameterizationError as exc:
        raise CurvedPatchError("segmenting mesh", exc.code, str(exc)) from exc
    return positions, [int(loop[position]) for position in positions]


def _region_chain_line(
    mesh_vertices: np.ndarray,
    loop: np.ndarray,
    positions: np.ndarray,
    chain: int,
    settings: CurvedPatchSettings,
) -> tuple[np.ndarray, np.ndarray]:
    """Fit one straight boundary chain of a region, gating its deviation."""

    selected = _chain_positions(len(loop), int(positions[chain]), int(positions[(chain + 1) % 4]))
    centroid, direction, deviation = _fit_line(mesh_vertices[loop[selected]])
    if deviation > settings.boundary_line_tolerance_mm:
        raise CurvedPatchError(
            "fitting boundary",
            "curved_patch_boundary_not_straight",
            (
                f"outer boundary chain deviates {deviation:g} mm from a line "
                f"(limit {settings.boundary_line_tolerance_mm:g} mm)"
            ),
        )
    return centroid, direction


def _parameterize_half(half: ChartHalf) -> ChartParameterization:
    """Harmonically map one region half, filling hole rims with virtual fans.

    A free hole rim inside a nearly flat region collapses to a point in the
    harmonic map (skinny rim fans wreck the system's conditioning), so the
    solve runs on the FILLED region: one synthetic centroid vertex per hole,
    fanned to the rim with the region's winding. The synthetic rows are
    dropped from the returned chart; only real vertices keep their UVs.
    """

    if not half.hole_loops:
        return harmonic_square_parameterization(
            half.vertices,
            half.faces,
            half.boundary_loop,
            corner_loop_positions=np.asarray(half.corner_positions, dtype=np.int64),
        )
    vertices = [np.asarray(half.vertices, dtype=np.float64)]
    fans: list[np.ndarray] = []
    next_index = len(half.vertices)
    for loop in half.hole_loops:
        centroid = np.asarray(half.vertices, dtype=np.float64)[loop].mean(axis=0)
        vertices.append(centroid[None, :])
        count = len(loop)
        # Directed rim edges follow the region's face winding, so the fan
        # triangle across (a -> b) traverses it as (b -> a).
        fans.append(
            np.column_stack(
                [
                    np.roll(loop, -1),
                    loop,
                    np.full(count, next_index, dtype=np.int64),
                ]
            )
        )
        next_index += 1
    augmented = harmonic_square_parameterization(
        np.concatenate(vertices),
        np.vstack([half.faces, *fans]),
        half.boundary_loop,
        corner_loop_positions=np.asarray(half.corner_positions, dtype=np.int64),
    )
    return ChartParameterization(
        uv=augmented.uv[: len(half.vertices)],
        boundary_loop=augmented.boundary_loop,
        corner_loop_positions=augmented.corner_loop_positions,
        flipped_triangle_count=augmented.flipped_triangle_count,
        minimum_uv_area_ratio=augmented.minimum_uv_area_ratio,
        maximum_stretch=augmented.maximum_stretch,
        mean_area_distortion=augmented.mean_area_distortion,
    )


def _project_plate_region_uv(
    vertices: np.ndarray,
    faces: np.ndarray,
    corners: np.ndarray,
) -> np.ndarray:
    """Project a near-planar observed island into the primary chart frame.

    Torus fusion hides an annulus of the plate but leaves a disconnected
    inner island.  The plate-specific topology guarantees a height field over
    the fitted rectangle, so its in-plane coordinates provide the common UV
    frame without inventing correspondence across the hidden annulus.
    """

    basis = np.column_stack((corners[1] - corners[0], corners[3] - corners[0]))
    if np.linalg.matrix_rank(basis) != 2:
        raise CurvedPatchError(
            "parameterizing chart",
            "curved_patch_torus_uv_degenerate",
            "the plate rectangle does not define a two-dimensional UV frame",
        )
    uv = np.linalg.lstsq(basis, (vertices - corners[0]).T, rcond=None)[0].T
    if not np.all(np.isfinite(uv)) or np.any(uv < -1e-9) or np.any(uv > 1.0 + 1e-9):
        raise CurvedPatchError(
            "parameterizing chart",
            "curved_patch_torus_uv_outside",
            "the inner torus island projects outside the plate chart",
        )
    edge_a = uv[faces[:, 1]] - uv[faces[:, 0]]
    edge_b = uv[faces[:, 2]] - uv[faces[:, 0]]
    signed = edge_a[:, 0] * edge_b[:, 1] - edge_a[:, 1] * edge_b[:, 0]
    scale = max(float(np.max(np.abs(signed))), 1e-300)
    if np.any(np.abs(signed) <= scale * 1e-12) or not (
        np.all(signed > 0.0) or np.all(signed < 0.0)
    ):
        raise CurvedPatchError(
            "parameterizing chart",
            "curved_patch_torus_uv_folded",
            "the inner torus island has folded or degenerate projected UV triangles",
        )
    return np.asarray(uv)


def _torus_plate_context(
    mesh: trimesh.Trimesh,
    segmentation: SegmentationResult,
    settings: CurvedPatchSettings,
) -> _PlateContext | None:
    """Build one fitted chart from two regions separated by a torus bead."""

    regions = sorted(
        (patch for patch in segmentation.patches if patch.kind in ("freeform", "unknown")),
        key=lambda patch: patch.id,
    )
    if len(regions) != 2:
        return None
    bridging = [
        patch
        for patch in segmentation.patches
        if patch.kind == "torus" and all(patch.id in region.neighbor_ids for region in regions)
    ]
    if not bridging:
        return None
    if len(bridging) != 1:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_torus_topology_unsupported",
            f"expected one torus between the two freeform regions, found {len(bridging)}",
        )
    torus_patch = bridging[0]
    if regions[1].id in regions[0].neighbor_ids:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_torus_topology_unsupported",
            "torus-separated plate regions must not also share a direct boundary",
        )
    plane_ids = {patch.id for patch in segmentation.patches if patch.kind == "plane"}
    outer_candidates = [region for region in regions if plane_ids & set(region.neighbor_ids)]
    if len(outer_candidates) != 1:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_torus_topology_unsupported",
            "exactly one torus-separated region must carry the plate's outer walls",
        )
    outer = outer_candidates[0]
    inner = regions[1] if outer is regions[0] else regions[0]
    if len(outer.boundary_loops) != 2 or len(inner.boundary_loops) != 1:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_torus_topology_unsupported",
            "a torus bead requires an outer annulus region and one inner disk region",
        )
    if not all(loop.closed for loop in (*outer.boundary_loops, *inner.boundary_loops)):
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_not_disk",
            "all torus-separated freeform boundary loops must be closed",
        )
    torus_vertices = set(torus_patch.vertex_ids)
    inner_loop = inner.boundary_loops[0]
    if not set(inner_loop.vertex_ids).issubset(torus_vertices):
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_torus_topology_unsupported",
            "the inner freeform disk does not share its entire rim with the torus",
        )

    context = _plate_context(
        mesh,
        settings,
        segmentation=segmentation,
        primary_freeform=outer,
        additional_freeforms=(inner,),
        fill_holes_for_parameterization=True,
    )
    if len(context.tori) != 1 or context.tori[0].patch_id != torus_patch.id:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_torus_topology_unsupported",
            "the outer plate loop did not resolve to the separating torus",
        )

    mesh_faces = np.asarray(mesh.faces, dtype=np.int64)
    mesh_vertices = np.asarray(mesh.vertices, dtype=np.float64)
    inner_faces_global = mesh_faces[np.asarray(inner.triangle_ids, dtype=np.int64)]
    inner_used = np.unique(inner_faces_global)
    inner_local = np.full(len(mesh_vertices), -1, dtype=np.int64)
    inner_local[inner_used] = np.arange(len(inner_used))
    inner_vertices = mesh_vertices[inner_used]
    inner_faces = inner_local[inner_faces_global]
    inner_uv = _project_plate_region_uv(inner_vertices, inner_faces, context.corners)
    return replace(
        context,
        supplemental_regions=(_SupplementalRegion(inner_vertices, inner_faces, inner_uv),),
        freeform_locked=context.freeform_locked or inner.locked,
    )


def _crease_context(
    mesh: trimesh.Trimesh,
    segmentation: SegmentationResult,
    settings: CurvedPatchSettings,
) -> _CreaseContext:
    """Extract, order, and bound the two-region crease-network topology.

    The two freeform regions must each be one disk (a single closed boundary
    loop, no holes yet), be adjacent, and share exactly two boundary corners:
    the crease endpoints. Every non-crease boundary chain must be straight so
    the six outer corners define the plate rectangle plus the two (possibly
    elevated) crease endpoints on their walls.
    """

    regions = sorted(
        (patch for patch in segmentation.patches if patch.kind in ("freeform", "unknown")),
        key=lambda patch: patch.id,
    )
    region_a, region_b = regions
    if region_b.id not in region_a.neighbor_ids:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_regions_detached",
            "the two freeform regions do not share a boundary",
        )
    for region in regions:
        if not region.boundary_loops or not all(loop.closed for loop in region.boundary_loops):
            raise CurvedPatchError(
                "segmenting mesh",
                "curved_patch_not_disk",
                "every freeform boundary loop must be closed (one outer, optional holes)",
            )

    mesh_vertices = np.asarray(mesh.vertices, dtype=np.float64)
    mesh_faces = np.asarray(mesh.faces, dtype=np.int64)

    outer_loops: list[np.ndarray] = []
    interior_loops: list[np.ndarray] = []
    interior_regions: list[SurfacePatch] = []
    for region in regions:
        loops = [np.asarray(loop.vertex_ids, dtype=np.int64) for loop in region.boundary_loops]
        outer_index = int(
            np.argmax([_closed_loop_perimeter(mesh_vertices, loop) for loop in loops])
        )
        outer_loops.append(loops[outer_index])
        for index, loop in enumerate(loops):
            if index != outer_index:
                interior_loops.append(loop)
                interior_regions.append(region)
    loop_a, loop_b = outer_loops
    openings: list[PlateHole | PlateCap | PlateCone | PlateTorus] = []
    for region, loop in zip(interior_regions, interior_loops, strict=True):
        openings.extend(_plate_openings(segmentation.patches, region, [loop], mesh_vertices))
    if any(isinstance(opening, PlateCone) for opening in openings):
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_cone_multiregion_unsupported",
            "conical bosses are supported only on a single freeform plate region",
        )
    if any(isinstance(opening, PlateCap) for opening in openings):
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_multiregion_caps",
            "analytic caps on multi-region plates are not supported yet",
        )
    if any(isinstance(opening, PlateTorus) for opening in openings):
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_multiregion_tori",
            "torus beads spanning a crease network are not supported",
        )
    holes = tuple(opening for opening in openings if isinstance(opening, PlateHole))
    positions_a, ids_a = _region_corner_cycle(mesh_vertices, loop_a, settings)
    positions_b, ids_b = _region_corner_cycle(mesh_vertices, loop_b, settings)

    shared = set(ids_a) & set(ids_b)
    if len(shared) != 2:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_crease_corners",
            (
                "the two freeform regions must share exactly two boundary "
                f"corners (the crease endpoints), found {len(shared)}"
            ),
        )
    crease_a = [k for k in range(4) if ids_a[k] in shared and ids_a[(k + 1) % 4] in shared]
    crease_b = [k for k in range(4) if ids_b[k] in shared and ids_b[(k + 1) % 4] in shared]
    if len(crease_a) != 1 or len(crease_b) != 1:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_crease_corners",
            "the shared crease must span exactly one boundary chain of each region",
        )
    ka = crease_a[0]
    ms_id, me_id = ids_a[ka], ids_a[(ka + 1) % 4]
    a0_id, a3_id = ids_a[(ka - 1) % 4], ids_a[(ka + 2) % 4]
    kb = crease_b[0]
    if ids_b[kb] == ms_id:
        b1_id, b2_id = ids_b[(kb - 1) % 4], ids_b[(kb + 2) % 4]
        chain_ms, chain_me = (kb - 1) % 4, (kb + 1) % 4
    else:
        b1_id, b2_id = ids_b[(kb + 2) % 4], ids_b[(kb - 1) % 4]
        chain_ms, chain_me = (kb + 1) % 4, (kb - 1) % 4

    line_a_in = _region_chain_line(mesh_vertices, loop_a, positions_a, (ka - 1) % 4, settings)
    line_a_out = _region_chain_line(mesh_vertices, loop_a, positions_a, (ka + 1) % 4, settings)
    line_a_far = _region_chain_line(mesh_vertices, loop_a, positions_a, (ka + 2) % 4, settings)
    line_b_ms = _region_chain_line(mesh_vertices, loop_b, positions_b, chain_ms, settings)
    line_b_me = _region_chain_line(mesh_vertices, loop_b, positions_b, chain_me, settings)
    line_b_far = _region_chain_line(mesh_vertices, loop_b, positions_b, (kb + 2) % 4, settings)

    corner_0 = _line_intersection(*line_a_far, *line_a_in)
    crease_start = _line_intersection(*line_a_in, *line_b_ms)
    corner_1 = _line_intersection(*line_b_ms, *line_b_far)
    corner_2 = _line_intersection(*line_b_far, *line_b_me)
    crease_end = _line_intersection(*line_b_me, *line_a_out)
    corner_3 = _line_intersection(*line_a_out, *line_a_far)
    corners = np.asarray([corner_0, corner_1, corner_2, corner_3])

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
            f"outer boundary corners deviate {coplanarity:g} mm from a common plane",
        )
    # The crease endpoints may sit above the rectangle, but each must lie in
    # its wall plane or the pentagon wall face cannot be planar.
    for label, point, wall_origin, wall_along in (
        ("start", crease_start, corners[0], corners[1] - corners[0]),
        ("end", crease_end, corners[2], corners[3] - corners[2]),
    ):
        wall_normal = np.cross(wall_along, rectangle_normal)
        wall_normal = wall_normal / max(float(np.linalg.norm(wall_normal)), 1e-300)
        offset = abs(float((point - wall_origin) @ wall_normal))
        if offset > settings.boundary_line_tolerance_mm:
            raise CurvedPatchError(
                "fitting boundary",
                "curved_patch_crease_off_wall",
                (
                    f"crease {label} point deviates {offset:g} mm from its wall "
                    f"plane (limit {settings.boundary_line_tolerance_mm:g} mm)"
                ),
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

    bottom_origin, bottom_normal = _bottom_plane(segmentation.patches, region_a, region_b)
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

    faces_a = mesh_faces[np.asarray(region_a.triangle_ids, dtype=np.int64)]
    faces_b = mesh_faces[np.asarray(region_b.triangle_ids, dtype=np.int64)]
    try:
        halves = (
            reindexed_chart_region(mesh_vertices, faces_a, (a0_id, ms_id, me_id, a3_id)),
            reindexed_chart_region(mesh_vertices, faces_b, (ms_id, b1_id, b2_id, me_id)),
        )
        charts = tuple(_parameterize_half(half) for half in halves)
    except ChartParameterizationError as exc:
        raise CurvedPatchError("parameterizing chart", exc.code, str(exc)) from exc

    return _CreaseContext(
        region_ids=(region_a.id, region_b.id),
        holes=holes,
        halves=halves,
        charts=(charts[0], charts[1]),
        corners=corners,
        crease_start=crease_start,
        crease_end=crease_end,
        rectangle_normal=rectangle_normal,
        prism_vector=rectangle_normal * height,
        segmentation_counts=dict(segmentation.counts_by_type),
        cache_faces=np.vstack([faces_a, faces_b]),
    )


def _reconstruct_crease_network(
    mesh: trimesh.Trimesh,
    segmentation: SegmentationResult,
    settings: CurvedPatchSettings,
    network_settings: CurvedNetworkSettings,
    guard: _StageGuard,
    *,
    fit_cache: CurvedFitCache | None,
    source_sha256: str | None,
    smooth_pairs: set[frozenset[str]] | None = None,
) -> CurvedNetworkResult:
    """Jointly fit two adjacent freeform regions sharing one real boundary.

    The shared pole row is aliased into single unknowns across both patches
    (G0 exactly zero by construction). By default the join is a declared
    ``crease`` with no tangent coupling and must stay sharp. When the user
    overrides the boundary to smooth, the same C1 rows used for artificial
    cuts couple the tangents, the curve is declared ``smooth``, and the G1
    angle gate replaces the sharpness gate -- if the data is genuinely
    creased the deviation gates reject the smoothed fit rather than
    fabricating the user's intent.
    """

    if network_settings.force_split:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_force_split_unsupported",
            (
                "forceSplit applies to single-region plates; two freeform "
                "regions already form a crease network"
            ),
        )
    if settings.budget.maximum_patches < 2:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_patch_budget",
            "the patch budget does not allow a two-patch crease network",
        )
    context = _crease_context(mesh, segmentation, settings)
    guard.stage("parameterizing chart", 20.0)
    degree = settings.fit.degree
    corners = context.corners
    smooth_join = bool(smooth_pairs) and frozenset(context.region_ids) in (smooth_pairs or set())
    curve_id = "smooth-0" if smooth_join else "crease-0"
    layout = "smooth-join-network" if smooth_join else "crease-network"

    pole_cap = min(
        settings.budget.maximum_total_control_points,
        settings.budget.maximum_solve_unknowns,
    )
    cache_key: str | None = None
    if fit_cache is not None:
        cache_key = fit_cache.key(
            source_sha256 or mesh_content_sha256(mesh),
            settings,
            network_settings,
            (np.asarray(mesh.vertices, dtype=np.float64), context.cache_faces),
            extras={"smoothJoin": True} if smooth_join else None,
        )
        cached = fit_cache.load(cache_key)
        if cached is not None:
            guard.stage("assembling solid", 70.0)
            network = SurfaceNetwork.from_artifact(cached["network"])
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
                for entry in cached["iterations"]
            )
            guard.stage("finished", 100.0)
            return CurvedNetworkResult(
                solid=solid,
                network=network,
                artifact_sha256=network.artifact_sha256(),
                charts=context.charts,
                iterations=iterations,
                residual_maximum=float(cached["residualMaximum"]),
                residual_rms=float(cached["residualRms"]),
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
                candidates=tuple(dict(candidate) for candidate in cached["candidates"]),
                cache_status="hit",
                sewing_tolerance_mm=settings.sewing_tolerance_mm,
            )

    guard.stage("fitting surface", 35.0)
    samples = []
    real_counts: list[int] = []
    for half, chart in zip(context.halves, context.charts, strict=True):
        sample_uv, sample_points, sample_weights = chart_lattice_samples(
            half.vertices, half.faces, chart.uv
        )
        keep = sample_weights > 0.0
        sample_uv = sample_uv[keep]
        sample_points = sample_points[keep]
        sample_weights = sample_weights[keep]
        real_counts.append(len(sample_uv))
        if half.hole_loops:
            # Weak synthetic fill across recognized-hole rims, exactly as in
            # the single-region path; excluded from the convergence gate and
            # trimmed away by the hole subtraction anyway.
            fill_weight = 0.05 * float(np.median(sample_weights))
            fill_uv, fill_points, fill_weights = _hole_fill_samples(
                chart, half.vertices, half.hole_loops, fill_weight
            )
            sample_uv = np.concatenate([sample_uv, fill_uv])
            sample_points = np.concatenate([sample_points, fill_points])
            sample_weights = np.concatenate([sample_weights, fill_weights])
        samples.append((sample_uv, sample_points, sample_weights))

    half_corners = (
        np.asarray([corners[0], context.crease_start, context.crease_end, corners[3]]),
        np.asarray([context.crease_start, corners[1], corners[2], context.crease_end]),
    )
    smallest = min(len(points) for _, points, _ in samples)
    sample_span_cap = max(1, int(np.sqrt(smallest / 2.0)) - degree)
    budget_span_cap = max(1, math.isqrt(pole_cap // 2) - degree)
    maximum_spans = max(
        settings.fit.initial_spans,
        min(settings.fit.maximum_spans, sample_span_cap, budget_span_cap),
    )
    spans = settings.fit.initial_spans
    iterations_list: list[FitIteration] = []
    best: tuple[list[np.ndarray], np.ndarray, np.ndarray] | None = None
    for _ in range(settings.fit.maximum_refinements + 1):
        guard.checkpoint()
        control = spans + degree
        knots = open_uniform_knots(control, degree)
        greville = greville_abscissae(knots, degree)
        # Pin the three straight outer chains of each region; the shared
        # boundary row stays a FREE pole row aliased across both patches.
        # For a crease there is deliberately NO tangent coupling, so the
        # joint fit keeps the dihedral the data demands instead of smoothing
        # it away; a user-declared smooth join adds the same C1 rows the
        # artificial cut uses.
        fixed_sets: list[dict[tuple[int, int], np.ndarray]] = []
        for side, side_corners in enumerate(half_corners):
            fixed = rectangle_boundary_poles(side_corners, greville, greville)
            for j in range(1, control - 1):
                del fixed[(control - 1, j) if side == 0 else (0, j)]
            fixed_sets.append(fixed)
        shared_poles = [((0, (control - 1, j)), (1, (0, j))) for j in range(control)]
        constraints = (
            [
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
            if smooth_join
            else []
        )

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
                constraint_weight=network_settings.smooth_override_coupling_weight,
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
            [uv_state[side][: real_counts[side]] for side in range(2)],
            [
                (
                    samples[side][0][: real_counts[side]],
                    samples[side][1][: real_counts[side]],
                    samples[side][2][: real_counts[side]],
                )
                for side in range(2)
            ],
            poles,
            knots,
            degree,
            settings.fit.reprojection_steps,
        )
        iterations_list.append(
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
    control = len(knots) - degree - 1
    candidates = [
        {
            "layout": layout,
            "converged": bool(residuals.max() <= settings.fit_tolerance_mm),
            "residualMaximum": float(residuals.max()),
            "residualRms": float(np.sqrt(np.mean(residuals**2))),
            "controlPoints": 2 * control * control - control,
            "chosen": False,
        }
    ]
    if residuals.max() > settings.fit_tolerance_mm:
        raise CurvedPatchError(
            "fitting surface",
            "curved_patch_tolerance_not_met",
            (
                f"maximum network fit residual {residuals.max():g} mm exceeds "
                f"{settings.fit_tolerance_mm:g} mm within the span budget"
            ),
        )
    candidates[0]["chosen"] = True

    curve_poles = np.asarray(poles[0][-1], dtype=np.float64)
    vertices = (
        *(NetworkVertex(f"corner-{index}", corners[index]) for index in range(4)),
        NetworkVertex(f"{curve_id}-start", context.crease_start),
        NetworkVertex(f"{curve_id}-end", context.crease_end),
    )
    curve = NetworkCurve(
        id=curve_id,
        degree=degree,
        knots=knots,
        poles=curve_poles,
        start_vertex_id=f"{curve_id}-start",
        end_vertex_id=f"{curve_id}-end",
        continuity="smooth" if smooth_join else "crease",
    )
    patch_a = NetworkPatch(
        id="patch-0",
        degree=degree,
        knots_u=knots,
        knots_v=knots,
        poles=poles[0],
        corner_vertex_ids=("corner-0", f"{curve_id}-start", f"{curve_id}-end", "corner-3"),
        shared_boundaries={"u1": curve_id},
    )
    patch_b = NetworkPatch(
        id="patch-1",
        degree=degree,
        knots_u=knots,
        knots_v=knots,
        poles=poles[1],
        corner_vertex_ids=(f"{curve_id}-start", "corner-1", "corner-2", f"{curve_id}-end"),
        shared_boundaries={"u0": curve_id},
    )
    network = SurfaceNetwork(
        units="mm", vertices=vertices, curves=(curve,), patches=(patch_a, patch_b)
    )

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
                layout,
                network,
                tuple(iterations_list),
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
        charts=context.charts,
        iterations=tuple(iterations_list),
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
        holes=context.holes,
        hole_cutters=cutters,
        candidates=tuple(candidates),
        cache_status="stored" if fit_cache is not None else "uncached",
        sewing_tolerance_mm=settings.sewing_tolerance_mm,
    )


def reconstruct_plate_network(
    mesh: trimesh.Trimesh,
    *,
    settings: CurvedPatchSettings | None = None,
    network_settings: CurvedNetworkSettings | None = None,
    progress: ProgressCallback | None = None,
    should_cancel: Callable[[], bool] | None = None,
    fit_cache: CurvedFitCache | None = None,
    source_sha256: str | None = None,
    patch_overrides: dict[str, dict[str, Any]] | None = None,
) -> CurvedNetworkResult:
    """Reconstruct a plate as a shared-topology patch network.

    One freeform region: fits one patch when the budget allows it; otherwise
    (or when forced) cuts the chart along a deterministic interior path and
    fits both halves jointly with a C1 coupling across the artificial smooth
    boundary. Two adjacent freeform regions: fits both jointly with the real
    crease boundary aliased and declared ``crease`` (sharp, no coupling).
    Two regions separated by one recognized torus are fitted into one
    rectangular chart across the hidden annulus, then fused with the recorded
    analytic torus. Either way everything assembles on common OCCT edges with
    exact iso pcurves.
    """

    settings = settings or CurvedPatchSettings()
    settings.validate()
    network_settings = network_settings or CurvedNetworkSettings()
    network_settings.validate()
    guard = _StageGuard(settings.budget, progress, should_cancel)

    guard.stage("segmenting mesh", 5.0)
    segmentation, smooth_pairs = _segment_with_overrides(mesh, settings, patch_overrides)
    freeform_count = sum(
        1 for patch in segmentation.patches if patch.kind in ("freeform", "unknown")
    )
    if freeform_count != 1 and any(patch.kind == "cone" for patch in segmentation.patches):
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_cone_multiregion_unsupported",
            "conical bosses are supported only on a single freeform plate region",
        )
    torus_context = (
        _torus_plate_context(mesh, segmentation, settings) if freeform_count == 2 else None
    )
    if freeform_count == 2 and torus_context is None:
        return _reconstruct_crease_network(
            mesh,
            segmentation,
            settings,
            network_settings,
            guard,
            fit_cache=fit_cache,
            source_sha256=source_sha256,
            smooth_pairs=smooth_pairs,
        )
    context = torus_context or _plate_context(mesh, settings, segmentation=segmentation)
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
    for supplemental in context.supplemental_regions:
        extra_uv, extra_points, extra_weights = chart_lattice_samples(
            supplemental.vertices, supplemental.faces, supplemental.uv
        )
        extra_valid = extra_weights > 0.0
        sample_uv = np.concatenate([sample_uv, extra_uv[extra_valid]])
        sample_points = np.concatenate([sample_points, extra_points[extra_valid]])
        sample_weights = np.concatenate([sample_weights, extra_weights[extra_valid]])
    real_sample_count = len(sample_uv)
    if context.hole_loops:
        fill_weight = 0.05 * float(np.median(sample_weights))
        fill_uv, fill_points, fill_weights = _hole_fill_samples(
            context.chart,
            context.chart_vertices,
            context.hole_loops,
            fill_weight,
            fill_analytics=context.fill_analytics,
            normal=context.rectangle_normal,
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
    layout = "torus-single-patch" if context.tori else "single-patch"
    candidates.append(
        {
            "layout": layout,
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
        fusers = _cap_fusers(context.caps)
        cone_fusers = _cone_fusers(context.cones)
        torus_fusers = _torus_fusers(context.tori)
        solid = _plate_solid_from_network(
            network,
            corners,
            context.prism_vector,
            cutters,
            settings.sewing_tolerance_mm,
            cap_fusers=fusers,
            cone_fusers=cone_fusers,
            torus_fusers=torus_fusers,
        )
        guard.stage("validating solid", 90.0)
        face_surfaces, comparison, evidence = _network_gates(
            mesh,
            solid,
            network,
            settings,
            network_settings,
            expected_cylinders=len(context.holes),
            expected_spheres=len(context.caps),
            expected_cones=len(context.cones),
            expected_face_count=(
                5
                + len(network.patches)
                + len(context.holes)
                + len(context.caps)
                + len(context.cones)
                if context.cones
                else None
            ),
            expected_tori=len(context.tori),
        )
        if fit_cache is not None and cache_key is not None:
            fit_cache.store(
                cache_key,
                _fit_cache_payload(
                    layout,
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
            caps=context.caps,
            cap_fusers=fusers,
            cones=context.cones,
            cone_fusers=cone_fusers,
            tori=context.tori,
            torus_fusers=torus_fusers,
            candidates=tuple(candidates),
            cache_status="stored" if fit_cache is not None else "uncached",
            sewing_tolerance_mm=settings.sewing_tolerance_mm,
        )

    if context.holes or context.caps or context.cones or context.tori:
        raise CurvedPatchError(
            "cutting chart",
            "curved_patch_holes_unsupported_split",
            "chart cutting across regions with holes or analytic bosses is not supported yet; "
            "the single-patch layout did not meet tolerance",
        )

    if context.freeform_locked:
        raise CurvedPatchError(
            "cutting chart",
            "curved_patch_locked_split",
            "the freeform patch is locked; unlock it to allow splitting into a two-patch network",
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
            # Analytic-fuser keys are present only when non-empty so existing
            # cap- and cone-free artifacts keep their historical bytes.
            **(
                {"caps": [fuser.to_dict() for fuser in result.cap_fusers]}
                if result.cap_fusers
                else {}
            ),
            **(
                {"cones": [fuser.to_dict() for fuser in result.cone_fusers]}
                if result.cone_fusers
                else {}
            ),
            **(
                {"tori": [fuser.to_dict() for fuser in result.torus_fusers]}
                if result.torus_fusers
                else {}
            ),
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
    fusers = tuple(CapFuser.from_dict(entry) for entry in assembly.get("caps", []))
    cone_fusers = tuple(ConeFuser.from_dict(entry) for entry in assembly.get("cones", []))
    torus_fusers = tuple(TorusFuser.from_dict(entry) for entry in assembly.get("tori", []))
    return _plate_solid_from_network(
        network,
        corners,
        prism_vector,
        cutters,
        float(assembly["sewingToleranceMm"]),
        cap_fusers=fusers,
        cone_fusers=cone_fusers,
        torus_fusers=torus_fusers,
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
    fusers = _cap_fusers(context.caps)
    cone_fusers = _cone_fusers(context.cones)
    torus_fusers = _torus_fusers(context.tori)
    solid = _plate_solid_from_network(
        network,
        corners,
        context.prism_vector,
        cutters,
        settings.sewing_tolerance_mm,
        cap_fusers=fusers,
        cone_fusers=cone_fusers,
        torus_fusers=torus_fusers,
    )
    guard.stage("validating solid", 90.0)
    face_surfaces, comparison, evidence = _network_gates(
        mesh,
        solid,
        network,
        settings,
        network_settings,
        expected_cylinders=len(context.holes),
        expected_spheres=len(context.caps),
        expected_cones=len(context.cones),
        expected_face_count=(
            5 + len(network.patches) + len(context.holes) + len(context.caps) + len(context.cones)
            if context.cones
            else None
        ),
        expected_tori=len(context.tori),
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
        caps=context.caps,
        cap_fusers=fusers,
        cones=context.cones,
        cone_fusers=cone_fusers,
        tori=context.tori,
        torus_fusers=torus_fusers,
        candidates=tuple(dict(candidate) for candidate in payload["candidates"]),
        cache_status="hit",
        sewing_tolerance_mm=settings.sewing_tolerance_mm,
    )


__all__ = [
    "PLATE_ARTIFACT_SCHEMA",
    "CapFuser",
    "ConeFuser",
    "CurvedNetworkResult",
    "CurvedNetworkSettings",
    "CurvedPatchError",
    "CurvedPatchResult",
    "CurvedPatchSettings",
    "HoleCutter",
    "PlateCap",
    "PlateCone",
    "PlateHole",
    "PlateTorus",
    "ProgressCallback",
    "ReconstructionBudget",
    "TorusFuser",
    "assemble_single_patch_plate",
    "chart_lattice_samples",
    "plate_artifact_bytes",
    "plate_artifact_payload",
    "plate_artifact_sha256",
    "rebuild_plate_solid",
    "reconstruct_plate_network",
    "reconstruct_single_patch_plate",
]
