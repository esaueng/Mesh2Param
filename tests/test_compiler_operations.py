from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import mesh2param.samples as sample_models
import numpy as np
import pytest
import trimesh
from mesh2param import (
    CompilationResult,
    FacetedFallbackError,
    compile_cadgraph,
    create_faceted_fallback,
)
from mesh2param.samples import sample_graph
from mesh2param.tessellation import export_binary_stl
from mesh2param.validation import export_step_validated
from mesh2param_contracts import CADGraph


def _document(slug: str = "rectangular-block") -> dict[str, Any]:
    return sample_graph(slug).model_dump(mode="json", by_alias=True)


def _result_reference(feature: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"{feature['id']}.result",
        "kind": "solid",
        "producerFeatureId": feature["id"],
        "role": "resultSolid",
        "generatedFrom": list(feature.get("profileIds", feature.get("sourceFeatureIds", []))),
        "status": "unresolved",
    }


def _append_feature(document: dict[str, Any], feature: dict[str, Any]) -> None:
    document["features"].append(feature)
    document["semanticTopology"].append(_result_reference(feature))


def _compile(document: dict[str, Any]) -> CompilationResult:
    result = compile_cadgraph(CADGraph.model_validate(document))
    assert result.success, [error.to_dict() for error in result.errors]
    return result


@pytest.mark.geometry
def test_additive_and_through_all_subtractive_extrusions() -> None:
    document = _document()
    document["sketches"].extend(
        (
            sample_models._xy_rectangle_sketch(
                "sketch.boss", "Boss", 16.0, 10.0, x=12.0, y=10.0, z=12.0
            ),
            sample_models._xy_rectangle_sketch(
                "sketch.slot", "Slot", 6.0, 14.0, x=17.0, y=8.0, z=16.0
            ),
        )
    )
    boss = sample_models._extrusion(
        "feature.boss",
        "Additive boss",
        1,
        "sketch.boss",
        (0, 0, 1),
        4.0,
        mode="additive",
        dependencies=["feature.base"],
    )
    slot = sample_models._extrusion(
        "feature.slot",
        "Through slot",
        2,
        "sketch.slot",
        (0, 0, -1),
        1.0,
        mode="subtractive",
        dependencies=["feature.boss"],
    )
    slot["extent"] = "throughAll"
    slot.pop("distance")
    _append_feature(document, boss)
    _append_feature(document, slot)
    result = _compile(document)
    assert result.require_shape().Volume() == pytest.approx(13792.0, abs=1e-8)


@pytest.mark.geometry
@pytest.mark.parametrize("operation", ("counterbore", "countersink"))
def test_compound_holes(operation: str) -> None:
    document = _document()
    feature = {
        **sample_models._feature_fields(
            f"feature.{operation}", operation.title(), 1, ["feature.base"]
        ),
        "operation": operation,
        "booleanMode": "subtractive",
        "holeType": "through",
        "position": {"x": 20.0, "y": 15.0, "z": 12.0},
        "axis": {"x": 0.0, "y": 0.0, "z": -1.0},
        "diameter": 6.0,
    }
    if operation == "counterbore":
        feature.update(boreDiameter=10.0, boreDepth=3.0)
    else:
        feature.update(sinkDiameter=12.0, sinkAngleDeg=90.0)
    _append_feature(document, feature)
    result = _compile(document)
    kinds = [str(face.geomType()) for face in result.require_shape().Faces()]
    expected = "CONE" if operation == "countersink" else "CYLINDER"
    assert expected in kinds
    assert result.require_shape().Volume() < 14400.0


@pytest.mark.geometry
def test_additive_and_subtractive_revolutions() -> None:
    document = _document("stepped-turned-part")
    document["sketches"].extend(
        (
            sample_models._xz_revolution_sketch(
                "sketch.flange", "Added flange", [(7, 10), (12, 10), (12, 15), (7, 15)]
            ),
            sample_models._xz_revolution_sketch(
                "sketch.groove", "Turned groove", [(5, 42), (9, 42), (9, 47), (5, 47)]
            ),
        )
    )
    additive = sample_models._revolution(
        "feature.flange",
        "Additive revolution",
        1,
        "sketch.flange",
        mode="additive",
        dependencies=["feature.base"],
    )
    subtractive = sample_models._revolution(
        "feature.groove",
        "Subtractive revolution",
        2,
        "sketch.groove",
        mode="subtractive",
        dependencies=["feature.flange"],
    )
    _append_feature(document, additive)
    _append_feature(document, subtractive)
    result = _compile(document)
    assert result.require_shape().isValid()
    assert len(result.feature_records) == 3


@pytest.mark.geometry
def test_linear_circular_patterns_and_mirror_samples() -> None:
    plate = _compile(_document("four-hole-mounting-plate")).require_shape()
    assert plate.Volume() == pytest.approx(31095.221315766132, abs=1e-8)
    assert _compile(_document("flange")).require_shape().Volume() == pytest.approx(
        37623.713619391347, abs=1e-8
    )

    document = _document()
    document["sketches"].append(
        sample_models._xy_rectangle_sketch("sketch.boss", "Boss", 4.0, 4.0, x=4.0, y=13.0, z=12.0)
    )
    boss = sample_models._extrusion(
        "feature.boss",
        "Boss",
        1,
        "sketch.boss",
        (0, 0, 1),
        4.0,
        mode="additive",
        dependencies=["feature.base"],
    )
    mirror = {
        **sample_models._feature_fields("feature.mirror", "Mirrored boss", 2, ["feature.boss"]),
        "operation": "mirror",
        "sourceFeatureIds": ["feature.boss"],
        "plane": {
            "origin": {"x": 20.0, "y": 0.0, "z": 0.0},
            "normal": {"x": 1.0, "y": 0.0, "z": 0.0},
            "xAxis": {"x": 0.0, "y": 1.0, "z": 0.0},
        },
        "keepOriginals": True,
    }
    _append_feature(document, boss)
    _append_feature(document, mirror)
    result = _compile(document)
    assert result.require_shape().Volume() == pytest.approx(14528.0, abs=1e-8)


@pytest.mark.geometry
@pytest.mark.parametrize("operation", ("chamfer", "fillet"))
def test_constant_edge_finishes(operation: str) -> None:
    document = _document()
    target = "feature.base.edge.1"
    feature = {
        **sample_models._feature_fields(
            f"feature.{operation}", operation.title(), 1, ["feature.base"]
        ),
        "operation": operation,
        "targetEdges": [target],
        "width" if operation == "chamfer" else "radius": 1.0,
    }
    _append_feature(document, feature)
    result = _compile(document)
    assert result.require_shape().isValid()
    assert result.require_shape().Volume() < 14400.0


@pytest.mark.geometry
def test_imported_step_and_faceted_stl_fallbacks(tmp_path: Path) -> None:
    source = _compile(_document()).require_shape()
    step_path = tmp_path / "source.step"
    export_step_validated(source, step_path)
    stl_path = tmp_path / "source.stl"
    export_binary_stl(source, stl_path)

    for artifact_id, path in (("artifact.step", step_path), ("artifact.stl", stl_path)):
        document = _document()
        document["sketches"] = []
        feature = {
            **sample_models._feature_fields("feature.imported", "Imported fallback", 0, []),
            "operation": "importedFaceted",
            "booleanMode": "base",
            "sourceArtifactId": artifact_id,
            "meshSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "intent": "fallback",
        }
        document["features"] = [feature]
        document["semanticTopology"] = [_result_reference(feature)]
        result = compile_cadgraph(
            CADGraph.model_validate(document), artifact_resolver={artifact_id: path}
        )
        assert result.success, [error.to_dict() for error in result.errors]
        assert result.require_shape().Volume() == pytest.approx(14400.0, abs=1e-6)
        if path.suffix == ".stl":
            document["source"]["scaleFactor"] = 2.0
            transformed = compile_cadgraph(
                CADGraph.model_validate(document), artifact_resolver={artifact_id: path}
            )
            assert not transformed.success
            assert transformed.errors[0].code == "faceted_source_transform_unsupported"


@pytest.mark.geometry
def test_imported_faceted_explicitly_sews_a_bounded_open_seam(tmp_path: Path) -> None:
    box = trimesh.creation.box(extents=(10.0, 10.0, 10.0))
    top_faces = np.flatnonzero(np.asarray(box.triangles_center)[:, 2] > 4.9)
    open_box = trimesh.Trimesh(
        vertices=np.asarray(box.vertices).copy(),
        faces=np.delete(np.asarray(box.faces), top_faces, axis=0),
        process=False,
    )
    cap = trimesh.Trimesh(
        vertices=np.asarray(
            [
                (-5.0, -5.0, 5.02),
                (5.0, -5.0, 5.02),
                (5.0, 5.0, 5.02),
                (-5.0, 5.0, 5.02),
            ],
            dtype=np.float64,
        ),
        faces=np.asarray(((0, 1, 2), (0, 2, 3)), dtype=np.int64),
        process=False,
    )
    path = tmp_path / "open-seam.stl"
    trimesh.util.concatenate((open_box, cap)).export(path)

    document = _document()
    document["sketches"] = []
    feature = {
        **sample_models._feature_fields("feature.imported", "Imported fallback", 0, []),
        "operation": "importedFaceted",
        "booleanMode": "base",
        "sourceArtifactId": "artifact.source",
        "meshSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "intent": "fallback",
        "sewingTolerance": 0.05,
    }
    document["features"] = [feature]
    document["semanticTopology"] = [_result_reference(feature)]

    result = compile_cadgraph(
        CADGraph.model_validate(document), artifact_resolver={"artifact.source": path}
    )
    assert result.success, [error.to_dict() for error in result.errors]
    assert result.require_shape().Volume() == pytest.approx(1000.666666, abs=1e-4)
    assert result.feature_records[0].validation is not None
    assert result.feature_records[0].validation.triangle_count == 0
    step = export_step_validated(
        result.require_shape(),
        tmp_path / "open-seam.step",
        require_tessellation=False,
    )
    assert step.valid
    assert step.source.triangle_count == 0
    assert step.reimport.triangle_count == 0
    initial_descriptor = result.topology["feature.imported.result"].descriptor
    assert initial_descriptor is not None
    assert initial_descriptor["meshSha256"] == feature["meshSha256"]
    assert initial_descriptor["sewingTolerance"] == 0.05
    assert initial_descriptor["units"] == "mm"

    feature["sewingTolerance"] = 0.005
    failed = compile_cadgraph(
        CADGraph.model_validate(document), artifact_resolver={"artifact.source": path}
    )
    assert not failed.success
    assert failed.errors[0].code == "faceted_sewing_incomplete"

    feature["sewingTolerance"] = 0.05
    hole = sample_models._hole(
        "feature.hole",
        "Through hole",
        1,
        (0.0, 0.0, 5.02),
        (0.0, 0.0, -1.0),
        2.0,
        dependencies=["feature.imported"],
    )
    _append_feature(document, hole)
    refined = compile_cadgraph(
        CADGraph.model_validate(document), artifact_resolver={"artifact.source": path}
    )
    assert refined.success, [error.to_dict() for error in refined.errors]
    remapped_descriptor = refined.topology["feature.imported.result"].descriptor
    assert remapped_descriptor is not None
    assert "meshSha256" not in remapped_descriptor
    assert (
        refined.topology["feature.imported.result"].descriptor_hash
        != result.topology["feature.imported.result"].descriptor_hash
    )


@pytest.mark.geometry
def test_imported_faceted_enforces_ten_millimeter_limit_in_project_units(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.stl"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(path)
    document = _document()
    document["units"] = "in"
    document["source"]["declaredUnits"] = "in"
    document["sketches"] = []
    feature = {
        **sample_models._feature_fields("feature.imported", "Imported fallback", 0, []),
        "operation": "importedFaceted",
        "booleanMode": "base",
        "sourceArtifactId": "artifact.source",
        "meshSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "intent": "fallback",
        # 0.4 inches is 10.16 mm and must be rejected despite satisfying the schema's
        # unit-agnostic numeric maximum.
        "sewingTolerance": 0.4,
    }
    document["features"] = [feature]
    document["semanticTopology"] = [_result_reference(feature)]

    result = compile_cadgraph(
        CADGraph.model_validate(document), artifact_resolver={"artifact.source": path}
    )

    assert not result.success
    assert result.errors[0].code == "invalid_sewing_tolerance"
    assert "0.393701 in (10 mm)" in result.errors[0].kernel_error


@pytest.mark.geometry
def test_faceted_fallback_converts_default_mm_tolerance_and_marks_proxy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.stl"
    trimesh.creation.box(extents=(1.0, 2.0, 3.0)).export(path)

    fallback = create_faceted_fallback(path, tmp_path / "fallback", units="in")

    feature = fallback.graph.features[0]
    assert feature.operation == "importedFaceted"
    assert feature.sewing_tolerance == pytest.approx(0.05 / 25.4)
    assert fallback.sewing_tolerance == pytest.approx(0.05 / 25.4)
    assert fallback.sewing_tolerance_mm == pytest.approx(0.05)
    assert fallback.graph.project_tolerance.linear_resolution == pytest.approx(0.001 / 25.4)
    assert fallback.graph.validation.status == "partial"
    assert fallback.graph.validation.tolerance_satisfied is None

    report = json.loads((tmp_path / "fallback" / "validation.json").read_text(encoding="utf-8"))
    assert report["status"] == "partial"
    assert report["toleranceSatisfied"] is None
    assert report["facetedFallback"]["sewingTolerance"] == pytest.approx(0.05 / 25.4)
    assert report["facetedFallback"]["sewingToleranceUnits"] == "in"
    assert report["facetedFallback"]["sewingToleranceMm"] == pytest.approx(0.05)
    assert report["facetedFallback"]["browserTessellation"] == "preserved-source-proxy"
    assert report["facetedFallback"]["browserTessellationRepresentsKernelResult"] is False
    assert (tmp_path / "fallback" / "source.glb").read_bytes() == (
        tmp_path / "fallback" / "reconstructed.glb"
    ).read_bytes()


def test_faceted_fallback_rejects_unimplemented_source_unit_or_scale_transform(
    tmp_path: Path,
) -> None:
    path = tmp_path / "source.stl"
    trimesh.creation.box(extents=(1.0, 2.0, 3.0)).export(path)
    descriptor = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "format": "stl",
        "originalFileName": "source.stl",
        "declaredUnits": "in",
        "scaleFactor": 1.0,
    }

    with pytest.raises(FacetedFallbackError) as units_error:
        create_faceted_fallback(
            path,
            tmp_path / "units-mismatch",
            units="mm",
            source_descriptor=descriptor,
        )
    assert units_error.value.code == "faceted_source_transform_unsupported"

    descriptor["declaredUnits"] = "mm"
    descriptor["scaleFactor"] = 2.0
    with pytest.raises(FacetedFallbackError) as scale_error:
        create_faceted_fallback(
            path,
            tmp_path / "scale-mismatch",
            units="mm",
            source_descriptor=descriptor,
        )
    assert scale_error.value.code == "faceted_source_transform_unsupported"


@pytest.mark.geometry
def test_failure_preserves_last_valid_result_and_reports_feature_context() -> None:
    document = _document()
    document["sketches"].append(
        sample_models._xy_rectangle_sketch(
            "sketch.miss", "Nonintersecting boss", 4.0, 4.0, x=100.0, y=100.0, z=12.0
        )
    )
    feature = sample_models._extrusion(
        "feature.miss",
        "Nonintersecting boss",
        1,
        "sketch.miss",
        (0, 0, 1),
        4.0,
        mode="additive",
        dependencies=["feature.base"],
    )
    _append_feature(document, feature)
    result = compile_cadgraph(CADGraph.model_validate(document))
    assert not result.success
    assert result.last_valid_feature_id == "feature.base"
    assert result.require_last_valid_shape().Volume() == pytest.approx(14400.0)
    assert result.errors[0].feature_id == "feature.miss"
    assert result.errors[0].code in {"boolean_no_effect", "solid_count"}
    assert "feature.miss.result" not in result.topology
    assert result.topology["feature.base.result"].shape is not None
    assert result.topology["feature.base.result"].shape.Volume() == pytest.approx(14400.0)


@pytest.mark.geometry
def test_semantic_topology_descriptors_repeat_across_rebuilds() -> None:
    graph = sample_graph("block-through-hole")
    first = compile_cadgraph(graph)
    second = compile_cadgraph(graph, previous_topology=first.topology)
    assert first.success and second.success
    assert first.topology["feature.base.result"].status == "resolved"
    assert second.topology["feature.hole.result"].status == "resolved"
    assert first.feature_records[-1].topology_hash == second.feature_records[-1].topology_hash
    resolved = (record for record in second.topology.values() if record.status == "resolved")
    assert all(record.descriptor_hash for record in resolved)
