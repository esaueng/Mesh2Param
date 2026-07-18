"""G2a evaluator hardening and calibrated general-parametric baseline."""

from __future__ import annotations

import sys
from pathlib import Path

import cadquery as cq
import numpy as np
import pytest
import trimesh
from mesh2param.comparison import ComparisonSettings, compare_meshes
from mesh2param.general_fixtures import (
    GENERAL_FIXTURES_BY_SLUG,
    build_general_fixture_shape,
)
from mesh2param.reconstruction import (
    PrismaticReconstructionResult,
    reconstruct_file,
)
from mesh2param.validation import (
    ParametricSurfacePolicy,
    audit_parametric_surfaces,
    classify_face_surfaces,
    classify_parametric_face_surfaces,
    export_step_validated,
    import_step_shape,
)
from mesh2param_contracts.models import ExtrusionFeature

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_GENERAL_FIXTURES = _REPOSITORY_ROOT / "samples" / "general-parametric-benchmark"
_SCRIPTS_DIR = str(_REPOSITORY_ROOT / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from run_general_baseline import _fixture_baseline  # type: ignore[import-not-found]  # noqa: E402


def _parallel_triangle_mesh(z: float) -> trimesh.Trimesh:
    return trimesh.Trimesh(
        vertices=np.asarray(((0.0, 0.0, z), (2.0, 0.0, z), (0.0, 2.0, z))),
        faces=np.asarray(((0, 1, 2),)),
        process=False,
        validate=False,
    )


def test_p99_comparison_is_deterministic_and_serialized() -> None:
    settings = ComparisonSettings(sample_count_each_direction=64, deterministic_seed=173)
    first = compare_meshes(_parallel_triangle_mesh(0.0), _parallel_triangle_mesh(1.0), settings)
    second = compare_meshes(_parallel_triangle_mesh(0.0), _parallel_triangle_mesh(1.0), settings)

    assert first == second
    assert first.p99_distance_mm == pytest.approx(1.0, abs=1e-12)
    assert first.to_dict()["distanceMm"]["p99"] == first.p99_distance_mm


@pytest.mark.geometry
def test_analytic_step_keeps_one_part_per_million_volume_tolerance(tmp_path: Path) -> None:
    shape = cq.Workplane("XY").box(40.0, 30.0, 12.0)
    report = export_step_validated(shape, tmp_path / "analytic-box.step")

    assert report.volume_tolerance == pytest.approx(report.source.volume * 1e-6)


@pytest.mark.geometry
def test_sharp_spanner_surface_audit_survives_step_reimport(tmp_path: Path) -> None:
    shape = build_general_fixture_shape(GENERAL_FIXTURES_BY_SLUG["spanner-sharp"])
    policy = ParametricSurfacePolicy(
        allowed_surface_types=("plane", "cylinder", "surfaceOfExtrusion"),
        source_triangle_count=508,
    )

    report = export_step_validated(
        shape,
        tmp_path / "sharp.step",
        parametric_surface_policy=policy,
    )

    assert report.valid
    assert report.parametric_surface_audit is not None
    assert report.parametric_surface_audit.valid
    assert report.parametric_surface_audit.surface_counts["plane"] == 10
    assert report.parametric_surface_audit.surface_counts["cylinder"] == 1
    assert report.parametric_surface_audit.surface_counts["surfaceOfExtrusion"] == 1
    assert report.to_dict()["parametricSurfaceAudit"]["valid"] is True
    assert report.volume_tolerance == pytest.approx(report.source.volume * 5e-6)


@pytest.mark.geometry
def test_fillet_surfaces_require_explicit_candidate_declaration(tmp_path: Path) -> None:
    shape = build_general_fixture_shape(GENERAL_FIXTURES_BY_SLUG["spanner-filleted"])
    counts = classify_parametric_face_surfaces(shape)
    assert counts["torus"] == 2
    assert counts["bspline"] == 2
    assert counts["surfaceOfExtrusion"] == 1

    without_fillets = ParametricSurfacePolicy(
        allowed_surface_types=("plane", "cylinder", "surfaceOfExtrusion"),
        source_triangle_count=5858,
    )
    audit = audit_parametric_surfaces(shape, without_fillets)
    assert not audit.valid
    assert [issue.code for issue in audit.issues] == [
        "unsupported-surface-type",
        "unsupported-surface-type",
    ]
    assert {issue.measured["surfaceType"] for issue in audit.issues} == {"bspline", "torus"}

    with_fillets = ParametricSurfacePolicy(
        allowed_surface_types=(
            "plane",
            "cylinder",
            "surfaceOfExtrusion",
            "torus",
            "bspline",
        ),
        source_triangle_count=5858,
    )
    report = export_step_validated(
        shape,
        tmp_path / "filleted.step",
        parametric_surface_policy=with_fillets,
    )
    assert report.valid
    assert report.parametric_surface_audit is not None
    assert report.parametric_surface_audit.valid


@pytest.mark.geometry
def test_triangle_per_face_parametric_claim_is_rejected(tmp_path: Path) -> None:
    shape = cq.Workplane("XY").box(4.0, 3.0, 2.0)
    policy = ParametricSurfacePolicy(
        allowed_surface_types=("plane",),
        source_triangle_count=6,
    )

    with pytest.raises(ValueError, match="triangle-per-face-parametric-output"):
        export_step_validated(
            shape,
            tmp_path / "faceted-claim.step",
            parametric_surface_policy=policy,
        )
    assert not (tmp_path / "faceted-claim.step").exists()


@pytest.mark.geometry
@pytest.mark.geometry
def test_sharp_spanner_reconstructs_as_spline_extrusion_and_polygon_cut(
    tmp_path: Path,
) -> None:
    first_output = tmp_path / "first"
    second_output = tmp_path / "second"
    first = reconstruct_file(
        _GENERAL_FIXTURES / "spanner-sharp" / "source.stl",
        first_output,
        units="mm",
    )
    second = reconstruct_file(
        _GENERAL_FIXTURES / "spanner-sharp" / "source.stl",
        second_output,
        units="mm",
    )
    assert isinstance(first, PrismaticReconstructionResult)
    assert isinstance(second, PrismaticReconstructionResult)
    assert first.selected.label == "analytic-prismatic-spline"
    assert [feature.operation for feature in first.graph.features] == ["extrusion", "extrusion"]
    base_feature, cut_feature = first.graph.features
    assert isinstance(base_feature, ExtrusionFeature)
    assert isinstance(cut_feature, ExtrusionFeature)
    assert [base_feature.boolean_mode, cut_feature.boolean_mode] == ["base", "subtractive"]
    assert cut_feature.extent == "throughAll"

    outer_kinds = [entity.kind for entity in first.graph.sketches[0].entities]
    assert outer_kinds.count("line") == 2
    assert outer_kinds.count("circularArc") == 1
    assert outer_kinds.count("bspline") == 1
    cut_kinds = [entity.kind for entity in first.graph.sketches[1].entities]
    assert cut_kinds.count("line") == 6
    assert first.prismatic.distance_mm == 8.0
    assert first.prismatic.distance_measurement is not None
    assert first.prismatic.distance_measurement.accepted
    polygon = next(item for item in first.prismatic.polygon_hypotheses if item is not None)
    assert polygon.side_count == 6
    assert polygon.selected_circumdiameter_mm == 12.0
    spline = next(item for item in first.prismatic.profiles[0] if item.kind == "bspline")
    assert spline.rms_residual_mm < 0.03
    assert spline.maximum_residual_mm < 0.075

    comparison = first.comparison
    tolerance = first.graph.project_tolerance.surface_deviation
    assert comparison.p95_distance_mm <= 1.5 * tolerance
    assert comparison.p99_distance_mm <= 3.0 * tolerance
    assert comparison.maximum_distance_mm <= 6.0 * tolerance
    assert comparison.p95_normal_angle_deg <= 3.0
    assert comparison.relative_volume_delta is not None
    assert comparison.relative_volume_delta <= 0.001
    assert first.step.valid
    assert first.step.source.face_count == 12
    assert len(first.source.mesh.faces) == 508
    ground_truth = build_general_fixture_shape(GENERAL_FIXTURES_BY_SLUG["spanner-sharp"])
    assert abs(first.step.source.volume - ground_truth.Volume()) / ground_truth.Volume() <= 0.001
    surfaces = classify_face_surfaces(import_step_shape(first.step.path))
    assert surfaces["plane"] == 10
    assert surfaces["cylinder"] == 1
    assert surfaces["other"] == 1
    assert sum(surfaces.values()) == 12

    for name in ("model.cadgraph.json", "model.cq.py", "model.step", "candidates.json"):
        assert (first_output / name).read_bytes() == (second_output / name).read_bytes(), name


@pytest.mark.geometry
def test_sharp_general_faceted_baseline_records_exact_inventory() -> None:
    first = _fixture_baseline(_GENERAL_FIXTURES / "spanner-sharp", sample_count=64)
    second = _fixture_baseline(_GENERAL_FIXTURES / "spanner-sharp", sample_count=64)
    first_without_runtime = {key: value for key, value in first.items() if key != "runtimeSeconds"}
    second_without_runtime = {
        key: value for key, value in second.items() if key != "runtimeSeconds"
    }

    assert first_without_runtime == second_without_runtime
    assert first["status"] == "converted"
    assert first["sourceTriangleCount"] == 508
    assert first["facetedFaceCount"] == 508
    assert first["facesPerSourceTriangle"] == 1.0
    assert first["stepByteSize"] > first["sourceStlByteSize"]
    assert len(first["stepSha256"]) == 64
    assert first["comparison"]["distanceMm"]["p99"] < 1e-4
