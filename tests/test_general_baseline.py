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
from mesh2param.reconstruction import ReconstructionError, reconstruct_file
from mesh2param.validation import (
    ParametricSurfacePolicy,
    audit_parametric_surfaces,
    classify_parametric_face_surfaces,
    export_step_validated,
)

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
@pytest.mark.parametrize(
    ("slug", "expected_code", "expected_message"),
    (
        (
            "spanner-sharp",
            "unsupported-freeform-remainder",
            "automatic L-bracket inference requires only plane and full-cylinder patches",
        ),
        (
            "spanner-filleted",
            "fillet-band-detected",
            "section inset series fits a constant-radius circle model",
        ),
        (
            "spanner-filleted-embossed",
            "fillet-band-detected",
            "section inset series fits a constant-radius circle model",
        ),
    ),
)
def test_general_fixtures_keep_calibrated_structured_rejection(
    slug: str,
    expected_code: str,
    expected_message: str,
    tmp_path: Path,
) -> None:
    with pytest.raises(ReconstructionError) as excinfo:
        reconstruct_file(
            _GENERAL_FIXTURES / slug / "source.stl",
            tmp_path / slug,
            units="mm",
        )

    error = excinfo.value
    assert error.stage == "segmentation"
    assert error.code == expected_code
    assert str(error) == expected_message
    if expected_code == "fillet-band-detected":
        assert error.measured["radiusMm"] == pytest.approx(1.5, abs=0.1)
        rms_residual = error.measured["rmsResidualMm"]
        assert isinstance(rms_residual, float)
        assert rms_residual < 0.03
        assert error.source_triangle_ids
    else:
        assert error.measured == {}
        assert error.source_triangle_ids == ()


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
