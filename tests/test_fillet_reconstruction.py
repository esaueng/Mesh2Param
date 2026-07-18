"""G3b semantic fillet emission and end-to-end acceptance evidence."""

from __future__ import annotations

from pathlib import Path

import pytest
from mesh2param.reconstruction import PrismaticReconstructionResult, reconstruct_file
from mesh2param.validation import classify_parametric_face_surfaces, import_step_shape
from mesh2param_contracts.models import ExtrusionFeature, FilletFeature

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    REPOSITORY_ROOT / "samples" / "general-parametric-benchmark" / "spanner-filleted" / "source.stl"
)


@pytest.mark.geometry
@pytest.mark.samples
def test_filleted_spanner_emits_semantic_fillet_and_is_deterministic(
    tmp_path: Path,
) -> None:
    outputs = (tmp_path / "first", tmp_path / "second")
    first = reconstruct_file(FIXTURE, outputs[0], units="mm")
    second = reconstruct_file(FIXTURE, outputs[1], units="mm")

    assert isinstance(first, PrismaticReconstructionResult)
    assert isinstance(second, PrismaticReconstructionResult)
    assert first.selected.label == "analytic-prismatic-spline-filleted"
    assert [feature.operation for feature in first.graph.features] == [
        "extrusion",
        "fillet",
        "extrusion",
    ]
    base, fillet, cut = first.graph.features
    assert isinstance(base, ExtrusionFeature)
    assert isinstance(fillet, FilletFeature)
    assert isinstance(cut, ExtrusionFeature)
    assert fillet.radius == pytest.approx(1.5, abs=0.02)
    assert len(fillet.target_edges) == 8
    assert all(target.startswith("feature.base.edge.") for target in fillet.target_edges)
    assert cut.dependencies == [fillet.id]
    assert cut.extent == "throughAll"

    assert len(first.candidates) == 2
    sharp, selected = first.candidates
    assert sharp.label == "analytic-prismatic-spline-sharp-parent"
    assert not sharp.valid
    assert sharp.rejection_reason is not None
    assert sharp.rejection_reason.startswith("measured fillet-band mismatch:")
    assert sharp.comparison is not None
    assert sharp.comparison.p95_distance_mm > 0.3
    assert selected.valid

    tolerance = first.graph.project_tolerance.surface_deviation
    comparison = first.comparison
    assert comparison.p95_distance_mm <= 1.5 * tolerance
    assert comparison.p99_distance_mm <= 3.0 * tolerance
    assert comparison.maximum_distance_mm <= 6.0 * tolerance
    assert comparison.p95_normal_angle_deg <= 3.0
    assert comparison.relative_volume_delta is not None
    assert comparison.relative_volume_delta <= 0.001
    assert first.step.valid
    assert first.step.parametric_surface_audit is not None
    assert first.step.parametric_surface_audit.valid
    assert first.graph.validation.status == "valid"
    assert first.step.source.face_count == 20
    assert len(first.source.mesh.faces) == 5_858

    surfaces = classify_parametric_face_surfaces(import_step_shape(first.step.path))
    assert surfaces == {
        "plane": 10,
        "cylinder": 5,
        "cone": 0,
        "sphere": 0,
        "torus": 2,
        "bspline": 2,
        "bezier": 0,
        "surfaceOfExtrusion": 1,
        "surfaceOfRevolution": 0,
        "offset": 0,
        "other": 0,
    }

    for artifact in (
        "model.cadgraph.json",
        "model.cq.py",
        "model.step",
        "candidates.json",
        "sections.json",
        "sections.glb",
        "fillets.json",
    ):
        assert (outputs[0] / artifact).read_bytes() == (outputs[1] / artifact).read_bytes(), (
            artifact
        )
