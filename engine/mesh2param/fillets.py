"""Route curvature fillet bands into loop-global constant-radius groups."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal

import numpy as np
import trimesh
from shapely.geometry import LineString, Point

from .sections import (
    CircleRadiusFit,
    SectionStack,
    SectionStackSettings,
    extract_section_stack,
    fit_section_circle_radius,
)
from .segmentation import (
    SegmentationResult,
    SegmentationSettings,
    SurfacePatch,
    segment_mesh,
)


@dataclass(frozen=True, slots=True)
class FilletRoutingSettings:
    segmentation: SegmentationSettings = field(
        default_factory=lambda: SegmentationSettings(enable_curvature_subsegmentation=True)
    )
    sections: SectionStackSettings = field(default_factory=SectionStackSettings)
    maximum_cap_radius_delta_mm: float = 0.02
    maximum_loop_fit_residual_mm: float = 0.02
    maximum_source_triangle_ids: int = 8192

    def validate(self) -> None:
        if not self.segmentation.enable_curvature_subsegmentation:
            raise ValueError("fillet routing requires curvature sub-segmentation")
        self.segmentation.validate()
        self.sections.validate()
        if self.maximum_cap_radius_delta_mm <= 0 or self.maximum_loop_fit_residual_mm <= 0:
            raise ValueError("fillet radius tolerances must be positive")
        if self.maximum_source_triangle_ids < 1:
            raise ValueError("fillet evidence limit must be positive")


@dataclass(frozen=True, slots=True)
class FilletBandAssignment:
    patch_id: str
    cap_side: Literal["lower", "upper"]
    loop_index: int
    median_loop_distance_mm: float
    curvature_radius_mm: float | None
    triangle_ids: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "patchId": self.patch_id,
            "capSide": self.cap_side,
            "loopIndex": self.loop_index,
            "medianLoopDistanceMm": self.median_loop_distance_mm,
            "curvatureRadiusMm": self.curvature_radius_mm,
            "triangleIds": list(self.triangle_ids),
        }


@dataclass(frozen=True, slots=True)
class FilletRadiusGroup:
    id: str
    radius_mm: float
    band_patch_ids: tuple[str, ...]
    assignments: tuple[FilletBandAssignment, ...]
    cap_radius_fits: tuple[CircleRadiusFit, CircleRadiusFit]
    maximum_cap_radius_delta_mm: float
    loop_fit_rms_residual_mm: float
    loop_fit_maximum_residual_mm: float
    stable_along_loop: bool
    source_triangle_ids: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "radiusMm": self.radius_mm,
            "bandPatchIds": list(self.band_patch_ids),
            "assignments": [assignment.to_dict() for assignment in self.assignments],
            "capRadiusFits": {
                "lower": self.cap_radius_fits[0].to_dict(),
                "upper": self.cap_radius_fits[1].to_dict(),
            },
            "maximumCapRadiusDeltaMm": self.maximum_cap_radius_delta_mm,
            "loopFitRmsResidualMm": self.loop_fit_rms_residual_mm,
            "loopFitMaximumResidualMm": self.loop_fit_maximum_residual_mm,
            "stableAlongLoop": self.stable_along_loop,
            "sourceTriangleIds": list(self.source_triangle_ids),
        }


@dataclass(frozen=True, slots=True)
class FilletDiagnostic:
    code: str
    message: str
    measured: dict[str, float | int | str] = field(default_factory=dict)
    source_triangle_ids: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "measured": dict(sorted(self.measured.items())),
            "sourceTriangleIds": list(self.source_triangle_ids),
        }


@dataclass(frozen=True, slots=True)
class FilletBandAnalysis:
    assignments: tuple[FilletBandAssignment, ...]
    groups: tuple[FilletRadiusGroup, ...]
    diagnostics: tuple[FilletDiagnostic, ...]
    section_radius_fit: CircleRadiusFit

    def to_dict(self) -> dict[str, Any]:
        return {
            "assignments": [assignment.to_dict() for assignment in self.assignments],
            "groups": [group.to_dict() for group in self.groups],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "sectionRadiusFit": self.section_radius_fit.to_dict(),
        }


def _fillet_patches(segmentation: SegmentationResult) -> tuple[SurfacePatch, ...]:
    return tuple(
        patch
        for patch in segmentation.patches
        if patch.curvature_evidence is not None
        and patch.curvature_evidence.curvature_class == "fillet-band"
    )


def _assign_band(
    mesh: trimesh.Trimesh,
    patch: SurfacePatch,
    stack: SectionStack,
) -> FilletBandAssignment:
    centroid_offset = float(np.dot(np.asarray(patch.centroid), np.asarray(stack.axis)))
    midpoint = 0.5 * (stack.cap_offsets_mm[0] + stack.cap_offsets_mm[1])
    cap_side: Literal["lower", "upper"] = "lower" if centroid_offset < midpoint else "upper"
    reference = stack.slices[stack.reference_slice_index]
    faces = np.asarray(mesh.faces, dtype=np.int64)[list(patch.triangle_ids)]
    vertex_ids = np.unique(faces.reshape(-1))
    projected = stack.frame.project(np.asarray(mesh.vertices, dtype=np.float64)[vertex_ids])
    loop_distances: list[tuple[float, int]] = []
    for loop in reference.loops:
        line = LineString(loop.points_mm)
        distances = np.asarray(
            [line.distance(Point(float(point[0]), float(point[1]))) for point in projected],
            dtype=np.float64,
        )
        loop_distances.append((float(np.median(distances)), loop.index))
    median_distance, loop_index = min(loop_distances)
    evidence = patch.curvature_evidence
    return FilletBandAssignment(
        patch.id,
        cap_side,
        loop_index,
        median_distance,
        evidence.estimated_minimum_radius_mm if evidence is not None else None,
        patch.triangle_ids,
    )


def evaluate_fillet_radius_group(
    assignments: tuple[FilletBandAssignment, ...],
    global_fit: CircleRadiusFit,
    lower_fit: CircleRadiusFit,
    upper_fit: CircleRadiusFit,
    settings: FilletRoutingSettings,
) -> tuple[FilletRadiusGroup | None, FilletDiagnostic | None]:
    """Accept one constant-radius group or emit variable-radius evidence."""

    evidence_ids = tuple(
        sorted({face_id for item in assignments for face_id in item.triangle_ids})
    )[: settings.maximum_source_triangle_ids]
    complete_outer_pair = (
        len(assignments) == 2
        and {assignment.cap_side for assignment in assignments} == {"lower", "upper"}
        and all(assignment.loop_index == 0 for assignment in assignments)
    )
    fits_complete = all(
        fit.accepted and fit.radius_mm is not None
        for fit in (global_fit, lower_fit, upper_fit)
    )
    if not complete_outer_pair or not fits_complete:
        return None, FilletDiagnostic(
            "incomplete-fillet-band-routing",
            "fillet evidence does not form one lower/upper outer-loop radius group",
            {
                "assignmentCount": len(assignments),
                "lowerBandCount": sum(item.cap_side == "lower" for item in assignments),
                "upperBandCount": sum(item.cap_side == "upper" for item in assignments),
            },
            evidence_ids,
        )
    assert global_fit.radius_mm is not None
    assert lower_fit.radius_mm is not None
    assert upper_fit.radius_mm is not None
    cap_delta = abs(lower_fit.radius_mm - upper_fit.radius_mm)
    loop_rms = float(global_fit.rms_residual_mm or 0.0)
    loop_maximum = float(global_fit.maximum_residual_mm or 0.0)
    stable = (
        cap_delta <= settings.maximum_cap_radius_delta_mm
        and loop_maximum <= settings.maximum_loop_fit_residual_mm
    )
    if not stable:
        return None, FilletDiagnostic(
            "variable-fillet-radius",
            "lower and upper loop evidence does not support one constant fillet radius",
            {
                "lowerRadiusMm": lower_fit.radius_mm,
                "upperRadiusMm": upper_fit.radius_mm,
                "radiusDeltaMm": cap_delta,
                "loopRmsResidualMm": loop_rms,
                "loopMaximumResidualMm": loop_maximum,
            },
            evidence_ids,
        )
    ordered = tuple(sorted(assignments, key=lambda item: (item.cap_side, item.patch_id)))
    return (
        FilletRadiusGroup(
            "fillet-group.outer",
            global_fit.radius_mm,
            tuple(item.patch_id for item in ordered),
            ordered,
            (lower_fit, upper_fit),
            cap_delta,
            loop_rms,
            loop_maximum,
            True,
            evidence_ids,
        ),
        None,
    )


def analyze_fillet_bands(
    mesh: trimesh.Trimesh,
    settings: FilletRoutingSettings | None = None,
    *,
    segmentation: SegmentationResult | None = None,
    section_stack: SectionStack | None = None,
) -> FilletBandAnalysis:
    """Enable curvature routing and group both outer cap fillet bands."""

    settings = settings or FilletRoutingSettings()
    settings.validate()
    active_segmentation = segmentation or segment_mesh(
        mesh,
        replace(settings.segmentation, enable_curvature_subsegmentation=True),
    )
    stack = section_stack or extract_section_stack(mesh, settings.sections)
    patches = _fillet_patches(active_segmentation)
    if not patches:
        return FilletBandAnalysis((), (), (), stack.radius_fit)
    assignments = tuple(_assign_band(mesh, patch, stack) for patch in patches)
    lower_fit = fit_section_circle_radius(
        stack,
        cap_side="lower",
        settings=settings.sections,
    )
    upper_fit = fit_section_circle_radius(
        stack,
        cap_side="upper",
        settings=settings.sections,
    )
    group, diagnostic = evaluate_fillet_radius_group(
        assignments,
        stack.radius_fit,
        lower_fit,
        upper_fit,
        settings,
    )
    return FilletBandAnalysis(
        assignments,
        (group,) if group is not None else (),
        (diagnostic,) if diagnostic is not None else (),
        stack.radius_fit,
    )


__all__ = [
    "FilletBandAnalysis",
    "FilletBandAssignment",
    "FilletDiagnostic",
    "FilletRadiusGroup",
    "FilletRoutingSettings",
    "analyze_fillet_bands",
    "evaluate_fillet_radius_group",
]
