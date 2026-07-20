from __future__ import annotations

import math

import pytest
from mesh2param.units import (
    MILLIMETERS_PER_UNIT,
    millimeters_to_project_units,
    project_units_to_millimeters,
    validate_physical_tolerance,
)


@pytest.mark.parametrize(("units", "scale"), sorted(MILLIMETERS_PER_UNIT.items()))
def test_all_project_units_round_trip_without_changing_scale(units: str, scale: float) -> None:
    project_value = millimeters_to_project_units(1234.5, units)

    assert project_value == pytest.approx(1234.5 / scale)
    assert project_units_to_millimeters(project_value, units) == pytest.approx(1234.5)


@pytest.mark.parametrize("units", ["MM", "inch", "yards", ""])
def test_unit_conversion_rejects_unsupported_or_implicitly_normalized_units(units: str) -> None:
    with pytest.raises(ValueError, match="unsupported project unit"):
        millimeters_to_project_units(1.0, units)
    with pytest.raises(ValueError, match="unsupported project unit"):
        project_units_to_millimeters(1.0, units)


@pytest.mark.parametrize("value", [0.0, -0.1, math.nan, math.inf, -math.inf])
def test_physical_tolerance_must_be_finite_and_positive(value: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        validate_physical_tolerance(value, "mm", maximum_mm=10.0)


def test_physical_tolerance_limit_is_compared_in_millimeters() -> None:
    assert validate_physical_tolerance(0.25, "in", maximum_mm=6.35) == 0.25

    with pytest.raises(ValueError, match=r"0\.25 in \(6\.35 mm\)"):
        validate_physical_tolerance(0.25001, "in", maximum_mm=6.35)
