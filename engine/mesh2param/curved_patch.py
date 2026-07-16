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

from dataclasses import dataclass, field
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
from .parameterization import (
    ChartParameterization,
    ChartParameterizationError,
    harmonic_square_parameterization,
)
from .segmentation import SegmentationSettings, SurfacePatch, segment_mesh
from .surface_fit import FittedPatch, SurfaceFitSettings, fit_bspline_patch
from .validation import classify_face_surfaces, validate_shape


class CurvedPatchError(ValueError):
    """A fail-closed single-patch reconstruction error with a stable code."""

    def __init__(self, phase: str, code: str, message: str) -> None:
        super().__init__(message)
        self.phase = phase
        self.code = code


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

    def validate(self) -> None:
        if self.fit_tolerance_mm <= 0.0 or self.surface_deviation_tolerance_mm <= 0.0:
            raise ValueError("tolerances must be positive")
        if self.boundary_line_tolerance_mm <= 0.0 or self.sewing_tolerance_mm <= 0.0:
            raise ValueError("boundary and sewing tolerances must be positive")
        if not 0.0 < self.plane_parallel_tolerance_deg < 90.0:
            raise ValueError("plane parallel tolerance must be in (0, 90) degrees")
        self.segmentation.validate()
        self.fit.validate()


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
    loops = [loop for loop in patch.boundary_loops if loop.closed]
    if len(patch.boundary_loops) != 1 or len(loops) != 1:
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_not_disk",
            "the freeform region must have exactly one closed boundary loop",
        )
    return patch


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


def reconstruct_single_patch_plate(
    mesh: trimesh.Trimesh,
    *,
    settings: CurvedPatchSettings | None = None,
) -> CurvedPatchResult:
    """Reconstruct one freeform-topped plate as an approximate curved B-Rep."""

    settings = settings or CurvedPatchSettings()
    settings.validate()

    segmentation = segment_mesh(mesh, settings.segmentation)
    freeform = _freeform_patch(segmentation.patches)
    bottom_origin, bottom_normal = _bottom_plane(segmentation.patches, freeform)

    # Reindex the freeform region as a standalone chart.
    triangle_ids = np.asarray(freeform.triangle_ids, dtype=np.int64)
    chart_faces_global = np.asarray(mesh.faces, dtype=np.int64)[triangle_ids]
    used_vertices = np.unique(chart_faces_global)
    local_index = np.full(len(mesh.vertices), -1, dtype=np.int64)
    local_index[used_vertices] = np.arange(len(used_vertices))
    chart_vertices = np.asarray(mesh.vertices, dtype=np.float64)[used_vertices]
    chart_faces = local_index[chart_faces_global]
    loop_global = np.asarray(freeform.boundary_loops[0].vertex_ids, dtype=np.int64)
    chart_loop = local_index[loop_global]
    if np.any(chart_loop < 0):
        raise CurvedPatchError(
            "segmenting mesh",
            "curved_patch_boundary_mismatch",
            "the freeform boundary loop references vertices outside the region",
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

    # Fit each boundary chain as a straight crease line and refine the corners.
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
                    f"(limit {settings.boundary_line_tolerance_mm:g} mm); curved "
                    "boundary networks arrive with Milestone 2"
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

    # Samples: vertices weighted by mixed area plus barycenters weighted by area.
    chart_mesh = trimesh.Trimesh(
        vertices=chart_vertices, faces=chart_faces, process=False, validate=False
    )
    face_areas = np.asarray(chart_mesh.area_faces, dtype=np.float64)
    vertex_weights = np.zeros(len(chart_vertices))
    for column in range(3):
        np.add.at(vertex_weights, chart_faces[:, column], face_areas / 3.0)

    # Interior samples come from a barycentric lattice whose density scales
    # with triangle area: large boundary fan triangles (straight crease edges
    # never subdivide) would otherwise leave whole knot spans without data.
    median_area = float(np.median(face_areas[face_areas > 0.0]))
    lattice_uv: list[np.ndarray] = [chart.uv]
    lattice_points: list[np.ndarray] = [chart_vertices]
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
        triangle_uv = chart.uv[chart_faces[selected]]
        triangle_points = chart_vertices[chart_faces[selected]]
        lattice_uv.append(np.einsum("kb,tbc->tkc", barycentric, triangle_uv).reshape(-1, 2))
        lattice_points.append(np.einsum("kb,tbc->tkc", barycentric, triangle_points).reshape(-1, 3))
        lattice_weights.append(np.repeat(face_areas[selected] / len(barycentric), len(barycentric)))
    sample_uv = np.concatenate(lattice_uv)
    sample_points = np.concatenate(lattice_points)
    sample_weights = np.concatenate(lattice_weights)
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

    # Prism from the crease rectangle to the fitted bottom plane.
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
    prism_vector = rectangle_normal * height

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

    counts = {
        kind: sum(1 for patch in segmentation.patches if patch.kind == kind)
        for kind in ("plane", "cylinder", "freeform", "unknown")
    }
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
        segmentation_counts=counts,
    )


__all__ = [
    "CurvedPatchError",
    "CurvedPatchResult",
    "CurvedPatchSettings",
    "assemble_single_patch_plate",
    "reconstruct_single_patch_plate",
]
