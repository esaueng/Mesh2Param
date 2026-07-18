"""Bounded spline and regular-polygon hypotheses for prismatic profiles.

The fitters in this module operate only on ordered 2-D mesh evidence.  They use
the same open-uniform, clamped B-spline convention as the CADGraph compiler and
record the residual, complexity penalty, and uncertainty used to select a fit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from scipy.interpolate import BSpline
from scipy.optimize import minimize_scalar


@dataclass(frozen=True, slots=True)
class FitUncertainty:
    rms_residual_mm: float
    maximum_residual_mm: float
    sample_count: int
    parameter_iterations: int
    design_condition_number: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "rmsResidualMm": self.rms_residual_mm,
            "maximumResidualMm": self.maximum_residual_mm,
            "sampleCount": self.sample_count,
            "parameterIterations": self.parameter_iterations,
            "designConditionNumber": self.design_condition_number,
        }


@dataclass(frozen=True, slots=True)
class FitPenalties:
    residual: float
    complexity: float
    endpoint: float
    total: float

    def to_dict(self) -> dict[str, float]:
        return {
            "residual": self.residual,
            "complexity": self.complexity,
            "endpoint": self.endpoint,
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class BSplineSegment:
    start: tuple[float, float]
    end: tuple[float, float]
    rms_residual_mm: float
    maximum_residual_mm: float
    length_mm: float
    degree: int
    control_points: tuple[tuple[float, float], ...]
    penalties: FitPenalties
    uncertainty: FitUncertainty
    tangent_to_next_deg: float | None = None

    @property
    def kind(self) -> Literal["bspline"]:
        return "bspline"

    def start_tangent(self) -> np.ndarray:
        vector = np.asarray(self.control_points[1]) - np.asarray(self.control_points[0])
        return np.asarray(vector / np.linalg.norm(vector), dtype=np.float64)

    def end_tangent(self) -> np.ndarray:
        vector = np.asarray(self.control_points[-1]) - np.asarray(self.control_points[-2])
        return np.asarray(vector / np.linalg.norm(vector), dtype=np.float64)


@dataclass(frozen=True, slots=True)
class NominalMeasurement:
    measured_mm: float
    suggested_nominal_mm: float | None
    delta_mm: float | None
    accepted: bool

    @property
    def selected_mm(self) -> float:
        return (
            float(self.suggested_nominal_mm)
            if self.accepted and self.suggested_nominal_mm is not None
            else float(self.measured_mm)
        )

    def to_dict(self) -> dict[str, float | bool | None]:
        return {
            "measuredMm": self.measured_mm,
            "suggestedNominalMm": self.suggested_nominal_mm,
            "deltaMm": self.delta_mm,
            "accepted": self.accepted,
        }


@dataclass(frozen=True, slots=True)
class NominalSnappingPolicy:
    enabled: bool = True
    grid_mm: float = 0.5
    tolerance_mm: float = 0.05

    def snap(self, value_mm: float) -> NominalMeasurement:
        if self.grid_mm <= 0 or self.tolerance_mm < 0:
            raise ValueError("nominal snap grid must be positive and tolerance non-negative")
        if not math.isfinite(value_mm) or value_mm <= 0:
            raise ValueError("nominal measurements must be finite and positive")
        nominal = round(value_mm / self.grid_mm) * self.grid_mm
        delta = float(nominal - value_mm)
        accepted = self.enabled and abs(delta) <= self.tolerance_mm
        return NominalMeasurement(
            float(value_mm),
            float(nominal) if abs(delta) <= self.tolerance_mm else None,
            delta if abs(delta) <= self.tolerance_mm else None,
            accepted,
        )


@dataclass(frozen=True, slots=True)
class RegularPolygonHypothesis:
    side_count: int
    center: tuple[float, float]
    measured_circumdiameter_mm: float
    selected_circumdiameter_mm: float
    phase_angle_rad: float
    clockwise: bool
    maximum_radial_residual_mm: float
    maximum_angular_residual_deg: float
    nominal: NominalMeasurement
    source_points: tuple[tuple[float, float], ...]

    @property
    def points(self) -> tuple[tuple[float, float], ...]:
        direction = -1.0 if self.clockwise else 1.0
        radius = self.selected_circumdiameter_mm * 0.5
        return tuple(
            (
                self.center[0] + radius * math.cos(
                    self.phase_angle_rad + direction * 2.0 * math.pi * index / self.side_count
                ),
                self.center[1] + radius * math.sin(
                    self.phase_angle_rad + direction * 2.0 * math.pi * index / self.side_count
                ),
            )
            for index in range(self.side_count)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sideCount": self.side_count,
            "centerMm": list(self.center),
            "measuredCircumdiameterMm": self.measured_circumdiameter_mm,
            "selectedCircumdiameterMm": self.selected_circumdiameter_mm,
            "phaseAngleRad": self.phase_angle_rad,
            "clockwise": self.clockwise,
            "maximumRadialResidualMm": self.maximum_radial_residual_mm,
            "maximumAngularResidualDeg": self.maximum_angular_residual_deg,
            "nominal": self.nominal.to_dict(),
            "sourcePointsMm": [list(point) for point in self.source_points],
        }


def _open_uniform_knots(control_point_count: int, degree: int) -> np.ndarray:
    interior_count = control_point_count - degree - 1
    return np.asarray(
        [0.0] * (degree + 1)
        + [(index + 1) / (interior_count + 1) for index in range(interior_count)]
        + [1.0] * (degree + 1),
        dtype=np.float64,
    )


def _fit_control_points(
    points: np.ndarray,
    parameters: np.ndarray,
    control_point_count: int,
    degree: int,
) -> tuple[np.ndarray, float]:
    basis = BSpline.design_matrix(
        parameters, _open_uniform_knots(control_point_count, degree), degree
    ).toarray()
    controls = np.zeros((control_point_count, 2), dtype=np.float64)
    controls[0] = points[0]
    controls[-1] = points[-1]
    rhs = points - basis[:, [0]] * controls[0] - basis[:, [-1]] * controls[-1]
    interior = basis[:, 1:-1]
    controls[1:-1] = np.linalg.lstsq(interior, rhs, rcond=None)[0]
    return controls, float(np.linalg.cond(interior))


def _fit_one_bspline(
    points: np.ndarray,
    control_point_count: int,
    *,
    degree: int,
    maximum_iterations: int,
) -> BSplineSegment:
    chord_lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cumulative = np.concatenate(([0.0], np.cumsum(chord_lengths)))
    parameters = cumulative / cumulative[-1]
    condition = math.inf
    completed_iterations = 0
    previous_rms = math.inf
    for iteration in range(maximum_iterations):
        controls, condition = _fit_control_points(
            points, parameters, control_point_count, degree
        )
        curve = BSpline(_open_uniform_knots(control_point_count, degree), controls, degree)
        old_parameters = parameters.copy()
        for index in range(1, len(points) - 1):
            lower = old_parameters[index - 1] + 1e-12
            upper = old_parameters[index + 1] - 1e-12
            solution = minimize_scalar(
                lambda value, point=points[index], fitted_curve=curve: float(
                    np.sum((fitted_curve(value) - point) ** 2)
                ),
                bounds=(lower, upper),
                method="bounded",
                options={"xatol": 1e-13, "maxiter": 80},
            )
            parameters[index] = float(solution.x)
        residuals = np.linalg.norm(curve(parameters) - points, axis=1)
        rms = math.sqrt(float(np.mean(residuals**2)))
        completed_iterations = iteration + 1
        if iteration >= 20 and abs(previous_rms - rms) <= 1e-10:
            break
        previous_rms = rms
    controls, condition = _fit_control_points(points, parameters, control_point_count, degree)
    curve = BSpline(_open_uniform_knots(control_point_count, degree), controls, degree)
    residuals = np.linalg.norm(curve(parameters) - points, axis=1)
    rms = math.sqrt(float(np.mean(residuals**2)))
    maximum = float(np.max(residuals))
    dense = curve(np.linspace(0.0, 1.0, 1025))
    length = float(np.sum(np.linalg.norm(np.diff(dense, axis=0), axis=1)))
    residual_penalty = rms + 0.25 * maximum
    complexity_penalty = 0.0025 * (control_point_count - 4)
    endpoint_error = max(
        float(np.linalg.norm(curve(0.0) - points[0])),
        float(np.linalg.norm(curve(1.0) - points[-1])),
    )
    penalties = FitPenalties(
        residual_penalty,
        complexity_penalty,
        endpoint_error,
        residual_penalty + complexity_penalty + endpoint_error,
    )
    uncertainty = FitUncertainty(
        rms,
        maximum,
        len(points),
        completed_iterations,
        condition,
    )
    return BSplineSegment(
        (float(points[0, 0]), float(points[0, 1])),
        (float(points[-1, 0]), float(points[-1, 1])),
        rms,
        maximum,
        length,
        degree,
        tuple((float(point[0]), float(point[1])) for point in controls),
        penalties,
        uncertainty,
    )


def fit_bounded_bspline(
    points: np.ndarray,
    *,
    degree: int = 3,
    minimum_control_points: int = 4,
    maximum_control_points: int = 8,
    rms_tolerance_mm: float = 0.03,
    maximum_tolerance_mm: float = 0.075,
    maximum_iterations: int = 100,
) -> BSplineSegment:
    """Fit a deterministic contract-bounded open-uniform B-spline segment."""

    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 4:
        raise ValueError("B-spline evidence must contain at least four 2-D points")
    if not np.all(np.isfinite(points)):
        raise ValueError("B-spline evidence contains non-finite coordinates")
    if not 1 <= degree <= 3 or minimum_control_points < degree + 1:
        raise ValueError("B-spline degree and control-point bounds are invalid")
    if maximum_control_points > 8 or minimum_control_points > maximum_control_points:
        raise ValueError("B-spline control-point count must remain within 4..8")
    if np.any(np.linalg.norm(np.diff(points, axis=0), axis=1) <= 1e-12):
        raise ValueError("B-spline evidence contains coincident consecutive points")
    fits = [
        _fit_one_bspline(
            points,
            count,
            degree=degree,
            maximum_iterations=maximum_iterations,
        )
        for count in range(minimum_control_points, maximum_control_points + 1)
    ]
    accepted = [
        fit
        for fit in fits
        if fit.rms_residual_mm <= rms_tolerance_mm
        and fit.maximum_residual_mm <= maximum_tolerance_mm
    ]
    if not accepted:
        best = min(fits, key=lambda fit: fit.penalties.total)
        raise ValueError(
            "bounded B-spline fit exceeds residual limits: "
            f"rms={best.rms_residual_mm:g} mm, max={best.maximum_residual_mm:g} mm"
        )
    return min(
        accepted,
        key=lambda fit: (fit.penalties.total, len(fit.control_points), fit.control_points),
    )


def fit_regular_polygon(
    points: np.ndarray,
    *,
    snapping: NominalSnappingPolicy | None = None,
    minimum_sides: int = 3,
    maximum_sides: int = 12,
    radial_tolerance_mm: float = 0.05,
    angular_tolerance_deg: float = 1.0,
) -> RegularPolygonHypothesis:
    """Recognize one ordered regular polygon and apply the explicit snap policy."""

    points = np.asarray(points, dtype=np.float64)
    count = len(points)
    if points.ndim != 2 or points.shape[1] != 2 or not minimum_sides <= count <= maximum_sides:
        raise ValueError("regular-polygon evidence has an unsupported vertex count")
    center = np.mean(points, axis=0)
    radial = points - center
    radii = np.linalg.norm(radial, axis=1)
    measured_radius = float(np.mean(radii))
    maximum_radial = float(np.max(np.abs(radii - measured_radius)))
    signed_area = 0.5 * float(
        np.sum(points[:, 0] * np.roll(points[:, 1], -1) - points[:, 1] * np.roll(points[:, 0], -1))
    )
    clockwise = signed_area < 0
    direction = -1.0 if clockwise else 1.0
    angles = np.unwrap(np.arctan2(radial[:, 1], radial[:, 0]))
    expected = angles[0] + direction * 2.0 * math.pi * np.arange(count) / count
    angular_error = np.angle(np.exp(1j * (angles - expected)))
    maximum_angular = math.degrees(float(np.max(np.abs(angular_error))))
    if maximum_radial > radial_tolerance_mm or maximum_angular > angular_tolerance_deg:
        raise ValueError(
            "loop is not a regular polygon: "
            f"radial={maximum_radial:g} mm, angular={maximum_angular:g} deg"
        )
    nominal = (snapping or NominalSnappingPolicy()).snap(2.0 * measured_radius)
    return RegularPolygonHypothesis(
        count,
        (float(center[0]), float(center[1])),
        2.0 * measured_radius,
        nominal.selected_mm,
        float(angles[0]),
        clockwise,
        maximum_radial,
        maximum_angular,
        nominal,
        tuple((float(point[0]), float(point[1])) for point in points),
    )


__all__ = [
    "BSplineSegment",
    "FitPenalties",
    "FitUncertainty",
    "NominalMeasurement",
    "NominalSnappingPolicy",
    "RegularPolygonHypothesis",
    "fit_bounded_bspline",
    "fit_regular_polygon",
]
