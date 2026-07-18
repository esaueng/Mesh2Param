"""G3a fillet-band routing and loop-global radius evidence."""

from __future__ import annotations

from pathlib import Path

import pytest
import trimesh
from mesh2param.fillets import (
    FilletBandAssignment,
    FilletRoutingSettings,
    analyze_fillet_bands,
    evaluate_fillet_radius_group,
)
from mesh2param.sections import CircleRadiusFit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPOSITORY_ROOT / "samples" / "general-parametric-benchmark"


def _fixture_mesh(slug: str) -> trimesh.Trimesh:
    mesh = trimesh.load_mesh(FIXTURE_ROOT / slug / "source.stl", process=True)
    assert isinstance(mesh, trimesh.Trimesh)
    return mesh


@pytest.mark.geometry
@pytest.mark.samples
def test_filleted_spanner_routes_both_outer_bands_into_one_radius_group() -> None:
    mesh = _fixture_mesh("spanner-filleted")

    first = analyze_fillet_bands(mesh)
    repeated = analyze_fillet_bands(mesh)

    assert first.to_dict() == repeated.to_dict()
    assert not first.diagnostics
    assert len(first.assignments) == 2
    assert {(item.cap_side, item.loop_index) for item in first.assignments} == {
        ("lower", 0),
        ("upper", 0),
    }
    assert len(first.groups) == 1
    group = first.groups[0]
    assert group.id == "fillet-group.outer"
    assert group.radius_mm == pytest.approx(1.5, abs=0.02)
    assert group.maximum_cap_radius_delta_mm < 0.001
    assert group.loop_fit_rms_residual_mm < 0.001
    assert group.loop_fit_maximum_residual_mm < 0.002
    assert group.stable_along_loop
    assert {item.cap_side for item in group.assignments} == {"lower", "upper"}
    assert len(group.source_triangle_ids) == sum(
        len(assignment.triangle_ids) for assignment in group.assignments
    )


@pytest.mark.geometry
@pytest.mark.samples
def test_sharp_spanner_reports_no_fillet_group() -> None:
    analysis = analyze_fillet_bands(_fixture_mesh("spanner-sharp"))

    assert analysis.assignments == ()
    assert analysis.groups == ()
    assert analysis.diagnostics == ()
    assert not analysis.section_radius_fit.accepted


def test_inconsistent_cap_radii_reject_as_variable_fillet_radius() -> None:
    assignments = (
        FilletBandAssignment("band.lower", "lower", 0, 0.1, 1.5, (1, 2)),
        FilletBandAssignment("band.upper", "upper", 0, 0.1, 1.55, (3, 4)),
    )
    global_fit = CircleRadiusFit(True, 1.525, 0.005, 0.01, 0.5)
    lower_fit = CircleRadiusFit(True, 1.5, 0.002, 0.005, 0.5)
    upper_fit = CircleRadiusFit(True, 1.55, 0.002, 0.005, 0.5)

    group, diagnostic = evaluate_fillet_radius_group(
        assignments,
        global_fit,
        lower_fit,
        upper_fit,
        FilletRoutingSettings(),
    )

    assert group is None
    assert diagnostic is not None
    assert diagnostic.code == "variable-fillet-radius"
    assert diagnostic.measured["lowerRadiusMm"] == 1.5
    assert diagnostic.measured["upperRadiusMm"] == 1.55
    assert diagnostic.measured["radiusDeltaMm"] == pytest.approx(0.05)
    assert diagnostic.source_triangle_ids == (1, 2, 3, 4)
