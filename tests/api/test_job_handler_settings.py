from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import mesh2param
import mesh2param.tessellation as tessellation_module
import pytest
import trimesh
from mesh2param_api.jobs.handlers import (
    JobFailure,
    _automatic_detail_mode,
    _faceted_sewing_tolerance,
    _reconstruction_project_settings,
    _reconstruction_segmentation_settings,
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
    assert (first_dir / "source.glb").read_bytes() == (first_dir / "repaired.glb").read_bytes()
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
    assert analysis["prismaticCandidate"]["accepted"] is False
    assert analysis["prismaticCandidate"]["diagnostics"][0]["code"] == ("no_opposing_planar_caps")
    assert analysis["settings"] == {
        "smoothAngleDeg": 27.5,
        "planarFitToleranceMm": 0.125,
        "cylinderFitToleranceMm": 0.125,
        "sphereFitToleranceMm": 0.01,
        "coneFitToleranceMm": 0.01,
        "torusFitToleranceMm": 0.01,
        "minimumCylinderCoverageDeg": 300.0,
        "minimumRevolutionCoverageDeg": 300.0,
        "minimumConeHalfAngleDeg": 5.0,
        "maximumConeHalfAngleDeg": 85.0,
        "maximumCylinderAxisNormalComponent": 0.05,
        "minimumFacetedCylinderSideCount": 8,
        "maximumFacetedCylinderSagittaMm": 0.1,
        "minimumPatchAreaMm2": 0.25,
        "stableIdResolutionMm": 1e-05,
    }
    artifacts = _artifact_map(output)
    assert {
        name: artifacts[name].kind for name in ("source.glb", "repaired.glb", "analysis-proxy.glb")
    } == {
        "source.glb": "source-mesh",
        "repaired.glb": "repaired-mesh",
        "analysis-proxy.glb": "analysis-proxy",
    }
    assert (workdir / "source.glb").read_bytes().startswith(b"glTF")
    assert (workdir / "analysis-proxy.glb").read_bytes() == (workdir / "repaired.glb").read_bytes()


@pytest.mark.geometry
def test_reconstruct_handler_creates_explicit_faceted_step_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.stl"
    trimesh.creation.box(extents=(5.0, 6.0, 7.0)).export(source)
    workdir = tmp_path / "faceted"
    workdir.mkdir()

    output = run_handler(
        "reconstruct",
        {
            "sourcePath": str(source),
            "settings": {"mode": "faceted", "sewingTolerance": 0.05},
            "units": "mm",
            "source": {
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "format": "stl",
                "originalFileName": "source.stl",
                "declaredUnits": "mm",
                "scaleFactor": 1.0,
            },
            "projectState": {"settings": {"theme": "dark"}},
        },
        workdir,
        _progress,
    )

    assert output.result["status"] == "valid"
    assert output.result["scope"] == "explicit non-parametric faceted fallback"
    assert output.state_patch["cadgraph"]["features"][0]["operation"] == "importedFaceted"
    assert output.state_patch["cadgraph"]["features"][0]["sewingTolerance"] == 0.05
    assert output.state_patch["cadgraph"]["source"]["originalFileName"] == "source.stl"
    assert output.state_patch["cadgraph"]["source"]["declaredUnits"] == "mm"
    assert output.state_patch["cadgraph"]["source"]["scaleFactor"] == 1.0
    assert output.state_patch["validation"]["stepReimportValid"] is True
    assert output.state_patch["settings"]["theme"] == "dark"
    assert output.state_patch["settings"]["facetedFallback"] == {
        "nonParametric": True,
        "sewingTolerance": 0.05,
        "units": "mm",
        "sourceSha256": output.state_patch["cadgraph"]["source"]["sha256"],
    }
    assert {
        "source.original.stl",
        "model.step",
        "model.cadgraph.json",
        "model.cq.py",
        "reconstructed.glb",
        "validation.json",
        "faceted-fallback.json",
    } <= set(_artifact_map(output))
    assert _artifact_map(output)["reconstructed.glb"].kind == "preserved-source-proxy"

    rebuild_dir = tmp_path / "faceted-rebuild"
    rebuild_dir.mkdir()
    real_export_step_validated = mesh2param.export_step_validated
    rebuild_export: dict[str, object] = {}

    def export_step_validated(*args: Any, **kwargs: Any) -> Any:
        rebuild_export.update(kwargs)
        return real_export_step_validated(*args, **kwargs)

    monkeypatch.setattr(mesh2param, "export_step_validated", export_step_validated)
    rebuilt = run_handler(
        "rebuild",
        {
            "sourcePath": str(source),
            "cadgraph": output.state_patch["cadgraph"],
            "settings": {},
        },
        rebuild_dir,
        _progress,
    )
    assert rebuilt.result["validation"]["stepReimportValid"] is True
    assert rebuilt.result["validation"]["status"] == "partial"
    assert rebuilt.result["validation"]["toleranceSatisfied"] is None
    assert rebuilt.result["validation"]["facetedFallback"] == {
        "nonParametric": True,
        "sewingTolerance": 0.05,
        "sewingToleranceUnits": "mm",
        "importedFeatureCount": 1,
        "sourcePreserved": True,
        "geometricDeviationMeasured": False,
        "browserTessellation": "preserved-source-proxy",
        "browserTessellationRepresentsKernelResult": False,
    }
    assert rebuilt.result["artifactValidationState"] == "partial"
    assert (
        rebuild_export["linear_resolution"]
        == (output.state_patch["cadgraph"]["projectTolerance"]["linearResolution"])
    )
    assert rebuild_export["require_tessellation"] is False
    assert _artifact_map(rebuilt)["reconstructed.glb"].kind == "preserved-source-proxy"
    assert "source.original.stl" in _artifact_map(rebuilt)
    assert "artifact.source" in (rebuild_dir / "model.cq.py").read_text(encoding="utf-8")

    derived_graph = copy.deepcopy(output.state_patch["cadgraph"])
    derived_graph["features"].append(
        {
            "id": "feature.downstream-hole",
            "name": "Downstream hole",
            "order": 1,
            "dependencies": ["feature.faceted-source"],
            "suppressed": False,
            "sourceEvidence": [],
            "confidence": 1.0,
            "userLocks": [],
            "overrides": [],
            "semanticOutputs": [],
            "operation": "hole",
            "booleanMode": "subtractive",
            "holeType": "through",
            "position": {"x": 0.0, "y": 0.0, "z": 3.5},
            "axis": {"x": 0.0, "y": 0.0, "z": -1.0},
            "diameter": 1.0,
            "depth": None,
            "terminationFace": None,
        }
    )
    derived_dir = tmp_path / "faceted-derived-rebuild"
    derived_dir.mkdir()
    derived = run_handler(
        "rebuild",
        {
            "sourcePath": str(source),
            "cadgraph": derived_graph,
            "settings": {},
        },
        derived_dir,
        _progress,
    )
    assert derived.result["validation"]["status"] == "partial"
    assert derived.result["validation"]["toleranceSatisfied"] is None
    assert derived.result["validation"]["facetedFallback"]["importedFeatureCount"] == 1
    assert derived.result["validation"]["facetedFallback"]["browserTessellation"] == "kernel-result"
    assert (
        derived.result["validation"]["facetedFallback"]["browserTessellationRepresentsKernelResult"]
        is True
    )
    assert _artifact_map(derived)["reconstructed.glb"].kind == "reconstructed"


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

    def export_step_validated(_shape: object, destination: Path, *, units: str) -> _FakeStep:
        captured["units"] = units
        destination.write_bytes(b"ISO-10303-21;\nEND-ISO-10303-21;\n")
        return _FakeStep()

    def write_cadquery_source(_graph: Any, destination: Path) -> None:
        destination.write_text("# generated\n", encoding="utf-8")

    def tessellate_shape(
        _shape: object,
        **_settings: float,
    ) -> mesh2param.Tessellation:
        return mesh2param.Tessellation(
            vertices=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
            triangles=((0, 1, 2),),
            normals=(),
        )

    monkeypatch.setattr(mesh2param, "compile_cadgraph", compile_cadgraph)
    monkeypatch.setattr(mesh2param, "export_step_validated", export_step_validated)
    monkeypatch.setattr(mesh2param, "write_cadquery_source", write_cadquery_source)
    monkeypatch.setattr(mesh2param, "tessellate_shape", tessellate_shape)
    monkeypatch.setattr(
        tessellation_module,
        "display_tessellation",
        lambda _shape: tessellation_module.DisplayTessellation(0.1, 0.1, 0.05, 1.0),
    )
    monkeypatch.setattr(tessellation_module, "sample_shape_edges", lambda *_args, **_kwargs: ())

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
    assert output.result["artifactValidationState"] == ("valid" if satisfied else "invalid")
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
        (
            _faceted_sewing_tolerance,
            {"mode": "faceted", "sewingTolerance": 0},
            "invalid_faceted_settings",
        ),
        (_faceted_sewing_tolerance, {"mode": "faceted", "ignored": 1}, "invalid_faceted_settings"),
    ],
)
def test_job_settings_fail_closed(factory: Any, settings: dict[str, object], code: str) -> None:
    payload: dict[str, object] = {"settings": settings}
    if factory is _faceted_sewing_tolerance:
        payload["units"] = "mm"
    with pytest.raises(JobFailure) as captured:
        factory(payload)
    assert captured.value.code == code


def test_faceted_sewing_tolerance_is_explicit_and_bounded() -> None:
    assert _faceted_sewing_tolerance({"settings": {}}) is None
    assert _faceted_sewing_tolerance({"settings": {"mode": "faceted"}, "units": "mm"}) == 0.05
    assert _faceted_sewing_tolerance({"settings": {"mode": "faceted"}, "units": "cm"}) == 0.005
    assert (
        _faceted_sewing_tolerance(
            {"settings": {"mode": "faceted", "sewingTolerance": 0.125}, "units": "in"}
        )
        == 0.125
    )
    with pytest.raises(JobFailure) as above_maximum:
        _faceted_sewing_tolerance(
            {"settings": {"mode": "faceted", "sewingTolerance": 0.4}, "units": "in"}
        )
    assert above_maximum.value.recommended_action is not None
    assert "10 mm" in above_maximum.value.recommended_action
    with pytest.raises(JobFailure, match="explicit mm, cm, m, in, or ft"):
        _faceted_sewing_tolerance({"settings": {"mode": "faceted"}, "units": "yard"})


def test_reconstruction_replays_persisted_analysis_segmentation_settings() -> None:
    settings = _reconstruction_segmentation_settings(
        {
            "projectState": {
                "patches": [{"id": "patch.1", "type": "plane"}],
                "analysis": {
                    "settings": {
                        "smoothAngleDeg": 27.5,
                        "planarFitToleranceMm": 0.125,
                        "cylinderFitToleranceMm": 0.125,
                        "minimumCylinderCoverageDeg": 300.0,
                        "maximumCylinderAxisNormalComponent": 0.05,
                        "minimumFacetedCylinderSideCount": 10,
                        "maximumFacetedCylinderSagittaMm": 0.2,
                        "minimumPatchAreaMm2": 0.25,
                        "stableIdResolutionMm": 1e-5,
                    }
                },
            }
        }
    )

    assert settings.smooth_angle_deg == 27.5
    assert settings.planar_fit_tolerance_mm == 0.125
    assert settings.cylinder_fit_tolerance_mm == 0.125
    assert settings.minimum_patch_area_mm2 == 0.25
    assert settings.minimum_cylinder_coverage_deg == 300.0
    assert settings.maximum_cylinder_axis_normal_component == 0.05
    assert settings.minimum_faceted_cylinder_side_count == 10
    assert settings.maximum_faceted_cylinder_sagitta_mm == 0.2
    assert settings.stable_id_resolution_mm == 1e-5


def test_reconstruction_rejects_patches_without_their_analysis_settings() -> None:
    with pytest.raises(JobFailure) as captured:
        _reconstruction_segmentation_settings(
            {
                "projectState": {
                    "patches": [{"id": "patch.1", "type": "plane"}],
                    "analysis": {"patches": []},
                }
            }
        )
    assert captured.value.code == "analysis_settings_missing"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("smoothAngleDeg", float("nan")),
        ("planarFitToleranceMm", True),
        ("cylinderFitToleranceMm", 0.0),
        ("minimumCylinderCoverageDeg", 361.0),
        ("maximumCylinderAxisNormalComponent", 1.1),
        ("minimumFacetedCylinderSideCount", 7.5),
        ("maximumFacetedCylinderSagittaMm", 0.0),
        ("minimumPatchAreaMm2", -1.0),
        ("stableIdResolutionMm", 0.0),
    ],
)
def test_reconstruction_rejects_invalid_persisted_segmentation_settings(
    field: str,
    value: object,
) -> None:
    persisted: dict[str, object] = {
        "smoothAngleDeg": 12.0,
        "planarFitToleranceMm": 0.005,
        "cylinderFitToleranceMm": 0.01,
        "minimumCylinderCoverageDeg": 300.0,
        "maximumCylinderAxisNormalComponent": 0.05,
        "minimumFacetedCylinderSideCount": 8,
        "maximumFacetedCylinderSagittaMm": 0.1,
        "minimumPatchAreaMm2": 1e-8,
        "stableIdResolutionMm": 1e-5,
    }
    persisted[field] = value

    with pytest.raises(JobFailure) as captured:
        _reconstruction_segmentation_settings(
            {
                "projectState": {
                    "patches": [{"id": "patch.1", "type": "plane"}],
                    "analysis": {"settings": persisted},
                }
            }
        )

    assert captured.value.code == "invalid_analysis_settings"


def test_reconstruct_handler_passes_persisted_segmentation_to_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.stl"
    source.write_bytes(ASCII_SQUARE_STL)
    captured: dict[str, object] = {}

    def reconstruct_file(
        _source: Path,
        _workdir: Path,
        *,
        units: str,
        settings: Any,
        progress_callback: Any,
    ) -> object:
        del progress_callback
        captured["units"] = units
        captured["segmentation"] = settings.segmentation
        raise mesh2param.ReconstructionError(
            "segmentation", "captured-settings", "stop after capturing settings"
        )

    monkeypatch.setattr(mesh2param, "reconstruct_file", reconstruct_file)
    payload = {
        "sourcePath": str(source),
        "units": "mm",
        "settings": {},
        "projectState": {
            "patches": [{"id": "patch.1", "type": "plane"}],
            "analysis": {
                "settings": {
                    "smoothAngleDeg": 21.0,
                    "planarFitToleranceMm": 0.075,
                    "cylinderFitToleranceMm": 0.075,
                    "minimumCylinderCoverageDeg": 300.0,
                    "maximumCylinderAxisNormalComponent": 0.05,
                    "minimumFacetedCylinderSideCount": 12,
                    "maximumFacetedCylinderSagittaMm": 0.3,
                    "minimumPatchAreaMm2": 2.5,
                    "stableIdResolutionMm": 1e-5,
                }
            },
        },
    }

    with pytest.raises(JobFailure) as failure:
        run_handler("reconstruct", payload, tmp_path, _progress)

    assert failure.value.code == "captured-settings"
    segmentation: Any = captured["segmentation"]
    assert segmentation.smooth_angle_deg == 21.0
    assert segmentation.planar_fit_tolerance_mm == 0.075
    assert segmentation.cylinder_fit_tolerance_mm == 0.075
    assert segmentation.minimum_patch_area_mm2 == 2.5
    assert segmentation.minimum_cylinder_coverage_deg == 300.0
    assert segmentation.maximum_cylinder_axis_normal_component == 0.05
    assert segmentation.minimum_faceted_cylinder_side_count == 12
    assert segmentation.maximum_faceted_cylinder_sagitta_mm == 0.3
    assert segmentation.stable_id_resolution_mm == 1e-5


def test_automatic_detail_mode_is_bounded_and_defaults_to_functional() -> None:
    assert _automatic_detail_mode({"settings": {}}) == "functional"
    assert _automatic_detail_mode({"settings": {"detailMode": "full"}}) == "full"

    with pytest.raises(JobFailure) as invalid_mode:
        _automatic_detail_mode({"settings": {"detailMode": "everything"}})
    assert invalid_mode.value.code == "invalid_detail_mode"

    with pytest.raises(JobFailure) as unsupported:
        _automatic_detail_mode({"settings": {"detailMode": "full", "depth": 0.4}})
    assert unsupported.value.code == "invalid_reconstruction_settings"

    with pytest.raises(JobFailure) as invalid_reconstruction:
        _automatic_detail_mode({"settings": {"mode": "guess"}})
    assert invalid_reconstruction.value.code == "invalid_reconstruction_mode"


def test_reconstruct_handler_routes_full_detail_mode_to_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.stl"
    source.write_bytes(ASCII_SQUARE_STL)
    captured: dict[str, object] = {}

    def reconstruct_file(
        _source: Path,
        _workdir: Path,
        *,
        units: str,
        settings: Any,
        progress_callback: Any,
    ) -> object:
        del units, progress_callback
        captured["detail_mode"] = settings.detail_mode
        raise mesh2param.ReconstructionError(
            "detail-recovery", "captured-detail-mode", "stop after capturing mode"
        )

    monkeypatch.setattr(mesh2param, "reconstruct_file", reconstruct_file)
    payload = {
        "sourcePath": str(source),
        "units": "mm",
        "settings": {"detailMode": "full"},
    }

    with pytest.raises(JobFailure) as failure:
        run_handler("reconstruct", payload, tmp_path, _progress)

    assert failure.value.code == "captured-detail-mode"
    assert captured["detail_mode"] == "full"


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
    result = {
        "candidates": [candidate],
        "selectedCandidate": "measured",
        "detailMode": "full",
    }
    settings = _reconstruction_project_settings(
        {"projectState": {"settings": {"surfaceTolerance": 0.1}}}, result
    )

    assert settings == {
        "surfaceTolerance": 0.1,
        "candidateHistories": [candidate],
        "selectedCandidate": "measured",
        "detailMode": "full",
    }
    candidate["label"] = "mutated"
    assert settings["candidateHistories"][0]["label"] == "measured"
