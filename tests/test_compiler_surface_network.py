from __future__ import annotations

from pathlib import Path
from typing import Any

import mesh2param.samples as sample_models
import pytest
import trimesh
from mesh2param import compile_cadgraph
from mesh2param.curved_fixtures import (
    CURVED_FIXTURES_BY_SLUG,
    FIXTURE_STL_NAME,
    generate_curved_fixture,
)
from mesh2param.curved_patch import (
    CurvedNetworkResult,
    CurvedPatchSettings,
    plate_artifact_bytes,
    plate_artifact_payload,
    plate_artifact_sha256,
    reconstruct_plate_network,
)
from mesh2param.samples import sample_graph
from mesh2param.validation import export_step_validated
from mesh2param_contracts import CADGraph

SETTINGS = CurvedPatchSettings(
    fit_tolerance_mm=0.25,
    surface_deviation_tolerance_mm=0.3,
    comparison_sample_count=500,
)


@pytest.fixture(scope="module")
def reconstruction(tmp_path_factory: pytest.TempPathFactory) -> CurvedNetworkResult:
    root = tmp_path_factory.mktemp("curved-plate-compile")
    generate_curved_fixture(CURVED_FIXTURES_BY_SLUG["bspline-bump-plate-hole"], root)
    mesh = trimesh.load_mesh(root / "bspline-bump-plate-hole" / FIXTURE_STL_NAME, process=True)
    assert isinstance(mesh, trimesh.Trimesh)
    return reconstruct_plate_network(mesh, settings=SETTINGS)


def _network_document(artifact_sha256: str) -> dict[str, Any]:
    document = sample_graph("rectangular-block").model_dump(mode="json", by_alias=True)
    document["sketches"] = []
    feature = {
        **sample_models._feature_fields("feature.curved", "Reconstructed surface network", 0, []),
        "operation": "reconstructedSurfaceNetwork",
        "sourceArtifactId": "artifact.curved-plate",
        "artifactSha256": artifact_sha256,
    }
    document["features"] = [feature]
    document["semanticTopology"] = [
        {
            "id": "feature.curved.result",
            "kind": "solid",
            "producerFeatureId": "feature.curved",
            "role": "resultSolid",
            "generatedFrom": [],
            "status": "unresolved",
        }
    ]
    return document


def _write_artifact(reconstruction: CurvedNetworkResult, directory: Path) -> tuple[Path, str]:
    payload = plate_artifact_payload(reconstruction)
    path = directory / "curved-plate.json"
    path.write_bytes(plate_artifact_bytes(payload))
    return path, plate_artifact_sha256(payload)


@pytest.mark.geometry
def test_compiler_rebuilds_the_identical_hybrid_solid(
    reconstruction: CurvedNetworkResult, tmp_path: Path
) -> None:
    artifact_path, artifact_sha = _write_artifact(reconstruction, tmp_path)
    document = _network_document(artifact_sha)
    result = compile_cadgraph(
        CADGraph.model_validate(document),
        artifact_resolver={"artifact.curved-plate": artifact_path},
    )
    assert result.success, [error.to_dict() for error in result.errors]
    compiled = result.require_shape()

    driver_sha = export_step_validated(
        reconstruction.solid, tmp_path / "driver" / "plate.step"
    ).sha256
    compiled_sha = export_step_validated(compiled, tmp_path / "compiled" / "plate.step").sha256
    assert compiled_sha == driver_sha
    assert compiled.Volume() == pytest.approx(reconstruction.solid.Volume(), abs=1e-9)


@pytest.mark.geometry
def test_compiler_rejects_artifact_hash_mismatch(
    reconstruction: CurvedNetworkResult, tmp_path: Path
) -> None:
    artifact_path, _ = _write_artifact(reconstruction, tmp_path)
    document = _network_document("0" * 64)
    result = compile_cadgraph(
        CADGraph.model_validate(document),
        artifact_resolver={"artifact.curved-plate": artifact_path},
    )
    assert not result.success
    assert any(error.code == "artifact_hash_mismatch" for error in result.errors)


@pytest.mark.geometry
def test_compiler_rejects_corrupt_artifact(
    reconstruction: CurvedNetworkResult, tmp_path: Path
) -> None:
    import hashlib

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text('{"schema": "mesh2param/curved-plate/999"}', encoding="utf-8")
    document = _network_document(hashlib.sha256(corrupt.read_bytes()).hexdigest())
    result = compile_cadgraph(
        CADGraph.model_validate(document),
        artifact_resolver={"artifact.curved-plate": corrupt},
    )
    assert not result.success
    assert any(error.code == "network_rebuild_failed" for error in result.errors)


@pytest.mark.geometry
def test_downstream_features_operate_on_the_curved_base(
    reconstruction: CurvedNetworkResult, tmp_path: Path
) -> None:
    artifact_path, artifact_sha = _write_artifact(reconstruction, tmp_path)
    document = _network_document(artifact_sha)
    document["sketches"] = [
        sample_models._xy_rectangle_sketch("sketch.slot", "Slot", 10.0, 10.0, x=8.0, y=8.0, z=10.0)
    ]
    slot = {
        **sample_models._feature_fields("feature.slot", "Corner slot", 1, ["feature.curved"]),
        "operation": "extrusion",
        "booleanMode": "subtractive",
        "sketchId": "sketch.slot",
        "profileIds": ["sketch.slot.profile"],
        "direction": {"x": 0.0, "y": 0.0, "z": -1.0},
        "extent": "blind",
        "distance": 50.0,
    }
    document["features"].append(slot)
    document["semanticTopology"].append(
        {
            "id": "feature.slot.result",
            "kind": "solid",
            "producerFeatureId": "feature.slot",
            "role": "resultSolid",
            "generatedFrom": ["sketch.slot.profile"],
            "status": "unresolved",
        }
    )
    result = compile_cadgraph(
        CADGraph.model_validate(document),
        artifact_resolver={"artifact.curved-plate": artifact_path},
    )
    assert result.success, [error.to_dict() for error in result.errors]
    assert result.require_shape().Volume() < reconstruction.solid.Volume()
