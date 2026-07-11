"""Planar patch-boundary extraction for measured sketch evidence."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
import trimesh
from scipy.optimize import least_squares

from .frame import CoordinateFrame
from .segmentation import ResidualStats, SurfacePatch

LoopKind = Literal["circle", "closedLineLoop", "openBoundary"]


@dataclass(frozen=True, slots=True)
class SketchExtractionSettings:
    circle_fit_tolerance_mm: float = 0.02
    minimum_circle_coverage_deg: float = 300.0
    collinear_tolerance_mm: float = 0.01


@dataclass(frozen=True, slots=True)
class ExtractedLoop:
    id: str
    patch_id: str
    kind: LoopKind
    coordinate_dimensions: tuple[int, int]
    source_vertex_ids: tuple[int, ...]
    points_mm: tuple[tuple[float, float], ...] = ()
    center_mm: tuple[float, float] | None = None
    radius_mm: float | None = None
    residuals_mm: ResidualStats | None = None
    coverage_deg: float | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["patchId"] = result.pop("patch_id")
        result["coordinateDimensions"] = list(result.pop("coordinate_dimensions"))
        result["sourceVertexIds"] = list(result.pop("source_vertex_ids"))
        result["pointsMm"] = [list(point) for point in result.pop("points_mm")]
        center = result.pop("center_mm")
        result["centerMm"] = list(center) if center is not None else None
        result["radiusMm"] = result.pop("radius_mm")
        result["residualsMm"] = (
            self.residuals_mm.to_dict() if self.residuals_mm is not None else None
        )
        result.pop("residuals_mm")
        result["coverageDeg"] = result.pop("coverage_deg")
        return result


@dataclass(frozen=True, slots=True)
class ExtractedSketches:
    loops: tuple[ExtractedLoop, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": {
                kind: sum(loop.kind == kind for loop in self.loops)
                for kind in ("circle", "closedLineLoop", "openBoundary")
            },
            "warnings": list(self.warnings),
            "loops": [loop.to_dict() for loop in self.loops],
        }


@dataclass(frozen=True, slots=True)
class InferredProfile:
    points_yz_mm: tuple[tuple[float, float], ...]
    extrusion_distance_mm: float
    evidence_ids: tuple[str, ...]
    confidence: float


def _residual_stats(values: np.ndarray) -> ResidualStats:
    absolute = np.abs(values)
    return ResidualStats(
        rms=float(np.sqrt(np.mean(absolute * absolute))),
        median=float(np.median(absolute)),
        p95=float(np.quantile(absolute, 0.95)),
        maximum=float(np.max(absolute)),
    )


def _circle(points: np.ndarray) -> tuple[np.ndarray, float, ResidualStats, float]:
    x_values, y_values = points[:, 0], points[:, 1]
    design = np.column_stack((2 * x_values, 2 * y_values, np.ones(len(points))))
    target = x_values * x_values + y_values * y_values
    center_x, center_y, constant = np.linalg.lstsq(design, target, rcond=None)[0]
    radius = math.sqrt(max(float(constant + center_x * center_x + center_y * center_y), 0.0))

    def errors(parameters: np.ndarray) -> np.ndarray:
        x_center, y_center, candidate_radius = parameters
        return np.asarray(np.hypot(x_values - x_center, y_values - y_center) - candidate_radius)

    fit = least_squares(
        errors,
        np.asarray((center_x, center_y, radius)),
        ftol=1e-13,
        xtol=1e-13,
        gtol=1e-13,
    )
    center_x, center_y, radius = (float(value) for value in fit.x)
    angles = np.mod(np.arctan2(y_values - center_y, x_values - center_x), 2 * np.pi)
    sorted_angles = np.sort(angles)
    gaps = np.diff(np.concatenate((sorted_angles, sorted_angles[:1] + 2 * np.pi)))
    coverage = math.degrees(2 * np.pi - float(np.max(gaps)))
    return (
        np.asarray((center_x, center_y)),
        radius,
        _residual_stats(errors(fit.x)),
        coverage,
    )


def _simplify_collinear(points: np.ndarray, tolerance: float) -> np.ndarray:
    result = [np.asarray(point, dtype=np.float64) for point in points]
    changed = True
    while changed and len(result) > 3:
        changed = False
        keep: list[np.ndarray] = []
        for index, point in enumerate(result):
            previous = result[(index - 1) % len(result)]
            following = result[(index + 1) % len(result)]
            segment = following - previous
            length_squared = float(np.dot(segment, segment))
            if length_squared <= 1e-20:
                changed = True
                continue
            fraction = float(np.dot(point - previous, segment) / length_squared)
            projected = previous + np.clip(fraction, 0.0, 1.0) * segment
            forward = float(np.dot(point - previous, following - point)) >= 0
            if forward and float(np.linalg.norm(point - projected)) <= tolerance:
                changed = True
            else:
                keep.append(point)
        result = keep
    simplified = np.asarray(result)
    signed_area = 0.5 * float(
        np.sum(
            simplified[:, 0] * np.roll(simplified[:, 1], -1)
            - simplified[:, 1] * np.roll(simplified[:, 0], -1)
        )
    )
    if signed_area < 0:
        simplified = simplified[::-1]
    start = min(
        range(len(simplified)),
        key=lambda index: (
            round(float(simplified[index, 0]) / tolerance),
            round(float(simplified[index, 1]) / tolerance),
        ),
    )
    return np.asarray(np.roll(simplified, -start, axis=0))


def extract_planar_sketches(
    mesh: trimesh.Trimesh,
    patches: tuple[SurfacePatch, ...] | list[SurfacePatch],
    frame: CoordinateFrame,
    settings: SketchExtractionSettings | None = None,
) -> ExtractedSketches:
    settings = settings or SketchExtractionSettings()
    local_vertices = frame.world_to_local(np.asarray(mesh.vertices, dtype=np.float64))
    loops: list[ExtractedLoop] = []
    warnings: list[str] = []
    for patch in sorted(patches, key=lambda item: item.id):
        if patch.kind != "plane" or patch.plane_normal is None:
            continue
        normal_local = frame.axes.T @ np.asarray(patch.plane_normal)
        fixed_dimension = int(np.argmax(np.abs(normal_local)))
        dimensions = tuple(index for index in range(3) if index != fixed_dimension)
        if len(dimensions) != 2:
            raise AssertionError("a 3D plane must leave two sketch dimensions")
        dimension_pair = (dimensions[0], dimensions[1])
        for index, boundary in enumerate(patch.boundary_loops, start=1):
            loop_id = f"{patch.id}.loop.{index:03d}"
            if not boundary.closed:
                loops.append(
                    ExtractedLoop(
                        loop_id,
                        patch.id,
                        "openBoundary",
                        dimension_pair,
                        boundary.vertex_ids,
                    )
                )
                warnings.append(f"{loop_id} is open and was not converted into a profile")
                continue
            points = local_vertices[list(boundary.vertex_ids)][:, list(dimension_pair)]
            if len(points) >= 8:
                center, radius, residuals, coverage = _circle(points)
                if (
                    residuals.p95 <= settings.circle_fit_tolerance_mm
                    and coverage >= settings.minimum_circle_coverage_deg
                ):
                    loops.append(
                        ExtractedLoop(
                            loop_id,
                            patch.id,
                            "circle",
                            dimension_pair,
                            boundary.vertex_ids,
                            center_mm=(float(center[0]), float(center[1])),
                            radius_mm=radius,
                            residuals_mm=residuals,
                            coverage_deg=coverage,
                        )
                    )
                    continue
            simplified = _simplify_collinear(points, settings.collinear_tolerance_mm)
            loops.append(
                ExtractedLoop(
                    loop_id,
                    patch.id,
                    "closedLineLoop",
                    dimension_pair,
                    boundary.vertex_ids,
                    points_mm=tuple((float(point[0]), float(point[1])) for point in simplified),
                )
            )
    return ExtractedSketches(tuple(loops), tuple(dict.fromkeys(warnings)))


def infer_l_profile(
    patches: tuple[SurfacePatch, ...] | list[SurfacePatch],
    sketches: ExtractedSketches,
    frame: CoordinateFrame,
) -> InferredProfile:
    """Match the two six-line end patches that support one base extrusion."""

    patch_by_id = {patch.id: patch for patch in patches}
    candidates: list[tuple[float, SurfacePatch, ExtractedLoop]] = []
    for loop in sketches.loops:
        if (
            loop.kind != "closedLineLoop"
            or loop.coordinate_dimensions != (1, 2)
            or len(loop.points_mm) != 6
        ):
            continue
        patch = patch_by_id[loop.patch_id]
        if patch.plane_normal is None or patch.plane_origin is None:
            continue
        normal_local = frame.axes.T @ np.asarray(patch.plane_normal)
        if int(np.argmax(np.abs(normal_local))) != 0:
            continue
        offset = float(
            np.dot(np.asarray(patch.plane_origin) - np.asarray(frame.origin), frame.axes[:, 0])
        )
        candidates.append((offset, patch, loop))
    if len(candidates) != 2:
        raise ValueError(
            "L-profile inference requires exactly two matched six-line end loops; "
            f"found {len(candidates)}"
        )
    candidates.sort(key=lambda candidate: candidate[0])
    low, high = candidates
    if any(
        np.linalg.norm(np.asarray(left) - np.asarray(right)) > 0.05
        for left, right in zip(low[2].points_mm, high[2].points_mm, strict=True)
    ):
        raise ValueError("end profiles do not match within 0.05 mm")
    return InferredProfile(
        points_yz_mm=low[2].points_mm,
        extrusion_distance_mm=high[0] - low[0],
        evidence_ids=(low[1].id, high[1].id, low[2].id, high[2].id),
        confidence=min(low[1].confidence, high[1].confidence, frame.confidence),
    )


__all__ = [
    "ExtractedLoop",
    "ExtractedSketches",
    "InferredProfile",
    "LoopKind",
    "SketchExtractionSettings",
    "extract_planar_sketches",
    "infer_l_profile",
]
