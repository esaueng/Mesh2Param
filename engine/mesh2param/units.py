"""Project-unit conversions used at geometry-engine boundaries."""

import math

MILLIMETERS_PER_UNIT: dict[str, float] = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1_000.0,
    "in": 25.4,
    "ft": 304.8,
}
DEFAULT_FACETED_SEWING_TOLERANCE_MM = 0.05
MAXIMUM_FACETED_SEWING_TOLERANCE_MM = 10.0


def millimeters_to_project_units(value_mm: float, units: str) -> float:
    try:
        scale = MILLIMETERS_PER_UNIT[units]
    except KeyError as exc:
        raise ValueError(f"unsupported project unit {units!r}") from exc
    return float(value_mm) / scale


def project_units_to_millimeters(value: float, units: str) -> float:
    try:
        scale = MILLIMETERS_PER_UNIT[units]
    except KeyError as exc:
        raise ValueError(f"unsupported project unit {units!r}") from exc
    return float(value) * scale


def validate_physical_tolerance(
    value: float,
    units: str,
    *,
    maximum_mm: float,
) -> float:
    tolerance = float(value)
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("tolerance must be finite and positive")
    physical_mm = project_units_to_millimeters(tolerance, units)
    if physical_mm > maximum_mm:
        maximum = millimeters_to_project_units(maximum_mm, units)
        raise ValueError(f"tolerance must not exceed {maximum:g} {units} ({maximum_mm:g} mm)")
    return tolerance


__all__ = [
    "DEFAULT_FACETED_SEWING_TOLERANCE_MM",
    "MAXIMUM_FACETED_SEWING_TOLERANCE_MM",
    "MILLIMETERS_PER_UNIT",
    "millimeters_to_project_units",
    "project_units_to_millimeters",
    "validate_physical_tolerance",
]
