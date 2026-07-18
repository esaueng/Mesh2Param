"""Deterministic planar section evidence for near-prismatic meshes.

The section stack is evidence only: it never edits or smooths the source mesh.
It identifies the dominant extrusion direction, assembles bounded closed loops,
tracks support motion through the thickness, and fits the inset series expected
from a constant-radius top/bottom fillet.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import numpy as np
import trimesh
from scipy.optimize import minimize_scalar

from .prismatic import ProjectionFrame, make_projection_frame
from .tessellation import MeshArtifact, Tessellation, write_glb


@dataclass(frozen=True, slots=True)
class SectionStackSettings:
    """Explicit safety and evidence bounds for section extraction."""

    section_count: int = 32
    cap_normal_angle_deg: float = 2.0
    cap_level_merge_tolerance_mm: float = 0.03
    minimum_primary_extent_mm: float = 0.1
    closure_tolerance_mm: float = 0.01
    gap_bridge_tolerance_mm: float = 0.05
    collinear_tolerance_mm: float = 1e-5
    stationary_tolerance_mm: float = 0.03
    fillet_detection_inset_mm: float = 0.08
    fillet_fit_rms_tolerance_mm: float = 0.03
    fillet_fit_maximum_tolerance_mm: float = 0.08
    minimum_fillet_radius_mm: float = 0.1
    maximum_fillet_radius_fraction: float = 0.45
    maximum_loops_per_section: int = 16
    maximum_points_per_loop: int = 4096
    maximum_evidence_triangles_per_section: int = 4096
    maximum_diagnostic_triangle_ids: int = 512
    maximum_debug_segments_per_loop: int = 512

    def validate(self) -> None:
        if not 3 <= self.section_count <= 127:
            raise ValueError("section count must be in [3, 127]")
        if not 0 < self.cap_normal_angle_deg < 45:
            raise ValueError("cap normal angle must be in (0, 45) degrees")
        positive = (
            self.cap_level_merge_tolerance_mm,
            self.minimum_primary_extent_mm,
            self.closure_tolerance_mm,
            self.gap_bridge_tolerance_mm,
            self.collinear_tolerance_mm,
            self.stationary_tolerance_mm,
            self.fillet_detection_inset_mm,
            self.fillet_fit_rms_tolerance_mm,
            self.fillet_fit_maximum_tolerance_mm,
            self.minimum_fillet_radius_mm,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("section length and residual tolerances must be positive")
        if self.closure_tolerance_mm > self.gap_bridge_tolerance_mm:
            raise ValueError("closure tolerance cannot exceed the gap bridge tolerance")
        if not 0 < self.maximum_fillet_radius_fraction < 0.5:
            raise ValueError("maximum fillet radius fraction must be in (0, 0.5)")
        if self.maximum_loops_per_section < 1 or self.maximum_points_per_loop < 4:
            raise ValueError("section loop safety limits are too small")
        if (
            self.maximum_evidence_triangles_per_section < 1
            or self.maximum_diagnostic_triangle_ids < 1
            or self.maximum_debug_segments_per_loop < 3
        ):
            raise ValueError("section artifact safety limits are too small")


@dataclass(frozen=True, slots=True)
class SectionDiagnostic:
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
class SectionLoop:
    index: int
    points_mm: tuple[tuple[float, float], ...]
    signed_area_mm2: float
    bounds_mm: tuple[float, float, float, float]
    closure_error_mm: float
    gap_bridged: bool
    is_hole: bool
    corner_count: int
    motion: Literal["stationary", "moving"] = "stationary"
    support_deviation_mm: float = 0.0

    @property
    def array(self) -> np.ndarray:
        return np.asarray(self.points_mm, dtype=np.float64)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "pointsMm": [list(point) for point in self.points_mm],
            "signedAreaMm2": self.signed_area_mm2,
            "boundsMm": list(self.bounds_mm),
            "closureErrorMm": self.closure_error_mm,
            "gapBridged": self.gap_bridged,
            "isHole": self.is_hole,
            "cornerCount": self.corner_count,
            "motion": self.motion,
            "supportDeviationMm": self.support_deviation_mm,
        }


@dataclass(frozen=True, slots=True)
class SectionSlice:
    index: int
    offset_mm: float
    normalized_height: float
    loops: tuple[SectionLoop, ...]
    source_triangle_ids: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "offsetMm": self.offset_mm,
            "normalizedHeight": self.normalized_height,
            "loops": [loop.to_dict() for loop in self.loops],
            "sourceTriangleIds": list(self.source_triangle_ids),
        }


@dataclass(frozen=True, slots=True)
class RadiusSample:
    height_from_nearest_cap_mm: float
    measured_inset_mm: float
    predicted_inset_mm: float

    def to_dict(self) -> dict[str, float]:
        return {
            "heightFromNearestCapMm": self.height_from_nearest_cap_mm,
            "measuredInsetMm": self.measured_inset_mm,
            "predictedInsetMm": self.predicted_inset_mm,
        }


@dataclass(frozen=True, slots=True)
class CircleRadiusFit:
    accepted: bool
    radius_mm: float | None
    rms_residual_mm: float | None
    maximum_residual_mm: float | None
    maximum_measured_inset_mm: float
    samples: tuple[RadiusSample, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "radiusMm": self.radius_mm,
            "rmsResidualMm": self.rms_residual_mm,
            "maximumResidualMm": self.maximum_residual_mm,
            "maximumMeasuredInsetMm": self.maximum_measured_inset_mm,
            "samples": [sample.to_dict() for sample in self.samples],
        }


@dataclass(frozen=True, slots=True)
class SectionStack:
    axis: tuple[float, float, float]
    frame: ProjectionFrame
    cap_offsets_mm: tuple[float, float]
    slices: tuple[SectionSlice, ...]
    reference_slice_index: int
    section_to_section_deviation_mm: float
    radius_fit: CircleRadiusFit
    blind_feature_detected: bool
    tapered_extrusion_detected: bool
    diagnostics: tuple[SectionDiagnostic, ...] = ()

    @property
    def primary_extent_mm(self) -> float:
        return self.cap_offsets_mm[1] - self.cap_offsets_mm[0]

    @property
    def reference_slice(self) -> SectionSlice:
        return self.slices[self.reference_slice_index]

    def to_dict(self) -> dict[str, Any]:
        return {
            "axis": list(self.axis),
            "frame": asdict(self.frame),
            "capOffsetsMm": list(self.cap_offsets_mm),
            "primaryExtentMm": self.primary_extent_mm,
            "referenceSliceIndex": self.reference_slice_index,
            "sectionToSectionDeviationMm": self.section_to_section_deviation_mm,
            "blindFeatureDetected": self.blind_feature_detected,
            "taperedExtrusionDetected": self.tapered_extrusion_detected,
            "radiusFit": self.radius_fit.to_dict(),
            "slices": [section.to_dict() for section in self.slices],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


class SectionExtractionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _canonical_axis(axis: np.ndarray) -> np.ndarray:
    axis = np.asarray(axis, dtype=np.float64)
    magnitude = float(np.linalg.norm(axis))
    if magnitude <= 1e-15 or not np.all(np.isfinite(axis)):
        raise SectionExtractionError("invalid-section-axis", "section axis is not finite")
    axis = axis / magnitude
    dominant = int(np.argmax(np.abs(axis)))
    return -axis if axis[dominant] < 0 else axis


def estimate_section_axis(mesh: trimesh.Trimesh) -> np.ndarray:
    """Estimate the dominant cap normal from an area-weighted normal moment."""

    normals = np.asarray(mesh.face_normals, dtype=np.float64)
    areas = np.asarray(mesh.area_faces, dtype=np.float64)
    if len(normals) < 4 or not np.all(np.isfinite(normals)) or not np.all(areas > 0):
        raise SectionExtractionError(
            "insufficient-section-evidence", "section analysis requires finite positive-area faces"
        )
    moment = (normals.T * areas) @ normals
    _, vectors = np.linalg.eigh(moment)
    return _canonical_axis(vectors[:, -1])


def _primary_cap_offsets(
    mesh: trimesh.Trimesh,
    axis: np.ndarray,
    settings: SectionStackSettings,
) -> tuple[float, float]:
    normals = np.asarray(mesh.face_normals, dtype=np.float64)
    areas = np.asarray(mesh.area_faces, dtype=np.float64)
    centers = np.asarray(mesh.triangles_center, dtype=np.float64)
    aligned = np.flatnonzero(
        np.abs(normals @ axis) >= math.cos(math.radians(settings.cap_normal_angle_deg))
    )
    if len(aligned) < 2:
        raise SectionExtractionError("no-primary-caps", "fewer than two cap-aligned faces exist")

    samples = sorted(
        (
            float(np.dot(centers[face_id], axis)),
            float(areas[face_id]),
        )
        for face_id in aligned
    )
    groups: list[list[float]] = []
    for offset, area in samples:
        if not groups:
            groups.append([offset * area, area])
            continue
        mean = groups[-1][0] / groups[-1][1]
        if abs(offset - mean) <= settings.cap_level_merge_tolerance_mm:
            groups[-1][0] += offset * area
            groups[-1][1] += area
        else:
            groups.append([offset * area, area])
    levels = [(weighted / area, area) for weighted, area in groups]
    pairs = [
        (min(left[0], right[0]), max(left[0], right[0]), min(left[1], right[1]))
        for index, left in enumerate(levels)
        for right in levels[index + 1 :]
        if abs(right[0] - left[0]) >= settings.minimum_primary_extent_mm
    ]
    if not pairs:
        raise SectionExtractionError("no-primary-caps", "no separated cap pair was measured")
    low, high, _ = max(pairs, key=lambda pair: (pair[2], pair[1] - pair[0], -pair[0]))
    return low, high


def _signed_area(points: np.ndarray) -> float:
    body = points[:-1]
    following = np.roll(body, -1, axis=0)
    return 0.5 * float(np.sum(body[:, 0] * following[:, 1] - following[:, 0] * body[:, 1]))


def _remove_collinear(points: np.ndarray, tolerance: float) -> np.ndarray:
    body = [np.asarray(point, dtype=np.float64) for point in points[:-1]]
    changed = True
    while changed and len(body) > 3:
        changed = False
        retained: list[np.ndarray] = []
        for index, point in enumerate(body):
            previous = body[index - 1]
            following = body[(index + 1) % len(body)]
            chord = following - previous
            length = float(np.linalg.norm(chord))
            if length <= 1e-15:
                changed = True
                continue
            distance = (
                abs(
                    float(chord[0] * (previous[1] - point[1]) - chord[1] * (previous[0] - point[0]))
                )
                / length
            )
            between = float(np.dot(point - previous, point - following)) <= tolerance * tolerance
            if distance <= tolerance and between:
                changed = True
                continue
            retained.append(point)
        body = retained
    if len(body) < 3:
        raise SectionExtractionError(
            "degenerate-section-loop", "section loop has fewer than three corners"
        )
    result = np.asarray(body, dtype=np.float64)
    return np.vstack((result, result[0]))


def _corner_count(points: np.ndarray) -> int:
    body = points[:-1]
    count = 0
    for index, point in enumerate(body):
        before = point - body[index - 1]
        after = body[(index + 1) % len(body)] - point
        if np.linalg.norm(before) <= 1e-12 or np.linalg.norm(after) <= 1e-12:
            continue
        cosine = float(np.dot(before, after) / (np.linalg.norm(before) * np.linalg.norm(after)))
        if math.degrees(math.acos(float(np.clip(cosine, -1.0, 1.0)))) >= 5.0:
            count += 1
    return count


def _assemble_loop(
    raw_points: np.ndarray,
    settings: SectionStackSettings,
) -> tuple[np.ndarray, float, bool]:
    points = np.asarray(raw_points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3:
        raise SectionExtractionError("invalid-section-loop", "section path is not a 3-D polyline")
    if len(points) > settings.maximum_points_per_loop:
        raise SectionExtractionError(
            "section-loop-limit",
            f"section loop exceeds {settings.maximum_points_per_loop} points",
        )
    closure_error = float(np.linalg.norm(points[-1] - points[0]))
    if closure_error > settings.gap_bridge_tolerance_mm:
        raise SectionExtractionError(
            "open-section-loop",
            f"section loop closure gap {closure_error:g} mm exceeds the bounded bridge tolerance",
        )
    gap_bridged = closure_error > settings.closure_tolerance_mm
    if closure_error > 1e-12:
        points = np.vstack((points, points[0]))
    return points, closure_error, gap_bridged


def _project_and_classify_loops(
    raw_loops: list[np.ndarray],
    frame: ProjectionFrame,
    settings: SectionStackSettings,
) -> tuple[SectionLoop, ...]:
    if not raw_loops:
        raise SectionExtractionError("empty-section", "section plane produced no loops")
    if len(raw_loops) > settings.maximum_loops_per_section:
        raise SectionExtractionError(
            "section-loop-limit",
            f"section plane exceeds {settings.maximum_loops_per_section} loops",
        )
    projected: list[SectionLoop] = []
    for index, raw in enumerate(raw_loops):
        assembled, closure_error, gap_bridged = _assemble_loop(raw, settings)
        points = frame.project(assembled)
        points = _remove_collinear(points, settings.collinear_tolerance_mm)
        area = _signed_area(points)
        bounds = (
            float(np.min(points[:-1, 0])),
            float(np.min(points[:-1, 1])),
            float(np.max(points[:-1, 0])),
            float(np.max(points[:-1, 1])),
        )
        projected.append(
            SectionLoop(
                index=index,
                points_mm=tuple((float(point[0]), float(point[1])) for point in points),
                signed_area_mm2=area,
                bounds_mm=bounds,
                closure_error_mm=closure_error,
                gap_bridged=gap_bridged,
                is_hole=False,
                corner_count=_corner_count(points),
            )
        )
    projected.sort(key=lambda loop: (-abs(loop.signed_area_mm2), loop.bounds_mm, loop.index))
    return tuple(
        replace(loop, index=index, is_hole=index > 0) for index, loop in enumerate(projected)
    )


def _support_deviation(bounds: tuple[float, ...], reference: tuple[float, ...]) -> float:
    return max(abs(value - expected) for value, expected in zip(bounds, reference, strict=True))


def _circle_inset(distance: np.ndarray, radius: float) -> np.ndarray:
    active = distance < radius
    radial = np.maximum(0.0, radius * radius - (radius - np.minimum(distance, radius)) ** 2)
    return np.where(active, radius - np.sqrt(radial), 0.0)


def _fit_circle_radius(
    slices: tuple[SectionSlice, ...],
    reference: SectionSlice,
    cap_offsets: tuple[float, float],
    settings: SectionStackSettings,
) -> CircleRadiusFit:
    reference_outer = reference.loops[0]
    distances: list[float] = []
    insets: list[float] = []
    for section in slices:
        outer = section.loops[0]
        current = outer.bounds_mm
        expected = reference_outer.bounds_mm
        support_insets = (
            current[0] - expected[0],
            current[1] - expected[1],
            expected[2] - current[2],
            expected[3] - current[3],
        )
        insets.append(max(0.0, float(np.median(np.asarray(support_insets)))))
        distances.append(
            min(section.offset_mm - cap_offsets[0], cap_offsets[1] - section.offset_mm)
        )
    distance_array = np.asarray(distances, dtype=np.float64)
    inset_array = np.asarray(insets, dtype=np.float64)
    maximum_radius = (cap_offsets[1] - cap_offsets[0]) * settings.maximum_fillet_radius_fraction
    maximum_inset = float(np.max(inset_array))
    if maximum_radius <= settings.minimum_fillet_radius_mm:
        return CircleRadiusFit(False, None, None, None, maximum_inset)
    optimized = minimize_scalar(
        lambda radius: float(np.mean((_circle_inset(distance_array, radius) - inset_array) ** 2)),
        bounds=(settings.minimum_fillet_radius_mm, maximum_radius),
        method="bounded",
        options={"xatol": 1e-10, "maxiter": 128},
    )
    radius = float(optimized.x)
    predicted = _circle_inset(distance_array, radius)
    residuals = np.abs(predicted - inset_array)
    rms = math.sqrt(float(np.mean(residuals**2)))
    maximum = float(np.max(residuals))
    accepted = (
        maximum_inset >= settings.fillet_detection_inset_mm
        and rms <= settings.fillet_fit_rms_tolerance_mm
        and maximum <= settings.fillet_fit_maximum_tolerance_mm
    )
    samples = tuple(
        RadiusSample(float(distance), float(measured), float(model))
        for distance, measured, model in zip(distance_array, inset_array, predicted, strict=True)
    )
    return CircleRadiusFit(accepted, radius, rms, maximum, maximum_inset, samples)


def _taper_evidence(
    slices: tuple[SectionSlice, ...],
    tolerance_mm: float,
) -> tuple[bool, float, float]:
    heights = np.asarray([section.normalized_height for section in slices], dtype=np.float64)
    supports = np.asarray([section.loops[0].bounds_mm for section in slices], dtype=np.float64)
    maximum_change = 0.0
    maximum_r_squared = 0.0
    detected = False
    for column in range(supports.shape[1]):
        values = supports[:, column]
        slope, intercept = np.polyfit(heights, values, 1)
        predicted = slope * heights + intercept
        residual_sum = float(np.sum((values - predicted) ** 2))
        total_sum = float(np.sum((values - np.mean(values)) ** 2))
        r_squared = 1.0 - residual_sum / total_sum if total_sum > 1e-18 else 0.0
        maximum_change = max(maximum_change, abs(float(slope)))
        maximum_r_squared = max(maximum_r_squared, r_squared)
        if abs(float(slope)) > tolerance_mm and r_squared >= 0.95:
            detected = True
    return detected, maximum_change, maximum_r_squared


def extract_section_stack(
    mesh: trimesh.Trimesh,
    settings: SectionStackSettings | None = None,
    *,
    axis: tuple[float, float, float] | np.ndarray | None = None,
) -> SectionStack:
    """Extract bounded, deterministic section evidence from an untouched mesh."""

    settings = settings or SectionStackSettings()
    settings.validate()
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise SectionExtractionError("empty-section-source", "section analysis requires a mesh")
    section_axis = (
        estimate_section_axis(mesh) if axis is None else _canonical_axis(np.asarray(axis))
    )
    cap_offsets = _primary_cap_offsets(mesh, section_axis, settings)
    extent = cap_offsets[1] - cap_offsets[0]
    frame = make_projection_frame(section_axis, section_axis * cap_offsets[0])
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    face_vertices = vertices[np.asarray(mesh.faces, dtype=np.int64)]
    face_offsets = face_vertices @ section_axis
    slices: list[SectionSlice] = []
    for index in range(settings.section_count):
        normalized = (index + 1) / (settings.section_count + 1)
        offset = cap_offsets[0] + normalized * extent
        plane = mesh.section(plane_origin=section_axis * offset, plane_normal=section_axis)
        if plane is None:
            raise SectionExtractionError("empty-section", f"section {index} produced no path")
        raw_loops = [np.asarray(points, dtype=np.float64) for points in plane.discrete]
        loops = _project_and_classify_loops(raw_loops, frame, settings)
        crossing = np.flatnonzero(
            (np.min(face_offsets, axis=1) <= offset + 1e-9)
            & (np.max(face_offsets, axis=1) >= offset - 1e-9)
        )
        if len(crossing) > settings.maximum_evidence_triangles_per_section:
            raise SectionExtractionError(
                "section-evidence-limit",
                f"section {index} exceeds the triangle evidence bound",
            )
        slices.append(
            SectionSlice(
                index,
                float(offset),
                float(normalized),
                loops,
                tuple(int(value) for value in crossing),
            )
        )

    middle_candidates = [
        index for index, section in enumerate(slices) if 0.4 <= section.normalized_height <= 0.6
    ]
    reference_index = min(
        middle_candidates,
        key=lambda index: (
            -abs(slices[index].loops[0].signed_area_mm2),
            abs(slices[index].normalized_height - 0.5),
            index,
        ),
    )
    reference = slices[reference_index]
    reference_by_role = [loop.bounds_mm for loop in reference.loops]
    classified_slices: list[SectionSlice] = []
    maximum_deviation = 0.0
    for section in slices:
        classified_loops: list[SectionLoop] = []
        for index, loop in enumerate(section.loops):
            if index >= len(reference_by_role):
                deviation = settings.stationary_tolerance_mm * 2.0
            else:
                deviation = _support_deviation(loop.bounds_mm, reference_by_role[index])
            maximum_deviation = max(maximum_deviation, deviation)
            classified_loops.append(
                replace(
                    loop,
                    motion="stationary"
                    if deviation <= settings.stationary_tolerance_mm
                    else "moving",
                    support_deviation_mm=deviation,
                )
            )
        classified_slices.append(replace(section, loops=tuple(classified_loops)))
    final_slices = tuple(classified_slices)
    reference = final_slices[reference_index]
    radius_fit = _fit_circle_radius(final_slices, reference, cap_offsets, settings)
    loop_counts = {len(section.loops) for section in final_slices}
    blind_feature = len(loop_counts) > 1
    taper_evidence = _taper_evidence(
        final_slices,
        settings.stationary_tolerance_mm,
    )
    tapered = not radius_fit.accepted and taper_evidence[0]
    moving_sections = [section for section in final_slices if section.loops[0].motion == "moving"]
    diagnostic_sections = moving_sections or list(final_slices)
    evidence_ids = tuple(
        sorted(
            {face_id for section in diagnostic_sections for face_id in section.source_triangle_ids}
        )[: settings.maximum_diagnostic_triangle_ids]
    )
    diagnostics: list[SectionDiagnostic] = []
    if radius_fit.accepted and radius_fit.radius_mm is not None:
        diagnostics.append(
            SectionDiagnostic(
                "fillet-band-detected",
                "section inset series fits a constant-radius circle model",
                {
                    "radiusMm": radius_fit.radius_mm,
                    "rmsResidualMm": radius_fit.rms_residual_mm or 0.0,
                    "maximumResidualMm": radius_fit.maximum_residual_mm or 0.0,
                },
                evidence_ids,
            )
        )
    if blind_feature:
        diagnostics.append(
            SectionDiagnostic(
                "unsupported-blind-feature",
                "section loop count changes through the primary extent",
                {"minimumLoopCount": min(loop_counts), "maximumLoopCount": max(loop_counts)},
                evidence_ids,
            )
        )
    if tapered:
        diagnostics.append(
            SectionDiagnostic(
                "unsupported-tapered-extrusion",
                "section supports follow a bounded linear taper",
                {
                    "maximumLinearSupportChangeMm": taper_evidence[1],
                    "maximumLinearFitRSquared": taper_evidence[2],
                },
                evidence_ids,
            )
        )
    return SectionStack(
        (
            float(section_axis[0]),
            float(section_axis[1]),
            float(section_axis[2]),
        ),
        frame,
        cap_offsets,
        final_slices,
        reference_index,
        maximum_deviation,
        radius_fit,
        blind_feature,
        tapered,
        tuple(diagnostics),
    )


def write_section_debug_glb(
    stack: SectionStack,
    path: str | Path,
    settings: SectionStackSettings | None = None,
) -> MeshArtifact:
    """Write deterministic thin ribbons for the measured section loops."""

    settings = settings or SectionStackSettings()
    settings.validate()
    half_width = max(stack.primary_extent_mm * 0.0005, 0.001)
    vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    for section in stack.slices:
        local_offset = section.offset_mm - stack.cap_offsets_mm[0]
        for loop in section.loops:
            body = loop.array[:-1]
            stride = max(1, math.ceil(len(body) / settings.maximum_debug_segments_per_loop))
            sampled = body[::stride]
            if len(sampled) < 3:
                continue
            for start, end in zip(sampled, np.roll(sampled, -1, axis=0), strict=True):
                direction = end - start
                length = float(np.linalg.norm(direction))
                if length <= 1e-12:
                    continue
                transverse = np.asarray((-direction[1], direction[0])) / length * half_width
                planar = np.asarray(
                    (start - transverse, start + transverse, end + transverse, end - transverse)
                )
                world = stack.frame.inverse(planar, offset=local_offset)
                base = len(vertices)
                vertices.extend(
                    (float(point[0]), float(point[1]), float(point[2])) for point in world
                )
                triangles.extend(((base, base + 1, base + 2), (base, base + 2, base + 3)))
    if not triangles:
        raise SectionExtractionError("empty-section-debug", "section stack has no debug segments")
    return write_glb(Tessellation(tuple(vertices), tuple(triangles), ()), path)


__all__ = [
    "CircleRadiusFit",
    "RadiusSample",
    "SectionDiagnostic",
    "SectionExtractionError",
    "SectionLoop",
    "SectionSlice",
    "SectionStack",
    "SectionStackSettings",
    "estimate_section_axis",
    "extract_section_stack",
    "write_section_debug_glb",
]
