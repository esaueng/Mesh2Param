"""Evidence-backed coordinate-frame inference for bounded prismatic parts."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from itertools import pairwise
from typing import Any

import numpy as np
import trimesh

from .segmentation import SurfacePatch


class FrameInferenceError(ValueError):
    """Raised when the bounded frame heuristic has no honest unique answer."""


@dataclass(frozen=True, slots=True)
class FrameInferenceSettings:
    parallel_angle_deg: float = 1.0
    distinct_extent_tolerance_mm: float = 0.1
    plane_offset_merge_tolerance_mm: float = 0.05


@dataclass(frozen=True, slots=True)
class FrameCandidate:
    kind: str
    score: float
    confidence: float
    support_patch_ids: tuple[str, ...]
    details: dict[str, Any]
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["supportPatchIds"] = list(self.support_patch_ids)
        result.pop("support_patch_ids")
        return result


@dataclass(frozen=True, slots=True)
class CoordinateFrame:
    origin: tuple[float, float, float]
    x_axis: tuple[float, float, float]
    y_axis: tuple[float, float, float]
    z_axis: tuple[float, float, float]
    extents_mm: tuple[float, float, float]
    confidence: float
    chosen: FrameCandidate
    alternatives: tuple[FrameCandidate, ...]

    @property
    def axes(self) -> np.ndarray:
        return np.asarray(np.column_stack((self.x_axis, self.y_axis, self.z_axis)))

    def world_to_local(self, points: np.ndarray) -> np.ndarray:
        return np.asarray(
            (np.asarray(points, dtype=np.float64) - np.asarray(self.origin)) @ self.axes
        )

    def local_to_world(self, points: np.ndarray) -> np.ndarray:
        return np.asarray(
            np.asarray(points, dtype=np.float64) @ self.axes.T + np.asarray(self.origin)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin": list(self.origin),
            "xAxis": list(self.x_axis),
            "yAxis": list(self.y_axis),
            "zAxis": list(self.z_axis),
            "extentsMm": list(self.extents_mm),
            "confidence": self.confidence,
            "chosen": self.chosen.to_dict(),
            "alternatives": [candidate.to_dict() for candidate in self.alternatives],
        }


def _tuple3(vector: np.ndarray) -> tuple[float, float, float]:
    return float(vector[0]), float(vector[1]), float(vector[2])


def _canonical_direction(vector: np.ndarray) -> np.ndarray:
    result = np.asarray(vector, dtype=np.float64)
    result /= np.linalg.norm(result)
    dominant = int(np.argmax(np.abs(result)))
    return -result if result[dominant] < 0 else result


def _unique_offsets(values: list[float], tolerance: float) -> list[float]:
    result: list[float] = []
    for value in sorted(values):
        if not result or abs(value - result[-1]) > tolerance:
            result.append(value)
    return result


def infer_coordinate_frame(
    mesh: trimesh.Trimesh,
    patches: tuple[SurfacePatch, ...] | list[SurfacePatch],
    settings: FrameInferenceSettings | None = None,
) -> CoordinateFrame:
    """Infer the bracket frame without using its generating transform.

    The chosen bounded convention assigns the longest dominant span to X, the
    shortest to Y, and the remaining span to Z.  Equal spans are returned as an
    unsupported ambiguity rather than guessed.
    """

    settings = settings or FrameInferenceSettings()
    planes = [patch for patch in patches if patch.kind == "plane"]
    if len(planes) < 6:
        raise FrameInferenceError(
            f"dominant-plane frame requires at least six plane patches; found {len(planes)}"
        )
    cosine = math.cos(math.radians(settings.parallel_angle_deg))
    direction_lines: list[dict[str, Any]] = []
    for patch in sorted(planes, key=lambda item: (-item.area_mm2, item.id)):
        if patch.plane_normal is None:
            continue
        normal = _canonical_direction(np.asarray(patch.plane_normal))
        match = next(
            (
                line
                for line in direction_lines
                if abs(float(np.dot(normal, line["direction"]))) >= cosine
            ),
            None,
        )
        if match is None:
            direction_lines.append(
                {
                    "direction": normal,
                    "support": patch.area_mm2,
                    "patchIds": [patch.id],
                }
            )
        else:
            aligned = normal if float(np.dot(normal, match["direction"])) >= 0 else -normal
            accumulated = match["direction"] * match["support"] + aligned * patch.area_mm2
            match["support"] += patch.area_mm2
            match["direction"] = accumulated / np.linalg.norm(accumulated)
            match["patchIds"].append(patch.id)
    if len(direction_lines) != 3:
        raise FrameInferenceError(
            "expected exactly three dominant antipodal plane directions; "
            f"found {len(direction_lines)} (coarse facets or unsupported geometry)"
        )
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    for line in direction_lines:
        line["extent"] = float(np.ptp(vertices @ line["direction"]))
    by_extent = sorted(direction_lines, key=lambda line: line["extent"])
    extents = [float(line["extent"]) for line in by_extent]
    if any(
        abs(right - left) <= settings.distinct_extent_tolerance_mm
        for left, right in pairwise(extents)
    ):
        raise FrameInferenceError(
            "dominant extents are tied; preserve axis-permutation alternatives for user choice"
        )
    y_line, z_line, x_line = by_extent

    def choose_positive(line: dict[str, Any]) -> tuple[np.ndarray, list[float]]:
        options: list[tuple[float, int, np.ndarray, list[float]]] = []
        for sign_order, sign in enumerate((1.0, -1.0)):
            direction = sign * line["direction"]
            raw_offsets = [
                float(np.dot(np.asarray(patch.plane_origin), direction))
                for patch in planes
                if patch.plane_origin is not None
                and patch.plane_normal is not None
                and abs(float(np.dot(np.asarray(patch.plane_normal), direction))) >= cosine
            ]
            unique = _unique_offsets(raw_offsets, settings.plane_offset_merge_tolerance_mm)
            normalized = [value - unique[0] for value in unique]
            # The supported L-section has its inside thickness plane close to
            # the zero outer plane.  A mirrored choice yields 34/39 mm instead.
            inside_offset = normalized[1] if len(normalized) > 2 else math.inf
            options.append((inside_offset, sign_order, direction, normalized))
        _, _, direction, offsets = min(options, key=lambda item: (item[0], item[1]))
        return direction, offsets

    y_axis, y_offsets = choose_positive(y_line)
    z_axis, z_offsets = choose_positive(z_line)
    x_axis = np.cross(y_axis, z_axis)
    x_axis /= np.linalg.norm(x_axis)
    if abs(float(np.dot(x_axis, x_line["direction"]))) < cosine:
        raise FrameInferenceError(
            "right-handed axis completion disagrees with the third plane family"
        )
    z_axis = np.cross(x_axis, y_axis)
    z_axis /= np.linalg.norm(z_axis)
    axes = np.column_stack((x_axis, y_axis, z_axis))
    local_about_world_origin = vertices @ axes
    minimum = np.min(local_about_world_origin, axis=0)
    origin = axes @ minimum
    local = (vertices - origin) @ axes
    recovered_extents = np.ptp(local, axis=0)

    face_centers = np.asarray(mesh.triangles_center, dtype=np.float64)
    face_areas = np.asarray(mesh.area_faces, dtype=np.float64)
    center = np.average(face_centers, axis=0, weights=face_areas)
    centered = face_centers - center
    covariance = (centered * face_areas[:, None]).T @ centered / np.sum(face_areas)
    _, pca_axes = np.linalg.eigh(covariance)
    pca_axes = pca_axes[:, ::-1]
    pca_alignment = [
        max(abs(float(np.dot(pca_axes[:, index], axes[:, target]))) for target in range(3))
        for index in range(3)
    ]
    pca_angles = [
        math.degrees(math.acos(float(np.clip(value, -1.0, 1.0)))) for value in pca_alignment
    ]
    support_area = sum(patch.area_mm2 for patch in planes)
    support_fraction = support_area / float(mesh.area)
    orthogonality = max(
        abs(float(np.dot(x_axis, y_axis))),
        abs(float(np.dot(x_axis, z_axis))),
        abs(float(np.dot(y_axis, z_axis))),
    )
    score = support_fraction * (1.0 - min(orthogonality, 1.0))
    support_ids = tuple(sorted(patch.id for patch in planes))
    chosen = FrameCandidate(
        kind="dominant-plane-triad",
        score=score,
        confidence=score,
        support_patch_ids=support_ids,
        details={
            "supportAreaFraction": support_fraction,
            "orthogonalityError": orthogonality,
            "yPlaneOffsetsFromMinMm": y_offsets,
            "zPlaneOffsetsFromMinMm": z_offsets,
            "axisAssignmentConvention": "longest=X, shortest=Y, remaining=Z",
        },
    )
    alternatives = (
        FrameCandidate(
            kind="surface-area-weighted-pca",
            score=float(np.mean(pca_alignment)) * 0.65,
            confidence=float(np.mean(pca_alignment)) * 0.65,
            support_patch_ids=(),
            details={"anglesToNearestDominantAxisDeg": pca_angles},
            warning="PCA is skewed by L-section mass and is not the selected machining frame.",
        ),
        FrameCandidate(
            kind="x-polarity-convention",
            score=score,
            confidence=score,
            support_patch_ids=support_ids,
            details={"transform": "flip X and preserve right-handedness"},
            warning="X polarity can be geometrically tied for an X-symmetric bracket.",
        ),
    )
    return CoordinateFrame(
        origin=_tuple3(origin),
        x_axis=_tuple3(x_axis),
        y_axis=_tuple3(y_axis),
        z_axis=_tuple3(z_axis),
        extents_mm=_tuple3(recovered_extents),
        confidence=score,
        chosen=chosen,
        alternatives=alternatives,
    )


__all__ = [
    "CoordinateFrame",
    "FrameCandidate",
    "FrameInferenceError",
    "FrameInferenceSettings",
    "infer_coordinate_frame",
]
