from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mesh2param
import pytest
from mesh2param_api.jobs.handlers import (
    JobFailure,
    _reconstruction_project_settings,
    _repair_settings,
    _segmentation_settings,
    _validation_surface_deviation,
    run_handler,
)

ASCII_SQUARE_STL = b"""solid square
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 1 1 0
  endloop
endfacet
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 1 1 0
    vertex 0 1 0
  endloop
endfacet
endsolid square
"""


def _progress(_phase: str, _value: float, _detail: str | None) -> None:
    return None


def _source_payload(source: Path, settings: dict[str, object]) -> dict[str, Any]:
    return {"sourcePath": str(source), "settings": settings}


def _artifact_map(output: Any) -> dict[str, Any]:
    return {artifact.name: artifact for artifact in output.artifacts}


def test_repair_handler_applies_explicit_operations_and_writes_truthful_glbs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.stl"
    source.write_bytes(ASCII_SQUARE_STL)
    payload = _source_payload(source, {"operations": []})
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()

    first = run_handler("repair", payload, first_dir, _progress)
    run_handler("repair", payload, second_dir, _progress)

    settings = first.result["settings"]
    assert isinstance(settings, dict)
    assert not any(value for key, value in settings.items() if isinstance(value, bool))
    operations = first.result["operations"]
    assert isinstance(operations, list)
    assert len(operations) == 9
    assert not any(operation["enabled"] for operation in operations)

    artifacts = _artifact_map(first)
    assert {
        "analysis.json",
        "source.glb",
        "repair.json",
        "repaired.stl",
        "repaired.glb",
    } == set(artifacts)
    assert artifacts["source.glb"].kind == "source-mesh"
    assert artifacts["repaired.glb"].kind == "repaired-mesh"
    assert (first_dir / "source.glb").read_bytes().startswith(b"glTF")
    assert (first_dir / "source.glb").read_bytes() == (
        first_dir / "repaired.glb"
    ).read_bytes()
    for name in ("source.glb", "repaired.glb"):
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes()


def test_analyze_handler_applies_segmentation_settings_and_writes_viewer_glbs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.stl"
    source.write_bytes(ASCII_SQUARE_STL)
    workdir = tmp_path / "analysis"
    workdir.mkdir()

    output = run_handler(
        "analyze",
        _source_payload(
            source,
            {"maxDeviation": 0.125, "minPatchArea": 0.25, "maxAngleDeg": 27.5},
        ),
        workdir,
        _progress,
    )

    analysis = output.state_patch["analysis"]
    assert isinstance(analysis, dict)
    assert analysis["settings"] == {
        "smoothAngleDeg": 27.5,
        "planarFitToleranceMm": 0.125,
        "cylinderFitToleranceMm": 0.125,
        "minimumCylinderCoverageDeg": 300.0,
        "maximumCylinderAxisNormalComponent": 0.05,
        "minimumPatchAreaMm2": 0.25,
        "stableIdResolutionMm": 1e-05,
    }
    artifacts = _artifact_map(output)
    assert {
        name: artifacts[name].kind
        for name in ("source.glb", "repaired.glb", "analysis-proxy.glb")
    } == {
        "source.glb": "source-mesh",
        "repaired.glb": "repaired-mesh",
        "analysis-proxy.glb": "analysis-proxy",
    }
    assert (workdir / "source.glb").read_bytes().startswith(b"glTF")
    assert (workdir / "analysis-proxy.glb").read_bytes() == (
        workdir / "repaired.glb"
    ).read_bytes()


class _FakeCheck:
    valid = True


class _FakeStep:
    valid = True
    source = _FakeCheck()
    reimport = _FakeCheck()

    def to_dict(self) -> dict[str, bool]:
        return {"valid": True}


class _FakeCompilation:
    success = True
    errors: tuple[()] = ()

    def require_shape(self) -> object:
        return object()

    def to_dict(self) -> dict[str, bool]:
        return {"success": True}


@pytest.mark.parametrize(("surface_deviation", "satisfied"), [(0.4, True), (0.2, False)])
def test_validation_setting_updates_graph_and_tolerance_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    surface_deviation: float,
    satisfied: bool,
) -> None:
    fixture = (
        Path(__file__).resolve().parents[2]
        / "packages"
        / "contracts"
        / "tests"
        / "fixtures"
        / "base.cadgraph.json"
    )
    graph = json.loads(fixture.read_text(encoding="utf-8"))
    graph["fitMetrics"]["p95SurfaceDistance"] = 0.15
    graph["fitMetrics"]["maxSurfaceDistance"] = 0.3
    graph["validation"]["status"] = "invalid"
    graph["validation"]["toleranceSatisfied"] = False
    captured: dict[str, Any] = {}

    def compile_cadgraph(value: Any) -> _FakeCompilation:
        captured["surfaceDeviation"] = value.project_tolerance.surface_deviation
        return _FakeCompilation()

    def export_step_validated(
        _shape: object, destination: Path, *, units: str
    ) -> _FakeStep:
        captured["units"] = units
        destination.write_bytes(b"ISO-10303-21;\nEND-ISO-10303-21;\n")
        return _FakeStep()

    def write_cadquery_source(_graph: Any, destination: Path) -> None:
        destination.write_text("# generated\n", encoding="utf-8")

    def export_glb(_shape: object, destination: Path) -> object:
        destination.write_bytes(b"glTF\x02\x00\x00\x00")
        return object()

    monkeypatch.setattr(mesh2param, "compile_cadgraph", compile_cadgraph)
    monkeypatch.setattr(mesh2param, "export_step_validated", export_step_validated)
    monkeypatch.setattr(mesh2param, "write_cadquery_source", write_cadquery_source)
    monkeypatch.setattr(mesh2param, "export_glb", export_glb)

    output = run_handler(
        "validate",
        {"cadgraph": graph, "settings": {"surfaceDeviation": surface_deviation}},
        tmp_path,
        _progress,
    )

    assert captured == {"surfaceDeviation": surface_deviation, "units": "mm"}
    assert output.state_patch["cadgraph"]["projectTolerance"]["surfaceDeviation"] == (
        surface_deviation
    )
    assert output.result["validation"]["toleranceSatisfied"] is satisfied
    assert output.result["artifactValidationState"] == (
        "valid" if satisfied else "invalid"
    )
    assert graph["projectTolerance"]["surfaceDeviation"] == 0.1


@pytest.mark.parametrize(
    ("factory", "settings", "code"),
    [
        (
            _repair_settings,
            {"operations": ["repairNormals", "repairNormals"]},
            "invalid_repair_settings",
        ),
        (_repair_settings, {"operations": ["notSupported"]}, "invalid_repair_settings"),
        (_segmentation_settings, {"maxDeviation": float("nan")}, "invalid_segmentation_settings"),
        (_segmentation_settings, {"maxAngleDeg": 90}, "invalid_segmentation_settings"),
        (_segmentation_settings, {"minPatchArea": "5"}, "invalid_segmentation_settings"),
        (_validation_surface_deviation, {"surfaceDeviation": 0}, "invalid_validation_settings"),
        (_validation_surface_deviation, {"surfaceDeviation": True}, "invalid_validation_settings"),
        (_validation_surface_deviation, {"ignored": 1}, "invalid_validation_settings"),
    ],
)
def test_job_settings_fail_closed(
    factory: Any, settings: dict[str, object], code: str
) -> None:
    with pytest.raises(JobFailure) as captured:
        factory({"settings": settings})
    assert captured.value.code == code


def test_reconstruction_persists_selectable_candidate_histories_without_losing_settings() -> None:
    candidate = {
        "label": "measured",
        "score": 0.99,
        "valid": True,
        "rejectionReason": None,
        "featureCount": 5,
        "cadgraph": {"schemaVersion": "1.0.0", "id": "candidate"},
        "kernel": {"success": True},
        "comparison": {"p95DistanceMm": 0.01},
    }
    result = {"candidates": [candidate], "selectedCandidate": "measured"}
    settings = _reconstruction_project_settings(
        {"projectState": {"settings": {"surfaceTolerance": 0.1}}}, result
    )

    assert settings == {
        "surfaceTolerance": 0.1,
        "candidateHistories": [candidate],
        "selectedCandidate": "measured",
    }
    candidate["label"] = "mutated"
    assert settings["candidateHistories"][0]["label"] == "measured"
