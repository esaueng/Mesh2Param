"""G4a explicit shallow-detail suppression and functional validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
import trimesh
from mesh2param.details import (
    DetailSuppressionSettings,
    analyze_shallow_cap_details,
    build_functional_reference_mesh,
)
from mesh2param.reconstruction import (
    PrismaticReconstructionResult,
    ReconstructionSettings,
    reconstruct_file,
)
from mesh2param.sections import extract_section_stack
from mesh2param_contracts.models import ExtrusionFeature

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPOSITORY_ROOT / "samples" / "general-parametric-benchmark"


def _mesh(slug: str) -> trimesh.Trimesh:
    mesh = trimesh.load_mesh(FIXTURE_ROOT / slug / "source.stl", process=True)
    assert isinstance(mesh, trimesh.Trimesh)
    return mesh


def test_detail_fraction_limit_rejects_instead_of_silently_masking() -> None:
    source = _mesh("spanner-filleted-embossed")
    analysis = analyze_shallow_cap_details(
        source,
        extract_section_stack(source),
        DetailSuppressionSettings(maximum_volume_fraction=0.001),
    )

    assert analysis.regions == ()
    assert [diagnostic.code for diagnostic in analysis.diagnostics] == ["detail-volume-limit"]
    diagnostic = analysis.diagnostics[0]
    assert diagnostic.measured["volumeFraction"] == pytest.approx(0.00364, abs=1e-5)
    assert len(diagnostic.source_triangle_ids) == 10


@pytest.mark.geometry
@pytest.mark.samples
def test_embossed_spanner_declares_only_boss_and_passes_masked_gates(
    tmp_path: Path,
) -> None:
    source = _mesh("spanner-filleted-embossed")
    stack = extract_section_stack(source)
    first_analysis = analyze_shallow_cap_details(source, stack)
    second_analysis = analyze_shallow_cap_details(source.copy(), stack)
    assert first_analysis.to_dict() == second_analysis.to_dict()
    assert not first_analysis.diagnostics
    assert len(first_analysis.regions) == 1

    region = first_analysis.regions[0]
    assert region.kind == "embossedCapDetail"
    assert region.cap_side == "upper"
    assert region.depth_mm == pytest.approx(0.4, abs=1e-3)
    assert region.footprint_area_mm2 == pytest.approx(18.0 * 6.0, abs=1e-6)
    assert region.measured_volume_mm3 == pytest.approx(43.2, abs=0.01)
    assert len(region.boundary_points_mm) == 4
    assert len(region.source_triangle_ids) == 10
    assert region.footprint_area_fraction < 0.1
    assert region.volume_fraction < 0.004

    functional_reference = build_functional_reference_mesh(source, first_analysis)
    unembossed = _mesh("spanner-filleted")
    assert functional_reference.is_watertight
    assert functional_reference.is_winding_consistent
    assert functional_reference.volume == pytest.approx(unembossed.volume, abs=1e-9)
    np.testing.assert_allclose(functional_reference.bounds, unembossed.bounds, atol=1e-9)

    output = tmp_path / "functional"
    result = reconstruct_file(
        FIXTURE_ROOT / "spanner-filleted-embossed" / "source.stl",
        output,
        units="mm",
    )
    assert isinstance(result, PrismaticReconstructionResult)
    assert result.to_dict()["detailMode"] == "functional"
    assert result.suppression is not None
    assert result.functional_comparison is not None
    assert result.graph.validation.status == "valid"
    assert result.step.valid
    assert result.step.source.face_count == 20

    tolerance = result.graph.project_tolerance.surface_deviation
    masked = result.functional_comparison.masked
    unmasked_report = result.functional_comparison.unmasked
    assert result.comparison is masked
    assert masked.p95_distance_mm <= 1.5 * tolerance
    assert masked.p99_distance_mm <= 3.0 * tolerance
    assert masked.maximum_distance_mm <= 6.0 * tolerance
    assert masked.p95_normal_angle_deg <= 3.0
    assert masked.relative_volume_delta is not None
    assert masked.relative_volume_delta <= 0.001
    assert unmasked_report.maximum_distance_mm > 0.39
    assert unmasked_report.relative_volume_delta is not None
    assert unmasked_report.relative_volume_delta > 0.003

    comparison_artifact = json.loads((output / "comparison.json").read_text())
    assert comparison_artifact["validationMode"] == "functional"
    assert comparison_artifact["suppressedTriangleCount"] == 10
    assert comparison_artifact["masked"] == masked.to_dict()
    assert comparison_artifact["unmasked"] == unmasked_report.to_dict()
    suppression_artifact = json.loads((output / "suppressed-regions.json").read_text())
    assert suppression_artifact == result.suppression.to_dict()
    assert suppression_artifact["measuredVolumeMm3"] == pytest.approx(43.2, abs=0.01)
    assert suppression_artifact["suppressedTriangleCount"] == 10
    assert result.artifacts["suppressedRegions"] == str(output / "suppressed-regions.json")

    extension = cast(
        dict[str, Any],
        (result.graph.extensions or {})["mesh2param.dev/prismaticReconstruction"],
    )
    assert extension["validationMode"] == "functional"
    assert len(extension["suppressedRegions"]) == 1
    selected_snapshot = cast(
        dict[str, Any],
        (result.selected.graph.extensions or {})["mesh2param.dev/prismaticReconstruction"],
    )
    assert selected_snapshot["suppressedRegions"] == extension["suppressedRegions"]


@pytest.mark.geometry
@pytest.mark.samples
def test_embossed_spanner_full_mode_recovers_additive_boss(tmp_path: Path) -> None:
    output = tmp_path / "full"
    result = reconstruct_file(
        FIXTURE_ROOT / "spanner-filleted-embossed" / "source.stl",
        output,
        units="mm",
        settings=ReconstructionSettings(detail_mode="full"),
    )

    assert isinstance(result, PrismaticReconstructionResult)
    assert result.suppression is None
    assert result.functional_comparison is None
    assert result.recovered_details is not None
    assert result.recovered_details.mode == "full"
    assert result.graph.validation.status == "valid"
    assert result.step.valid
    assert result.step.source.face_count == 25
    assert [feature.operation for feature in result.graph.features] == [
        "extrusion",
        "fillet",
        "extrusion",
        "extrusion",
    ]
    boss = result.graph.features[-1]
    assert isinstance(boss, ExtrusionFeature)
    assert boss.id == "feature.detail.1"
    assert boss.boolean_mode == "additive"
    assert boss.distance == pytest.approx(0.4, abs=1e-3)
    region = result.recovered_details.regions[0]
    assert region.footprint_area_mm2 == pytest.approx(18.0 * 6.0, abs=1e-6)
    assert region.measured_volume_mm3 == pytest.approx(43.2, abs=0.01)

    tolerance = result.graph.project_tolerance.surface_deviation
    assert result.comparison.p95_distance_mm <= 1.5 * tolerance
    assert result.comparison.p99_distance_mm <= 3.0 * tolerance
    assert result.comparison.maximum_distance_mm <= 6.0 * tolerance
    assert result.comparison.p95_normal_angle_deg <= 3.0
    assert result.comparison.relative_volume_delta is not None
    assert result.comparison.relative_volume_delta <= 0.001
    assert result.artifacts["detailRegions"] == str(output / "detail-regions.json")
    assert "suppressedRegions" not in result.artifacts

    reconstruction = json.loads((output / "reconstruction.json").read_text())
    assert reconstruction["detailMode"] == "full"
    assert reconstruction["suppressedRegions"] == []
    assert reconstruction["recoveredDetails"] == [region.to_dict()]
    assert json.loads((output / "detail-regions.json").read_text())["mode"] == "full"
    extension = cast(
        dict[str, Any],
        (result.graph.extensions or {})["mesh2param.dev/prismaticReconstruction"],
    )
    assert extension["detailRecovery"]["mode"] == "full"
    assert extension["detailRecovery"]["regions"] == [region.to_dict()]
