"""Analytic reconstruction of meshes that are linear extrusions of 2-D profiles.

This module intentionally stops at geometric evidence.  It detects antipodal caps,
extracts their ordered boundary loops, and fits deterministic line/circular-arc
chains.  CADGraph construction and OpenCascade compilation live in their existing
layers so a rejected hypothesis can safely fall through to other reconstruction
paths.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from itertools import combinations
from typing import Any, Literal

import numpy as np
import trimesh
from shapely.geometry import LinearRing, Point, Polygon

from .segmentation import SurfacePatch


@dataclass(frozen=True, slots=True)
class PrismaticSettings:
    """Scale-aware tolerances for extrusion detection and profile fitting."""

    cap_normal_angle_deg: float = 2.0
    cap_area_relative_tolerance: float = 0.03
    cap_plane_tolerance_mm: float = 0.03
    cap_loop_matching_tolerance_mm: float = 0.08
    side_normal_rms_tolerance: float = 0.04
    side_normal_max_component: float = 0.12
    side_normal_required_fraction: float = 0.98
    minimum_extrusion_length_mm: float = 0.1
    line_rms_tolerance_mm: float = 0.025
    line_max_residual_tolerance_mm: float = 0.075
    arc_rms_tolerance_mm: float = 0.025
    arc_max_residual_tolerance_mm: float = 0.075
    minimum_primitive_length_mm: float = 0.1
    minimum_arc_sweep_deg: float = 8.0
    minimum_arc_sagitta_mm: float = 0.04
    maximum_radius_scale: float = 20.0
    primitive_count_penalty: float = 1.5
    breakpoint_penalty: float = 0.25
    maximum_profile_vertices: int = 1024
    maximum_interval_vertices: int = 512
    candidate_start_count: int = 4

    def validate(self) -> None:
        positive = (
            self.cap_plane_tolerance_mm,
            self.cap_loop_matching_tolerance_mm,
            self.minimum_extrusion_length_mm,
            self.line_rms_tolerance_mm,
            self.line_max_residual_tolerance_mm,
            self.arc_rms_tolerance_mm,
            self.arc_max_residual_tolerance_mm,
            self.minimum_primitive_length_mm,
            self.minimum_arc_sagitta_mm,
            self.maximum_radius_scale,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("prismatic length and residual tolerances must be positive")
        if not 0 < self.cap_normal_angle_deg < 90:
            raise ValueError("cap normal angle must be in (0, 90) degrees")
        if not 0 <= self.cap_area_relative_tolerance < 1:
            raise ValueError("cap area relative tolerance must be in [0, 1)")
        if not 0 < self.side_normal_required_fraction <= 1:
            raise ValueError("side normal required fraction must be in (0, 1]")
        if self.maximum_profile_vertices < 4 or self.maximum_interval_vertices < 3:
            raise ValueError("profile safety limits are too small")


@dataclass(frozen=True, slots=True)
class PrismaticDiagnostic:
    code: str
    message: str
    measured: dict[str, float | int | str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProjectionFrame:
    origin: tuple[float, float, float]
    u: tuple[float, float, float]
    v: tuple[float, float, float]
    w: tuple[float, float, float]

    @property
    def matrix(self) -> np.ndarray:
        return np.column_stack((self.u, self.v, self.w))

    def project(self, points: np.ndarray) -> np.ndarray:
        local = (np.asarray(points, dtype=np.float64) - np.asarray(self.origin)) @ self.matrix
        return np.asarray(local[:, :2])

    def inverse(self, points: np.ndarray, *, offset: float = 0.0) -> np.ndarray:
        points = np.asarray(points, dtype=np.float64)
        local = np.column_stack((points, np.full(len(points), float(offset))))
        return np.asarray(local @ self.matrix.T + np.asarray(self.origin))


@dataclass(frozen=True, slots=True)
class ProjectedLoop:
    vertex_ids: tuple[int, ...]
    points: tuple[tuple[float, float], ...]
    frame: ProjectionFrame
    signed_area: float
    is_hole: bool = False

    @property
    def array(self) -> np.ndarray:
        return np.asarray(self.points, dtype=np.float64)


@dataclass(frozen=True, slots=True)
class ProfilePrimitive:
    start: tuple[float, float]
    end: tuple[float, float]
    rms_residual_mm: float
    maximum_residual_mm: float
    length_mm: float
    tangent_to_next_deg: float | None = None

    @property
    def kind(self) -> str:
        raise NotImplementedError

    def start_tangent(self) -> np.ndarray:
        raise NotImplementedError

    def end_tangent(self) -> np.ndarray:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class LinePrimitive(ProfilePrimitive):
    @property
    def kind(self) -> Literal["line"]:
        return "line"

    def start_tangent(self) -> np.ndarray:
        vector = np.asarray(self.end) - np.asarray(self.start)
        return np.asarray(vector / np.linalg.norm(vector), dtype=np.float64)

    def end_tangent(self) -> np.ndarray:
        return self.start_tangent()


@dataclass(frozen=True, slots=True)
class ArcPrimitive(ProfilePrimitive):
    center: tuple[float, float] = (0.0, 0.0)
    radius_mm: float = 0.0
    sweep_deg: float = 0.0

    @property
    def kind(self) -> Literal["arc"]:
        return "arc"

    @property
    def clockwise(self) -> bool:
        return self.sweep_deg < 0

    def _tangent(self, point: tuple[float, float]) -> np.ndarray:
        radial = np.asarray(point) - np.asarray(self.center)
        tangent = np.asarray((-radial[1], radial[0]))
        if self.clockwise:
            tangent = -tangent
        return np.asarray(tangent / np.linalg.norm(tangent), dtype=np.float64)

    def start_tangent(self) -> np.ndarray:
        return self._tangent(self.start)

    def end_tangent(self) -> np.ndarray:
        return self._tangent(self.end)


type Primitive = LinePrimitive | ArcPrimitive


@dataclass(frozen=True, slots=True)
class ExtrusionCandidate:
    accepted: bool
    axis: tuple[float, float, float] | None
    distance_mm: float | None
    cap_patch_ids: tuple[str, str] | None
    cap_offsets_mm: tuple[float, float] | None
    frame: ProjectionFrame | None
    loops: tuple[ProjectedLoop, ...] = ()
    profiles: tuple[tuple[Primitive, ...], ...] = ()
    side_normal_rms: float | None = None
    confidence: float = 0.0
    diagnostics: tuple[PrismaticDiagnostic, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "axis": list(self.axis) if self.axis is not None else None,
            "distanceMm": self.distance_mm,
            "capPatchIds": list(self.cap_patch_ids) if self.cap_patch_ids else None,
            "capOffsetsMm": list(self.cap_offsets_mm) if self.cap_offsets_mm else None,
            "sideNormalRms": self.side_normal_rms,
            "confidence": self.confidence,
            "loops": [
                {
                    "vertexIds": list(loop.vertex_ids),
                    "pointsMm": [list(point) for point in loop.points],
                    "signedAreaMm2": loop.signed_area,
                    "isHole": loop.is_hole,
                }
                for loop in self.loops
            ],
            "profiles": [
                [
                    {
                        "kind": primitive.kind,
                        "start": list(primitive.start),
                        "end": list(primitive.end),
                        "rmsResidualMm": primitive.rms_residual_mm,
                        "maxResidualMm": primitive.maximum_residual_mm,
                        "lengthMm": primitive.length_mm,
                        "tangentToNextDeg": primitive.tangent_to_next_deg,
                        **(
                            {
                                "center": list(primitive.center),
                                "radiusMm": primitive.radius_mm,
                                "sweepDeg": primitive.sweep_deg,
                            }
                            if isinstance(primitive, ArcPrimitive)
                            else {}
                        ),
                    }
                    for primitive in profile
                ]
                for profile in self.profiles
            ],
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }


class PrismaticFitError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _unit(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float64)
    magnitude = float(np.linalg.norm(vector))
    if magnitude <= 1e-15:
        raise ValueError("cannot normalize a zero vector")
    return vector / magnitude


def _canonical_axis(vector: np.ndarray) -> np.ndarray:
    result = _unit(vector)
    dominant = int(np.argmax(np.abs(result)))
    return -result if result[dominant] < 0 else result


def fit_extrusion_axis(normals: np.ndarray, areas: np.ndarray) -> tuple[np.ndarray, float]:
    """Return the minimum-energy translational axis and area-weighted RMS residual."""

    normals = np.asarray(normals, dtype=np.float64)
    areas = np.asarray(areas, dtype=np.float64)
    if normals.ndim != 2 or normals.shape[1] != 3 or len(normals) != len(areas):
        raise ValueError("normals must be Nx3 with one area per normal")
    if len(normals) < 2 or np.any(areas <= 0) or not np.all(np.isfinite(normals)):
        raise ValueError("side-normal evidence must contain finite positive-area samples")
    magnitudes = np.linalg.norm(normals, axis=1)
    if np.any(magnitudes <= 1e-15):
        raise ValueError("side-normal evidence contains a zero normal")
    normalized = normals / magnitudes[:, None]
    matrix = (normalized * areas[:, None]).T @ normalized
    values, vectors = np.linalg.eigh(matrix)
    axis = _canonical_axis(vectors[:, int(np.argmin(values))])
    residual = math.sqrt(float(np.sum(areas * (normalized @ axis) ** 2) / np.sum(areas)))
    return axis, residual


def extract_cap_boundary_loops(
    mesh: trimesh.Trimesh, triangle_ids: tuple[int, ...] | list[int] | np.ndarray
) -> tuple[tuple[int, ...], ...]:
    """Extract deterministic closed patch-local loops from single-use triangle edges."""

    face_ids = np.asarray(triangle_ids, dtype=np.int64)
    if len(face_ids) == 0:
        raise PrismaticFitError("invalid_boundary_topology", "cap patch contains no triangles")
    edge_counts: dict[tuple[int, int], int] = {}
    for face in np.asarray(mesh.faces, dtype=np.int64)[face_ids]:
        for left, right in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = min(int(left), int(right)), max(int(left), int(right))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    boundary = {edge for edge, count in edge_counts.items() if count == 1}
    adjacency: dict[int, set[int]] = {}
    for left, right in boundary:
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    if not boundary or any(len(neighbors) != 2 for neighbors in adjacency.values()):
        raise PrismaticFitError(
            "invalid_boundary_topology",
            "cap boundary is empty, open, or branching",
        )
    remaining = set(boundary)
    loops: list[tuple[int, ...]] = []
    while remaining:
        first = min(remaining)
        start = min(first)
        previous = -1
        current = start
        loop = [start]
        while True:
            choices = sorted(neighbor for neighbor in adjacency[current] if neighbor != previous)
            following = next(
                (
                    neighbor
                    for neighbor in choices
                    if (min(current, neighbor), max(current, neighbor)) in remaining
                    or neighbor == start
                ),
                None,
            )
            if following is None:
                raise PrismaticFitError("invalid_boundary_topology", "cap loop did not close")
            remaining.discard((min(current, following), max(current, following)))
            if following == start:
                break
            loop.append(following)
            previous, current = current, following
            if len(loop) > len(adjacency):
                raise PrismaticFitError("invalid_boundary_topology", "cap loop traversal cycled")
        if len(loop) < 3:
            raise PrismaticFitError("invalid_boundary_topology", "cap loop has fewer than 3 points")
        loops.append(tuple(loop))
    vertices = np.asarray(mesh.vertices, dtype=np.float64)

    def loop_key(loop: tuple[int, ...]) -> tuple[tuple[float, float, float], int, tuple[int, ...]]:
        center = np.asarray(np.mean(vertices[list(loop)], axis=0), dtype=np.float64)
        coordinates = (
            float(round(center[0], 9)),
            float(round(center[1], 9)),
            float(round(center[2], 9)),
        )
        return coordinates, len(loop), loop

    loops.sort(key=loop_key)
    return tuple(loops)


def make_projection_frame(
    axis: np.ndarray,
    origin: np.ndarray,
    *,
    u_hint: np.ndarray | None = None,
) -> ProjectionFrame:
    w = _unit(axis)
    if u_hint is not None:
        trial = np.asarray(u_hint, dtype=np.float64)
        trial = trial - w * float(np.dot(trial, w))
    else:
        basis = np.eye(3)
        trial = basis[int(np.argmin(np.abs(basis @ w)))]
        trial = trial - w * float(np.dot(trial, w))
    u = _unit(trial)
    dominant = int(np.argmax(np.abs(u)))
    if u[dominant] < 0:
        u = -u
    v = _unit(np.cross(w, u))
    return ProjectionFrame(tuple(origin), tuple(u), tuple(v), tuple(w))


def _signed_area(points: np.ndarray) -> float:
    return 0.5 * float(
        np.sum(points[:, 0] * np.roll(points[:, 1], -1) - points[:, 1] * np.roll(points[:, 0], -1))
    )


def _canonicalize_loop(
    points: np.ndarray, vertex_ids: tuple[int, ...], *, clockwise: bool
) -> tuple[np.ndarray, tuple[int, ...], float]:
    keep = [0]
    for index in range(1, len(points)):
        if float(np.linalg.norm(points[index] - points[keep[-1]])) > 1e-12:
            keep.append(index)
    points = points[keep]
    ids = tuple(vertex_ids[index] for index in keep)
    if len(points) < 3:
        raise PrismaticFitError("invalid_boundary_topology", "loop collapses after deduplication")
    area = _signed_area(points)
    if math.isclose(area, 0.0, abs_tol=1e-12):
        raise PrismaticFitError("invalid_boundary_topology", "projected loop has zero area")
    if (area < 0) != clockwise:
        points = points[::-1]
        ids = ids[::-1]
        area = -area
    start = min(
        range(len(points)),
        key=lambda index: (
            round(float(points[index, 0]), 9),
            round(float(points[index, 1]), 9),
            ids[index],
        ),
    )
    return np.roll(points, -start, axis=0), ids[start:] + ids[:start], area


def project_loop_to_plane(
    points: np.ndarray,
    axis: np.ndarray,
    *,
    origin: np.ndarray | None = None,
    vertex_ids: tuple[int, ...] | None = None,
    frame: ProjectionFrame | None = None,
    clockwise: bool = False,
) -> ProjectedLoop:
    """Project an ordered 3-D loop and retain a reversible orthonormal frame."""

    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 3:
        raise ValueError("loop points must be an Nx3 array with N >= 3")
    frame = frame or make_projection_frame(axis, points[0] if origin is None else origin)
    ids = vertex_ids or tuple(range(len(points)))
    projected, ids, area = _canonicalize_loop(frame.project(points), ids, clockwise=clockwise)
    return ProjectedLoop(
        ids,
        tuple((float(point[0]), float(point[1])) for point in projected),
        frame,
        area,
        clockwise,
    )


def _resample_closed(points: np.ndarray, count: int) -> np.ndarray:
    closed = np.vstack((points, points[0]))
    lengths = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    cumulative = np.concatenate(([0.0], np.cumsum(lengths)))
    if cumulative[-1] <= 1e-12:
        raise PrismaticFitError("cap_boundary_mismatch", "cap loop has zero perimeter")
    targets = np.arange(count, dtype=np.float64) * cumulative[-1] / count
    indices = np.searchsorted(cumulative, targets, side="right") - 1
    indices = np.clip(indices, 0, len(lengths) - 1)
    fractions = (targets - cumulative[indices]) / lengths[indices]
    return np.asarray(
        closed[indices] + fractions[:, None] * (closed[indices + 1] - closed[indices]),
        dtype=np.float64,
    )


def match_projected_loops(
    left: ProjectedLoop, right: ProjectedLoop, tolerance_mm: float
) -> tuple[bool, float, int, bool]:
    """Compare closed loops under cyclic shift and reversed winding."""

    hausdorff = float(LinearRing(left.array).hausdorff_distance(LinearRing(right.array)))
    if hausdorff <= tolerance_mm:
        return True, hausdorff, 0, left.signed_area * right.signed_area < 0
    count = max(32, min(512, max(len(left.points), len(right.points))))
    left_points = _resample_closed(left.array, count)
    right_points = _resample_closed(right.array, count)
    best = (math.inf, 0, False)
    reversed_points = right_points[np.mod(-np.arange(count), count)]
    for reversed_winding, candidate in ((False, right_points), (True, reversed_points)):
        for shift in range(count):
            shifted = np.roll(candidate, shift, axis=0)
            rms = float(np.sqrt(np.mean(np.sum((left_points - shifted) ** 2, axis=1))))
            option = (rms, shift, reversed_winding)
            if option < best:
                best = option
    return best[0] <= tolerance_mm, best[0], best[1], best[2]


def fit_line_primitive(
    points: np.ndarray, settings: PrismaticSettings | None = None
) -> LinePrimitive | None:
    settings = settings or PrismaticSettings()
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 2:
        return None
    start, end = points[0], points[-1]
    length = float(np.linalg.norm(end - start))
    if length < settings.minimum_primitive_length_mm:
        return None
    centered = points - np.mean(points, axis=0)
    _, _, vectors = np.linalg.svd(centered, full_matrices=False)
    normal = vectors[-1]
    residuals = np.abs(centered @ normal)
    rms = float(np.sqrt(np.mean(residuals * residuals)))
    maximum = float(np.max(residuals))
    if rms > settings.line_rms_tolerance_mm or maximum > settings.line_max_residual_tolerance_mm:
        return None
    return LinePrimitive(tuple(start), tuple(end), rms, maximum, length)


def _circle_initial(points: np.ndarray) -> np.ndarray | None:
    design = np.column_stack((2 * points[:, 0], 2 * points[:, 1], np.ones(len(points))))
    target = np.sum(points * points, axis=1)
    solution, _, rank, _ = np.linalg.lstsq(design, target, rcond=None)
    return solution[:2] if rank >= 3 else None


def fit_arc_primitive(
    points: np.ndarray, settings: PrismaticSettings | None = None
) -> ArcPrimitive | None:
    """Fit a circle constrained through the interval endpoints using one center scalar."""

    settings = settings or PrismaticSettings()
    points = np.asarray(points, dtype=np.float64)
    # Four polygon corners can always be ambiguous with a circular segment.  Requiring
    # five ordered samples prevents sparse straight-edged caps from becoming invented arcs.
    if len(points) < 5 or len(np.unique(np.round(points, 12), axis=0)) < 5:
        return None
    start, end = points[0], points[-1]
    chord = end - start
    chord_length = float(np.linalg.norm(chord))
    if chord_length < settings.minimum_primitive_length_mm:
        return None
    midpoint = (start + end) / 2
    bisector = np.asarray((-chord[1], chord[0])) / chord_length
    scale = max(float(np.ptp(points, axis=0).max()), chord_length, 1.0)
    maximum_radius = settings.maximum_radius_scale * scale
    initial_center = _circle_initial(points)
    initial = (
        float(np.dot(initial_center - midpoint, bisector)) if initial_center is not None else 0.0
    )
    bound = math.sqrt(max(maximum_radius * maximum_radius - chord_length**2 / 4, 1.0))

    def residual(parameter: float) -> np.ndarray:
        center = midpoint + parameter * bisector
        radius = float(np.linalg.norm(start - center))
        return np.asarray(np.linalg.norm(points - center, axis=1) - radius, dtype=np.float64)

    parameter = float(np.clip(initial, -bound, bound))
    for _ in range(6):
        center = midpoint + parameter * bisector
        distances = np.linalg.norm(points - center, axis=1)
        endpoint_distance = max(float(np.linalg.norm(start - center)), 1e-15)
        values = distances - endpoint_distance
        derivatives = ((center - points) @ bisector) / np.maximum(distances, 1e-15) - float(
            np.dot(center - start, bisector)
        ) / endpoint_distance
        denominator = float(np.dot(derivatives, derivatives))
        if denominator <= 1e-20:
            break
        step = float(np.dot(values, derivatives) / denominator)
        parameter = float(np.clip(parameter - step, -bound, bound))
        if abs(step) <= 1e-12 * max(1.0, abs(parameter)):
            break
    center = midpoint + parameter * bisector
    radius = float(np.linalg.norm(start - center))
    values = np.abs(residual(parameter))
    rms = float(np.sqrt(np.mean(values * values)))
    maximum = float(np.max(values))
    if (
        not math.isfinite(radius)
        or radius > maximum_radius
        or rms > settings.arc_rms_tolerance_mm
        or maximum > settings.arc_max_residual_tolerance_mm
    ):
        return None
    angles = np.unwrap(np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0]))
    differences = np.diff(angles)
    direction = 1.0 if float(np.median(differences)) >= 0 else -1.0
    angular_slop = max(1e-4, settings.arc_max_residual_tolerance_mm / max(radius, 1e-9))
    if np.any(direction * differences < -angular_slop):
        return None
    chordal_deviation = radius * (1.0 - math.cos(float(np.max(np.abs(differences))) / 2.0))
    maximum = max(maximum, chordal_deviation)
    if maximum > settings.arc_max_residual_tolerance_mm:
        return None
    sweep = float(angles[-1] - angles[0])
    if abs(sweep) > 2 * math.pi + angular_slop:
        return None
    sweep_deg = math.degrees(sweep)
    sagitta = radius * (1 - math.cos(abs(sweep) / 2))
    if abs(sweep_deg) < settings.minimum_arc_sweep_deg or sagitta < settings.minimum_arc_sagitta_mm:
        return None
    return ArcPrimitive(
        tuple(start),
        tuple(end),
        rms,
        maximum,
        abs(radius * sweep),
        None,
        (float(center[0]), float(center[1])),
        radius,
        sweep_deg,
    )


def _primitive_cost(primitive: Primitive, settings: PrismaticSettings) -> float:
    if isinstance(primitive, LinePrimitive):
        residual = primitive.rms_residual_mm / settings.line_rms_tolerance_mm
        maximum = primitive.maximum_residual_mm / settings.line_max_residual_tolerance_mm
        complexity = 0.0
    else:
        residual = primitive.rms_residual_mm / settings.arc_rms_tolerance_mm
        maximum = primitive.maximum_residual_mm / settings.arc_max_residual_tolerance_mm
        complexity = 0.05
    return (
        residual
        + 0.25 * maximum
        + settings.primitive_count_penalty
        + settings.breakpoint_penalty
        + complexity
    )


def _fit_open_chain(
    points: np.ndarray, settings: PrismaticSettings
) -> tuple[float, tuple[Primitive, ...]] | None:
    count = len(points)
    best_cost = np.full(count, math.inf)
    best_count = np.full(count, np.iinfo(np.int32).max, dtype=np.int64)
    previous = np.full(count, -1, dtype=np.int64)
    chosen: list[Primitive | None] = [None] * count
    best_cost[0] = 0.0
    best_count[0] = 0
    cache: dict[tuple[int, int], tuple[Primitive, ...]] = {}
    for end in range(1, count):
        minimum = max(0, end - settings.maximum_interval_vertices + 1)
        for start in range(minimum, end):
            if not math.isfinite(float(best_cost[start])):
                continue
            key = (start, end)
            if key not in cache:
                interval = points[start : end + 1]
                candidates: list[Primitive] = []
                line = fit_line_primitive(interval, settings)
                if line is not None:
                    candidates.append(line)
                elif len(interval) >= 4:
                    arc = fit_arc_primitive(interval, settings)
                    if arc is not None:
                        candidates.append(arc)
                cache[key] = tuple(candidates)
            for primitive in cache[key]:
                cost = float(best_cost[start]) + _primitive_cost(primitive, settings)
                primitive_count = int(best_count[start]) + 1
                tie = (cost, primitive_count, primitive.kind, start)
                existing = chosen[end]
                current = (
                    float(best_cost[end]),
                    int(best_count[end]),
                    existing.kind if existing is not None else "z",
                    int(previous[end]),
                )
                if tie < current:
                    best_cost[end] = cost
                    best_count[end] = primitive_count
                    previous[end] = start
                    chosen[end] = primitive
    if not math.isfinite(float(best_cost[-1])):
        return None
    chain: list[Primitive] = []
    index = count - 1
    while index > 0:
        selected_primitive = chosen[index]
        if selected_primitive is None:
            return None
        chain.append(selected_primitive)
        index = int(previous[index])
    chain.reverse()
    return float(best_cost[-1]), tuple(chain)


def _continuity(chain: tuple[Primitive, ...]) -> tuple[Primitive, ...]:
    result: list[Primitive] = list(chain)
    for index in range(len(result)):
        following = result[(index + 1) % len(result)]
        current = result[index]
        exact_end = following.start
        dot = float(np.clip(np.dot(current.end_tangent(), following.start_tangent()), -1.0, 1.0))
        angle = math.degrees(math.acos(dot))
        result[index] = replace(current, end=exact_end, tangent_to_next_deg=angle)
    return tuple(result)


def fit_closed_line_arc_chain(
    loop: ProjectedLoop | np.ndarray,
    settings: PrismaticSettings | None = None,
) -> tuple[Primitive, ...]:
    """Globally segment a cyclic polygon using cached line/arc interval fits."""

    settings = settings or PrismaticSettings()
    settings.validate()
    points = loop.array if isinstance(loop, ProjectedLoop) else np.asarray(loop, dtype=np.float64)
    if len(points) < 3:
        raise PrismaticFitError(
            "no_valid_line_arc_decomposition", "profile has fewer than 3 points"
        )
    if len(points) > settings.maximum_profile_vertices:
        raise PrismaticFitError(
            "profile_vertex_limit",
            f"profile has {len(points)} vertices; limit is {settings.maximum_profile_vertices}",
        )
    ring = LinearRing(points)
    if not ring.is_simple:
        raise PrismaticFitError("self_intersecting_profile", "projected profile self-intersects")
    lexicographic = min(range(len(points)), key=lambda index: tuple(points[index]))
    edges_before = points - np.roll(points, 1, axis=0)
    edges_after = np.roll(points, -1, axis=0) - points
    before_norm = np.linalg.norm(edges_before, axis=1)
    after_norm = np.linalg.norm(edges_after, axis=1)
    cosine = np.sum(edges_before * edges_after, axis=1) / np.maximum(
        before_norm * after_norm, 1e-15
    )
    turning = np.arccos(np.clip(cosine, -1.0, 1.0))
    ranked = sorted(range(len(points)), key=lambda index: (-float(turning[index]), index))
    starts = sorted(dict.fromkeys([lexicographic, *ranked[: settings.candidate_start_count]]))
    options: list[tuple[float, int, tuple[str, ...], int, tuple[Primitive, ...]]] = []
    for start in starts:
        rotated = np.roll(points, -start, axis=0)
        unwrapped = np.vstack((rotated, rotated[0]))
        fitted = _fit_open_chain(unwrapped, settings)
        if fitted is None:
            continue
        cost, chain = fitted
        options.append((cost, len(chain), tuple(item.kind for item in chain), start, chain))
    if not options:
        raise PrismaticFitError(
            "no_valid_line_arc_decomposition",
            "no closed line/circular-arc segmentation satisfies configured residuals",
        )
    return _continuity(min(options, key=lambda option: option[:4])[-1])


def _classify_projected_loops(loops: list[ProjectedLoop]) -> tuple[ProjectedLoop, ...]:
    if not loops:
        raise PrismaticFitError("invalid_boundary_topology", "cap has no boundary loops")
    largest_index = max(range(len(loops)), key=lambda index: abs(loops[index].signed_area))
    exterior = loops[largest_index]
    polygon = Polygon(exterior.array)
    if not polygon.is_valid or polygon.area <= 0:
        raise PrismaticFitError("self_intersecting_profile", "cap exterior is not a valid polygon")
    classified: list[ProjectedLoop] = [replace(exterior, is_hole=False)]
    holes: list[ProjectedLoop] = []
    for index, loop in enumerate(loops):
        if index == largest_index:
            continue
        if not polygon.contains(Point(np.mean(loop.array, axis=0))):
            raise PrismaticFitError(
                "invalid_boundary_topology",
                "cap contains multiple disjoint exterior loops",
            )
        points, ids, area = _canonicalize_loop(loop.array, loop.vertex_ids, clockwise=True)
        holes.append(
            ProjectedLoop(
                ids,
                tuple((float(point[0]), float(point[1])) for point in points),
                loop.frame,
                area,
                True,
            )
        )
    holes.sort(key=lambda loop: (-abs(loop.signed_area), loop.points))
    return tuple([classified[0], *holes])


def _candidate_for_pair(
    mesh: trimesh.Trimesh,
    left: SurfacePatch,
    right: SurfacePatch,
    settings: PrismaticSettings,
) -> ExtrusionCandidate:
    diagnostics: list[PrismaticDiagnostic] = []
    left_normal = _unit(np.asarray(left.plane_normal))
    right_normal = _unit(np.asarray(right.plane_normal))
    dot = float(np.dot(left_normal, right_normal))
    if dot > -math.cos(math.radians(settings.cap_normal_angle_deg)):
        diagnostics.append(
            PrismaticDiagnostic(
                "no_opposing_planar_caps", "cap normals are not opposite", {"normalDot": dot}
            )
        )
    area_delta = abs(left.area_mm2 - right.area_mm2) / max(left.area_mm2, right.area_mm2)
    if area_delta > settings.cap_area_relative_tolerance:
        diagnostics.append(
            PrismaticDiagnostic(
                "cap_area_mismatch", "candidate cap areas differ", {"relativeAreaDelta": area_delta}
            )
        )
    initial_axis = _canonical_axis(left_normal)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    left_offset = float(np.mean(vertices[list(left.vertex_ids)] @ initial_axis))
    right_offset = float(np.mean(vertices[list(right.vertex_ids)] @ initial_axis))
    if left_offset > right_offset:
        left, right = right, left
        left_offset, right_offset = right_offset, left_offset
    distance = right_offset - left_offset
    if distance < settings.minimum_extrusion_length_mm:
        diagnostics.append(
            PrismaticDiagnostic(
                "degenerate_extrusion_length",
                "cap separation is too small",
                {"distanceMm": distance},
            )
        )
    cap_triangles = set(left.triangle_ids) | set(right.triangle_ids)
    side_ids = np.asarray(
        [index for index in range(len(mesh.faces)) if index not in cap_triangles], dtype=np.int64
    )
    if len(side_ids) < 2:
        diagnostics.append(
            PrismaticDiagnostic("side_normals_inconsistent", "candidate has no side-wall triangles")
        )
        return ExtrusionCandidate(
            False,
            tuple(initial_axis),
            distance,
            (left.id, right.id),
            (left_offset, right_offset),
            None,
            diagnostics=tuple(diagnostics),
        )
    side_normals = np.asarray(mesh.face_normals, dtype=np.float64)[side_ids]
    side_areas = np.asarray(mesh.area_faces, dtype=np.float64)[side_ids]
    refined, axis_rms = fit_extrusion_axis(side_normals, side_areas)
    if float(np.dot(refined, initial_axis)) < 0:
        refined = -refined
    axis = (
        _unit(refined + initial_axis)
        if float(np.dot(refined, initial_axis)) > 0.9
        else initial_axis
    )
    components = np.abs(side_normals @ axis)
    side_fraction = float(
        np.sum(side_areas[components <= settings.side_normal_max_component]) / np.sum(side_areas)
    )
    axis_rms = math.sqrt(float(np.sum(side_areas * components**2) / np.sum(side_areas)))
    if (
        axis_rms > settings.side_normal_rms_tolerance
        or side_fraction < settings.side_normal_required_fraction
    ):
        diagnostics.append(
            PrismaticDiagnostic(
                "side_normals_inconsistent",
                "side-wall normals are not perpendicular to the extrusion axis",
                {"rms": axis_rms, "acceptedAreaFraction": side_fraction},
            )
        )
    left_offset = float(np.mean(vertices[list(left.vertex_ids)] @ axis))
    right_offset = float(np.mean(vertices[list(right.vertex_ids)] @ axis))
    if left_offset > right_offset:
        left, right = right, left
        left_offset, right_offset = right_offset, left_offset
    distance = right_offset - left_offset
    minimum, maximum = float(np.min(vertices @ axis)), float(np.max(vertices @ axis))
    extent_error = max(abs(left_offset - minimum), abs(right_offset - maximum))
    if extent_error > settings.cap_plane_tolerance_mm:
        diagnostics.append(
            PrismaticDiagnostic(
                "cap_extent_mismatch",
                "candidate caps are not the mesh extrema",
                {"extentErrorMm": extent_error},
            )
        )
    if left.plane_origin is None:
        raise AssertionError("planar cap is missing its fitted origin")
    origin = np.asarray(left.plane_origin) - axis * (
        float(np.dot(left.plane_origin, axis)) - left_offset
    )
    frame = make_projection_frame(axis, origin)
    try:
        left_raw = extract_cap_boundary_loops(mesh, left.triangle_ids)
        right_raw = extract_cap_boundary_loops(mesh, right.triangle_ids)
        left_loops = _classify_projected_loops(
            [
                project_loop_to_plane(vertices[list(loop)], axis, vertex_ids=loop, frame=frame)
                for loop in left_raw
            ]
        )
        right_loops = _classify_projected_loops(
            [
                project_loop_to_plane(vertices[list(loop)], axis, vertex_ids=loop, frame=frame)
                for loop in right_raw
            ]
        )
        if len(left_loops) != len(right_loops):
            raise PrismaticFitError("cap_boundary_mismatch", "caps contain different loop counts")
        match_residual = 0.0
        for left_loop, right_loop in zip(left_loops, right_loops, strict=True):
            matched, residual, _, _ = match_projected_loops(
                left_loop, right_loop, settings.cap_loop_matching_tolerance_mm
            )
            match_residual = max(match_residual, residual)
            if not matched:
                raise PrismaticFitError(
                    "cap_boundary_mismatch", f"projected cap loops differ by {residual:g} mm RMS"
                )
    except PrismaticFitError as exc:
        diagnostics.append(PrismaticDiagnostic(exc.code, str(exc)))
        left_loops = ()
        match_residual = math.inf
    accepted = not diagnostics
    confidence = (
        max(
            0.0,
            1.0
            - area_delta / max(settings.cap_area_relative_tolerance, 1e-12) * 0.2
            - axis_rms / settings.side_normal_rms_tolerance * 0.4
            - (
                match_residual / settings.cap_loop_matching_tolerance_mm * 0.4
                if math.isfinite(match_residual)
                else 0.4
            ),
        )
        if accepted
        else 0.0
    )
    return ExtrusionCandidate(
        accepted,
        tuple(axis),
        distance,
        (left.id, right.id),
        (left_offset, right_offset),
        frame,
        tuple(left_loops),
        side_normal_rms=axis_rms,
        confidence=confidence,
        diagnostics=tuple(diagnostics),
    )


def detect_extrusion_candidate(
    mesh: trimesh.Trimesh,
    patches: tuple[SurfacePatch, ...] | list[SurfacePatch],
    settings: PrismaticSettings | None = None,
) -> ExtrusionCandidate:
    """Find the best validated antipodal cap pair for one linear extrusion."""

    settings = settings or PrismaticSettings()
    settings.validate()
    planes = [
        patch for patch in patches if patch.kind == "plane" and patch.plane_normal is not None
    ]
    pairs = [
        (left, right)
        for left, right in combinations(sorted(planes, key=lambda patch: patch.id), 2)
        if float(
            np.dot(_unit(np.asarray(left.plane_normal)), _unit(np.asarray(right.plane_normal)))
        )
        <= -math.cos(math.radians(settings.cap_normal_angle_deg))
    ]
    if not pairs:
        return ExtrusionCandidate(
            False,
            None,
            None,
            None,
            None,
            None,
            diagnostics=(
                PrismaticDiagnostic(
                    "no_opposing_planar_caps", "no significant opposing planar cap pair was found"
                ),
            ),
        )
    candidates = [_candidate_for_pair(mesh, left, right, settings) for left, right in pairs]
    candidates.sort(
        key=lambda candidate: (
            not candidate.accepted,
            -candidate.confidence,
            len(candidate.diagnostics),
            candidate.cap_patch_ids or ("", ""),
        )
    )
    return candidates[0]


def validate_prismatic_candidate(
    candidate: ExtrusionCandidate,
    settings: PrismaticSettings | None = None,
) -> ExtrusionCandidate:
    """Fit every cap loop and return a fully analytic candidate or a rejection."""

    settings = settings or PrismaticSettings()
    if not candidate.accepted:
        return candidate
    try:
        profiles = tuple(fit_closed_line_arc_chain(loop, settings) for loop in candidate.loops)
    except PrismaticFitError as exc:
        return replace(
            candidate,
            accepted=False,
            diagnostics=(*candidate.diagnostics, PrismaticDiagnostic(exc.code, str(exc))),
        )
    if any(not profile for profile in profiles):
        return replace(
            candidate,
            accepted=False,
            diagnostics=(
                *candidate.diagnostics,
                PrismaticDiagnostic("profile_not_closed", "one fitted profile is empty"),
            ),
        )
    return replace(candidate, profiles=profiles)


__all__ = [
    "ArcPrimitive",
    "ExtrusionCandidate",
    "LinePrimitive",
    "PrismaticDiagnostic",
    "PrismaticFitError",
    "PrismaticSettings",
    "ProfilePrimitive",
    "ProjectedLoop",
    "ProjectionFrame",
    "detect_extrusion_candidate",
    "extract_cap_boundary_loops",
    "fit_arc_primitive",
    "fit_closed_line_arc_chain",
    "fit_extrusion_axis",
    "fit_line_primitive",
    "make_projection_frame",
    "match_projected_loops",
    "project_loop_to_plane",
    "validate_prismatic_candidate",
]
