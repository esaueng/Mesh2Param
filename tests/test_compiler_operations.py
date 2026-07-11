from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import mesh2param.samples as sample_models
import pytest
from mesh2param import CompilationResult, compile_cadgraph
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
